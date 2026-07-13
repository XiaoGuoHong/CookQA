from fastapi.testclient import TestClient

from api.app import create_app
from tests.test_api import FakeGenerator, FakeReadiness, FakeService


def web_client():
    return TestClient(create_app(FakeService(), FakeReadiness(), FakeGenerator()))


def test_homepage_and_static_assets_are_served():
    client = web_client()

    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_homepage_has_accessible_search_controls():
    html = web_client().get("/").text

    assert 'id="query-input"' in html
    assert 'id="search-form"' in html
    assert 'aria-live="polite"' in html


def test_javascript_uses_separate_search_detail_and_generation_endpoints():
    javascript = web_client().get("/static/app.js").text

    assert "/api/v1/search" in javascript
    assert "/api/v1/recipes/" in javascript
    assert "/answer/stream" in javascript
