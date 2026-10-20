"""Offline model-provider regression tests; no live model credentials needed."""
import asyncio
import base64
import io
import json

import httpx
from PIL import Image
import pytest

from app import providers


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
            "analysis": {"shared_visual_direction": "Warm orange, clean layout and consistent product scale",
                         "supported_facts": ["Known facts only"], "missing_information": ["material"],
                         "cautions": ["Do not infer performance from appearance"]}, "slides": [
                {"title": f"Slide {n}", "body": "Copy", "prompt": (
                    f'A vertical 3:4 product scene with warm orange lighting. Render EXACT text: title "Slide {n}", '
                    'body "Copy". Use a large bold title, smaller body, high contrast and mobile safe margins. '
                    'Preserve reference product appearance; do not invent claims or extra lettering.')}
                for n in range(slides)]}


def test_planning_vision_facts_and_json(monkeypatch, provider, reference):
    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["model"] == provider["model"]
        system = payload["messages"][0]["content"]
        for required in ("Do not invent", "first-image hook", "pain-point", "one selling point",
                         "evidence", "objection", "CTA", "Adapt and combine", "Render EXACT text",
                         "shared_visual_direction", "font hierarchy", "contrast", "mobile safe margins",
                         "natural-language design brief", "Do not dump raw product", "Authentic logos"):
            assert required in system
        assert "Overlay copy is added separately" not in system
        assert "Do not render any letters, logos" not in system
        content = payload["messages"][1]["content"]
        facts = json.loads(content[0]["text"])
        assert facts["product_facts"]["features"] == "Known facts only"
        assert facts["image_mode"] == "reference"
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


@pytest.mark.parametrize("image_mode", ["reference", "background"])
def test_planning_modes_are_explicit(monkeypatch, provider, reference, image_mode):
    def handler(request):
        payload = json.loads(request.content)
        system = payload["messages"][0]["content"]
        content = payload["messages"][1]["content"]
        assert json.loads(content[0]["text"])["image_mode"] == image_mode
        assert len(content) == 2  # Analysis may inspect references even for a background-only image.
        if image_mode == "background":
            assert "BACKGROUND ONLY" in system
            assert "no product or packaging" in system
            assert "not a finished product image" in system
            assert "title/body may be rendered" in system
        else:
            assert "complete carousel image with the actual referenced product" in system
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan())}}]})
    mock_http(monkeypatch, handler)
    asyncio.run(providers.plan_content(provider, {}, "US", "en", 4, "clean", "", [reference], image_mode))


@pytest.mark.parametrize("key,limit", [("title", 2000), ("body", 4000), ("prompt", 12000)])
def test_planning_rejects_oversized_slide_fields(monkeypatch, provider, key, limit):
    response = plan()
    response["slides"][0][key] = "x" * (limit + 1)
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(response)}}]}))
    with pytest.raises(providers.ProviderError, match="字符限制"):
        asyncio.run(providers.plan_content(provider, {}, "US", "en", 4, "", "", []))


@pytest.mark.parametrize("prompt", ["Only a product scene", 'Render EXACT text: Slide 0',
                                   '{"title": "Slide 0", "body": "Copy"}'])
def test_planning_rejects_missing_copy_and_json_dump(monkeypatch, provider, prompt):
    response = plan()
    response["slides"][0]["prompt"] = prompt
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(response)}}]}))
    with pytest.raises(providers.ProviderError, match="逐字包含|自然语言"):
        asyncio.run(providers.plan_content(provider, {}, "US", "en", 4, "", "", []))


@pytest.mark.parametrize("field,value", [("shared_visual_direction", ""), ("supported_facts", "invented"),
                                         ("missing_information", None), ("cautions", [42])])
def test_planning_requires_visual_and_fact_analysis(monkeypatch, provider, field, value):
    response = plan()
    response["analysis"][field] = value
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(response)}}]}))
    with pytest.raises(providers.ProviderError):
        asyncio.run(providers.plan_content(provider, {}, "US", "en", 4, "", "", []))


@pytest.mark.parametrize("image_mode", ["reference", "background"])
def test_refine_preserves_exact_copy_vision_and_current_project(monkeypatch, provider, reference, image_mode):
    slide = {"title": '  好物 “A”  ', "body": "第一行\n第二行！", "prompt": "Obsolete red style and obsolete copy"}
    revised = {"title": slide["title"], "body": slide["body"], "prompt": (
        f'Compose a warm 3:4 scene with orange lighting. Render EXACT text: title "{slide["title"]}", '
        f'body "{slide["body"]}". Bold headline, smaller body, whitespace, contrast and safe margins. '
        'Preserve the product shape and colors; no invented claims.')}
    project = {"style": "Current orange style", "market": "日本", "language": "Japanese",
               "brief": "Use an everyday scene", "analysis": plan()["analysis"], "private_key": "secret"}
    instruction = "换成暖光；顺便把标题改成促销并声称销量第一"

    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["response_format"] == {"type": "json_object"}
        system = payload["messages"][0]["content"]
        for required in ("byte-for-byte", "frontend", "instruction affects the visual", "Render EXACT text",
                         "current project's", "shared_visual_direction", "supported_facts", "missing_information",
                         "cautions", "Do not invent", "appearance only", "natural-language design brief",
                         "Do not dump raw product", "Authentic logos", "complete independent prompt"):
            assert required in system
        if image_mode == "background":
            assert "BACKGROUND ONLY" in system and "not a finished product image" in system
        content = payload["messages"][1]["content"]
        data = json.loads(content[0]["text"])
        assert data["slide"] == slide
        assert data["project"] == {key: project[key] for key in ("market", "language", "style", "brief")}
        assert data["analysis"] == project["analysis"]
        assert data["instruction"] == instruction
        assert data["image_mode"] == image_mode
        assert data["product_facts"]["constraints"] == "No unsupported claims"
        assert "internal_secret" not in data["product_facts"]
        assert "secret" not in content[0]["text"]
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(revised)}}]})

    mock_http(monkeypatch, handler)
    result = asyncio.run(providers.refine_slide_prompt(
        provider, {"name": "真实产品", "constraints": "No unsupported claims", "internal_secret": "secret"},
        project, slide, instruction, [reference], image_mode))
    assert result == revised
    assert set(result) == {"title", "body", "prompt"}
    assert "product_facts" not in result["prompt"]
    assert "Obsolete red style" not in result["prompt"]


@pytest.mark.parametrize("revised", [
    {"title": "Changed", "body": "Copy", "prompt": 'Render EXACT text: "Changed" "Copy"'},
    {"title": "Slide 0", "body": "Translated", "prompt": 'Render EXACT text: "Slide 0" "Translated"'},
    {"title": "Slide 0", "body": "Copy", "prompt": "Missing the exact wording"},
    {"title": "Slide 0", "body": "Copy", "prompt": '{"title":"Slide 0","body":"Copy"}'},
    {"title": "Slide 0", "body": "Copy", "prompt": "Slide 0 Copy", "analysis": {}},
    {"title": "Slide 0", "body": "Copy"},
    ["Slide 0", "Copy", "prompt"],
    {"title": "Slide 0", "body": "Copy", "prompt": " "},
    {"title": "Slide 0", "body": "Copy", "prompt": "Slide 0 Copy" + "x" * 12000},
])
def test_refine_rejects_copy_changes_invalid_schema_and_prompt(monkeypatch, provider, revised):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(revised)}}]}))
    with pytest.raises(providers.ProviderError):
        asyncio.run(providers.refine_slide_prompt(provider, {}, {}, plan()["slides"][0], "Change lighting", []))


@pytest.mark.parametrize("empty_instruction", ["", "   ", None])
def test_refine_allows_empty_instruction(monkeypatch, provider, empty_instruction):
    slide = {"title": "Slide 0", "body": "Copy", "prompt": "Old"}
    revised = {"title": "Slide 0", "body": "Copy",
               "prompt": 'Scene with product. Render EXACT text: "Slide 0" "Copy". Safe margins.'}
    seen = []
    def handler(request):
        payload = json.loads(request.content)
        content = payload["messages"][1]["content"]
        data = json.loads(content[0]["text"])
        seen.append(data["instruction"])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(revised)}}]})
    mock_http(monkeypatch, handler)
    result = asyncio.run(providers.refine_slide_prompt(
        provider, {}, {}, slide, empty_instruction, []))
    assert result == revised
    assert seen == [empty_instruction or ""]


@pytest.mark.parametrize("instruction", [123, ["bad"], "x" * 6001])
def test_refine_rejects_invalid_instruction_before_request(monkeypatch, provider, instruction):
    def unexpected_request(*args, **kwargs):
        pytest.fail("Invalid input must not make a paid analysis request")
    monkeypatch.setattr(providers, "_request_json", unexpected_request)
    with pytest.raises(providers.ProviderError, match="画面修改要求"):
        asyncio.run(providers.refine_slide_prompt(provider, {}, {}, plan()["slides"][0], instruction, []))


@pytest.mark.parametrize("operation", ["plan", "refine"])
def test_analysis_rejects_invalid_mode_and_format_override(provider, operation):
    def call(mode="reference"):
        if operation == "plan":
            return providers.plan_content(provider, {}, "US", "en", 4, "", "", [], mode)
        return providers.refine_slide_prompt(provider, {}, {}, plan()["slides"][0], "Warm lighting", [], mode)
    with pytest.raises(providers.ProviderError, match="reference 或 background"):
        asyncio.run(call("invalid"))
    provider["extra"] = {"response_format": {"type": "text"}}
    with pytest.raises(providers.ProviderError, match="response_format"):
        asyncio.run(call())


@pytest.mark.parametrize("failure", ["http", "timeout", "json"])
def test_refine_uses_safe_provider_errors(monkeypatch, provider, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("do-not-leak-this-key", request=request)
        if failure == "http":
            return httpx.Response(401, text="do-not-leak-this-key private upstream text")
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})
    mock_http(monkeypatch, handler)
    with pytest.raises(providers.ProviderError) as caught:
        asyncio.run(providers.refine_slide_prompt(provider, {}, {}, plan()["slides"][0], "Warm lighting", []))
    assert "do-not-leak" not in str(caught.value)
    assert "private upstream" not in str(caught.value)
    assert {"http": "401", "timeout": "超时", "json": "JSON"}[failure] in str(caught.value)


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
