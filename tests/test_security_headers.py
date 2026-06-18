"""SecurityHeadersMiddleware unit behaviour + confirmation the app wires it."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.security import SecurityHeadersMiddleware


def _mini_client(csp="default-src 'self'"):
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, csp=csp)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return TestClient(app)


def test_hardening_headers_present():
    r = _mini_client().get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_csp_skipped_on_docs_but_other_headers_kept():
    # FastAPI auto-serves /openapi.json; the middleware exempts it from CSP.
    r = _mini_client().get("/openapi.json")
    assert "content-security-policy" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_real_app_wires_the_middleware():
    from api.main import app

    assert any(m.cls is SecurityHeadersMiddleware for m in app.user_middleware)
