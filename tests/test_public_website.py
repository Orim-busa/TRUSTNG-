from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_root_serves_dijuang_homepage():
    response = client.get("/")

    assert response.status_code == 200
    assert "DIJUANG" in response.text
    assert "Built around what matters" in response.text


def test_dijuang_homepage_has_developer_navigation():
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/"' in response.text
    assert 'href="/trustng/developers/"' in response.text
    assert "Developers &amp; Code" in response.text


def test_trustng_developer_page_links_to_technical_resources():
    response = client.get("/trustng/developers/")

    assert response.status_code == 200
    assert 'href="/docs"' in response.text
    assert 'href="/openapi.json"' in response.text
    assert 'href="/trustng/architecture/"' in response.text
    assert "https://github.com/Orim-busa/TRUSTNG-" in response.text
