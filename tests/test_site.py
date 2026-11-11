"""Fixed-path files for browsers and search engines (web/routes/site.py) and
the page <head>.  Run: python -m pytest"""
import pytest


@pytest.fixture
def client():
    from helpers import web_site
    return web_site().app.test_client()


@pytest.mark.parametrize("path, mimetype", [
    ("/favicon.ico", "image/png"),
    ("/apple-touch-icon.png", "image/png"),
    ("/robots.txt", "text/plain"),
    ("/sitemap.xml", "application/xml"),
])
def test_served_without_registration(client, path, mimetype):
    r = client.get(path)
    assert r.status_code == 200 and r.mimetype == mimetype


def test_robots_hides_private_pages_and_points_to_sitemap(client):
    text = client.get("/robots.txt", base_url="https://avalon.iammerlin.fyi").text
    assert "Disallow: /admin" in text and "Disallow: /host" in text
    assert "Sitemap: https://avalon.iammerlin.fyi/sitemap.xml" in text


def test_sitemap_lists_start_and_rules_pages(client):
    xml = client.get("/sitemap.xml", base_url="https://avalon.iammerlin.fyi").text
    assert "<loc>https://avalon.iammerlin.fyi/register</loc>" in xml
    assert "<loc>https://avalon.iammerlin.fyi/rules/merlin</loc>" in xml


def test_unknown_page_is_404_not_redirect(client):
    assert client.get("/no-such-page").status_code == 404


def test_known_page_still_asks_for_a_name(client):
    r = client.get("/")
    assert r.status_code == 302 and "/register" in r.headers["Location"]


def test_head(client):
    html = client.get("/rules/merlin").text.split("</head>")[0]
    assert '<html lang="en">' in client.get("/register").text
    assert '<meta charset="utf-8">' in html
    assert '<link rel="canonical" href="https://localhost/rules/merlin">' in html
    assert '<meta name="description" content="THavalon rules: Merlin.' in html


def test_security_headers(client):
    for path in ("/register", "/no-such-page", "/static/style.css"):
        r = client.get(path)
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["Strict-Transport-Security"].startswith("max-age=")


def test_http_visitors_are_sent_to_https(client):
    r = client.get("/rules/merlin?x=1", base_url="http://avalon.iammerlin.fyi",
                   headers={"CF-Visitor": '{"scheme":"http"}'})
    assert r.status_code == 301
    assert r.headers["Location"] == "https://avalon.iammerlin.fyi/rules/merlin?x=1"


def test_https_visitors_are_served(client):
    r = client.get("/rules/merlin", headers={"CF-Visitor": '{"scheme":"https"}'})
    assert r.status_code == 200
