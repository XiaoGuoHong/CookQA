from api.app import create_app
from tests.http_client import asgi_client
from tests.test_api import FakeGenerator, FakeReadiness, FakeService


def web_app():
    return create_app(FakeService(), FakeReadiness(), FakeGenerator())


async def test_homepage_and_static_assets_are_served():
    async with asgi_client(web_app()) as client:
        homepage = await client.get("/")
        javascript = await client.get("/static/app.js")
        styles = await client.get("/static/styles.css")

    assert homepage.status_code == 200
    assert javascript.status_code == 200
    assert styles.status_code == 200


async def test_homepage_has_accessible_search_controls():
    async with asgi_client(web_app()) as client:
        html = (await client.get("/")).text

    assert 'id="query-input"' in html
    assert 'id="search-form"' in html
    assert 'aria-live="polite"' in html


async def test_javascript_uses_separate_search_detail_and_generation_endpoints():
    async with asgi_client(web_app()) as client:
        javascript = (await client.get("/static/app.js")).text

    assert "/api/v1/search" in javascript
    assert "/api/v1/recipes/" in javascript
    assert "/answer/stream" in javascript
