"""Security response headers.

A small pure-ASGI middleware that stamps a strict Content-Security-Policy plus
the usual hardening headers onto every HTTP response. Pure ASGI (rather than
BaseHTTPMiddleware) so it adds nothing to the WebSocket path and never buffers
response bodies.

The CSP is intentionally skipped on FastAPI's interactive docs (/docs, /redoc,
/openapi.json): Swagger UI pulls its assets from a CDN and runs an inline
bootstrap script, so a nonce-free policy would break it. Those are developer
tools meant to be disabled in production, not part of the app's attack surface.
The other headers are still applied there.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def docs_urls(demo_mode: bool) -> dict[str, str | None]:
    """FastAPI docs kwargs. The interactive docs (Swagger/ReDoc/OpenAPI) are a
    dev convenience and an information-disclosure surface, so they are served
    only in demo mode; in production every docs URL is disabled.

    Spread into the FastAPI constructor: ``FastAPI(..., **docs_urls(demo))``.
    """
    if demo_mode:
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}

# name -> value, all latin-1 encodable. Applied to every HTTP response.
_BASE_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
    # Only honoured over HTTPS; harmless over the demo's plain HTTP.
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, csp: str) -> None:
        self.app = app
        self.csp = csp.encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        send_csp = not scope.get("path", "").startswith(_DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend(_BASE_HEADERS)
                if send_csp:
                    headers.append((b"content-security-policy", self.csp))
            await send(message)

        await self.app(scope, receive, send_with_headers)
