"""Offline provider and rendering regression tests; no live model credentials needed."""
import asyncio
import base64
import io
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest

from app import providers, rendering


@pytest.fixture
def provider():
    return {"base_url": "https://models.example/v1", "model": "example-model",
            "api_key": "do-not-leak-this-key", "timeout": 20, "mode": "reference", "extra": {}}


@pytest.fixture
def png():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "orange").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def reference(tmp_path, png):
    target = tmp_path / "reference.png"
    target.write_bytes(png)
    return target


def mock_http(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(providers, 'getproxies_environment', lambda: {})
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=transport))


def plan(slides=4):
    return {"title": "Title", "caption": "Caption", "tags": ["tag"],
            "analysis": {"missing_information": ["material"]}, "slides": [
                {"title": f"Slide {n}", "body": "Copy", "prompt": "A product, no text"}
                for n in range(slides)]}


def test_planning_vision_facts_and_json(monkeypatch, provider, reference):
    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["model"] == provider["model"]
        assert "Do not invent" in payload["messages"][0]["content"]
        content = payload["messages"][1]["content"]
        facts = json.loads(content[0]["text"])
        assert facts["product_facts"]["features"] == "Known facts only"
        assert "internal_secret" not in facts["product_facts"]
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan())}}]})
    mock_http(monkeypatch, handler)
    result = asyncio.run(providers.plan_content(
        provider, {"name": "Product", "features": "Known facts only", "internal_secret": "private"},
        "US", "en", 4, "clean", "Do not invent specs", [reference]))
    assert len(result["slides"]) == 4
    assert result["analysis"]["missing_information"] == ["material"]


@pytest.mark.parametrize("image_count", [0, 3, 11, True, 4.0])
def test_planning_input_image_count_is_strict(provider, image_count):
    with pytest.raises(providers.ProviderError, match="4 到 10"):
        asyncio.run(providers.plan_content(provider, {}, "US", "en", image_count, "", "", []))


@pytest.mark.parametrize("bad_plan", [plan(3), plan(5), {**plan(), "tags": "tag"},
                                     {**plan(), "analysis": []},
                                     {**plan(), "slides": [{"title": "x", "body": "", "prompt": "p"}] * 4}])
def test_planning_output_is_strict(monkeypatch, provider, bad_plan):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(bad_plan)}}]}))
    with pytest.raises(providers.ProviderError):
        asyncio.run(providers.plan_content(provider, {}, "US", "en", 4, "", "", []))


def test_reference_multipart_keeps_all_images(monkeypatch, provider, reference, png):
    def handler(request):
        assert request.url.path == "/v1/images/edits"
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert request.content.count(b'name="image[]"') == 2
        assert b'name="n"\r\n\r\n1' in request.content
        assert b'name="quality"\r\n\r\nhigh' in request.content
        assert request.headers["Authorization"] == "Bearer do-not-leak-this-key"
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]})
    mock_http(monkeypatch, handler)
    provider["extra"] = {"quality": "high"}
    assert asyncio.run(providers.generate_image(provider, "A clean product", [reference, reference])) == png


def test_background_generation_and_download_without_key(monkeypatch, provider, png):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if request.method == "POST":
            assert request.url.path == "/v1/images/generations"
            assert json.loads(request.content)["n"] == 1
            return httpx.Response(200, json={"data": [{"url": "https://cdn.example/image.png"}]})
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=png, headers={"content-type": "image/png"})
    mock_http(monkeypatch, handler)
    provider["mode"] = "background"
    assert asyncio.run(providers.generate_image(provider, "A background", [])) == png
    assert len(seen) == 2


@pytest.mark.parametrize("headers,content", [
    ({"content-type": "text/html"}, b"<html>not image</html>"),
    ({"content-type": "image/png", "content-length": str(providers.MAX_IMAGE_BYTES + 1)}, b"x"),
    ({"content-type": "image/png"}, b"invalid image"),
])
def test_download_rejects_bad_type_size_content(monkeypatch, provider, headers, content):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": "https://cdn.example/image.png"}]})
        return httpx.Response(200, headers=headers, content=content)
    mock_http(monkeypatch, handler)
    provider["mode"] = "background"
    with pytest.raises(providers.ProviderError):
        asyncio.run(providers.generate_image(provider, "image", []))


def test_never_falls_back_or_ignores_references(provider, reference):
    with pytest.raises(providers.ProviderError, match="需要至少一张"):
        asyncio.run(providers.generate_image(provider, "image", []))
    provider["mode"] = "background"
    with pytest.raises(providers.ProviderError, match="不接受参考图"):
        asyncio.run(providers.generate_image(provider, "image", [reference]))


@pytest.mark.parametrize("key", ["model", "prompt", "messages", "image[]", "n", "stream", "API_KEY"])
def test_extra_cannot_override_core_fields(provider, key):
    provider["extra"] = {key: "override"}
    with pytest.raises(providers.ProviderError, match="关键参数"):
        asyncio.run(providers.generate_image(provider, "image", []))


def test_provider_error_does_not_expose_response_or_key(monkeypatch, provider):
    mock_http(monkeypatch, lambda request: httpx.Response(401, text="do-not-leak-this-key private upstream text"))
    provider["mode"] = "background"
    with pytest.raises(providers.ProviderError) as caught:
        asyncio.run(providers.generate_image(provider, "image", []))
    assert "401" in str(caught.value)
    assert "do-not-leak" not in str(caught.value)
    assert "private upstream" not in str(caught.value)


def test_timeout_message_is_safe(monkeypatch, provider):
    def handler(request):
        raise httpx.ReadTimeout("do-not-leak-this-key", request=request)
    mock_http(monkeypatch, handler)
    provider["mode"] = "background"
    with pytest.raises(providers.ProviderError, match="超时") as caught:
        asyncio.run(providers.generate_image(provider, "image", []))
    assert "do-not-leak" not in str(caught.value)


def test_test_provider_does_real_image_request_with_memory_reference(monkeypatch, provider, png):
    def handler(request):
        assert request.url.path == "/v1/images/edits"
        assert b"test-reference.png" in request.content
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]})
    mock_http(monkeypatch, handler)
    message = asyncio.run(providers.test_provider("image", provider))
    assert "实际生成" in message


def test_analysis_connection_checks_json(monkeypatch, provider):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"ok":true}'}}]}))
    assert "JSON" in asyncio.run(providers.test_provider("analysis", provider))


@pytest.mark.parametrize("size", [(1600, 600), (300, 1600), (300, 300)])
def test_render_crop_gradient_and_no_model_calls(tmp_path, size):
    source, output = tmp_path / "base.png", tmp_path / "nested" / "out.png"
    Image.new("RGB", size, "white").save(source)
    rendering.render_image(source, output, "Readable title", "Body text " * 90, "en")
    with Image.open(output) as result:
        assert result.size == (1080, 1440)
        assert result.mode == "RGB"
        assert sum(result.getpixel((20, 1400))) < sum(result.getpixel((20, 200)))
    with Image.open(source) as original:
        assert original.size == size
        assert original.getpixel((0, 0)) == (255, 255, 255)


def test_unicode_wrap_and_fit_never_overflow():
    text = "中文商品介绍，这是已知事实。超长说明" * 80
    try:
        font, lines, step = rendering._fit_text(text, "zh-CN", 928, 330, 38, 24)
    except RuntimeError:
        pytest.skip("CJK font is not installed in this test environment")
    assert all(font.getlength(line) <= 928 for line in lines)
    assert len(lines) * step <= 330
    assert lines[-1].endswith("…")
    english = rendering._wrap_text("A " + "longword" * 100, font, 928)
    assert all(font.getlength(line) <= 928 for line in english)


def test_render_unicode_and_transparency(tmp_path):
    try:
        rendering._load_font(24, "zh", "中文")
    except RuntimeError:
        pytest.skip("CJK font is not installed in this test environment")
    source, output = tmp_path / "base.png", tmp_path / "out.jpg"
    Image.new("RGBA", (500, 800), (255, 0, 0, 0)).save(source)
    rendering.render_image(source, output, "中文商品标题" * 40, "说明文案 " * 200, "zh")
    with Image.open(output) as result:
        assert result.size == (1080, 1440)
        assert result.getpixel((20, 20))[0] > 230


def test_render_exif_orientation(tmp_path):
    source, output = tmp_path / "base.jpg", tmp_path / "out.png"
    image = Image.new("RGB", (80, 120), "red")
    image.paste("blue", (0, 60, 80, 120))
    exif = image.getexif()
    exif[274] = 6
    image.save(source, exif=exif)
    rendering.render_image(source, output, "", "")
    with Image.open(output) as result:
        left, right = result.getpixel((10, 720)), result.getpixel((1070, 720))
        assert left[2] > left[0]
        assert right[0] > right[2]
