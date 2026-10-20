"""Regression for HTTPX parsing NO_PROXY IPv6 entries before sending any request."""
import asyncio
import base64
import httpx
import pytest
from app import providers


@pytest.mark.parametrize('destination', ['http://127.0.0.1:9000/v1', 'http://localhost:9000/v1', 'http://[::1]:9000/v1'])
def test_loopback_bypasses_environment_proxy(monkeypatch, destination):
    monkeypatch.setattr(providers, 'getproxies_environment', lambda: {'https': 'http://proxy.invalid:7890', 'all': 'socks5://proxy.invalid:7891', 'no': 'localhost,127.0.0.1,[::1]'})
    assert providers._network_options(destination) == {'trust_env': False, 'proxy': None}


def test_external_proxy_and_no_proxy_preserved(monkeypatch):
    proxies = {'https': 'http://proxy.invalid:7890', 'all': 'socks5://proxy.invalid:7891', 'no': 'localhost,127.0.0.1,[::1],.direct.example'}
    monkeypatch.setattr(providers, 'getproxies_environment', lambda: proxies)
    assert providers._network_options('https://models.example/v1')['proxy'] == proxies['https']
    assert providers._network_options('http://models.example/v1')['proxy'] == proxies['all']
    assert providers._network_options('https://cdn.direct.example/image.png')['proxy'] is None
    # Construction used to raise InvalidURL: Invalid port: ':1]'. No network I/O.
    async def construct():
        async with httpx.AsyncClient(**providers._network_options('https://models.example/v1')):
            pass
    asyncio.run(construct())


def test_invalid_proxy_is_safe_and_actionable(monkeypatch):
    monkeypatch.setattr(providers, 'getproxies_environment', lambda: {'https': 'http://user:secret@proxy.invalid:bad'})
    with pytest.raises(providers.ProviderError, match='环境代理') as caught:
        providers._network_options('https://models.example/v1')
    assert 'secret' not in str(caught.value)


def test_request_and_download_use_explicit_network_options(monkeypatch):
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (16, 16), 'blue').save(buffer, 'PNG')
    png = buffer.getvalue()
    real_client = httpx.AsyncClient
    seen_options = []
    def handler(request):
        if request.method == 'POST':
            assert request.headers['authorization'] == 'Bearer test-key'
            return httpx.Response(200, json={'data': [{'url': 'https://storage.example/image.png'}]})
        assert 'authorization' not in request.headers
        return httpx.Response(200, content=png, headers={'content-type': 'image/png'})
    def create(**kwargs):
        seen_options.append(dict(kwargs))
        # The explicit proxy is tested above; mock both HTTP transports here.
        kwargs.pop('proxy', None)
        return real_client(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(providers.httpx, 'AsyncClient', create)
    monkeypatch.setattr(providers, 'getproxies_environment', lambda: {'https': 'http://proxy.invalid:7890', 'no': '[::1],localhost'})
    config = {'base_url': 'https://models.example/v1', 'model': 'image', 'api_key': 'test-key', 'mode': 'background'}
    assert asyncio.run(providers.generate_image(config, 'A room background', [])) == png
    assert len(seen_options) == 2
    assert all(options['trust_env'] is False and options['proxy'] == 'http://proxy.invalid:7890' for options in seen_options)
