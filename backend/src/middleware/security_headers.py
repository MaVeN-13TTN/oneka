"""Security headers middleware — Phase 7 hardening."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Paths that serve Swagger UI / ReDoc — these need relaxed CSP to load
# external JS, CSS, and fonts from CDN.
_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if request.url.path in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: https://cdn.jsdelivr.net https://fastapi.tiangolo.com https://cdn.redoc.ly; "
                "worker-src 'self' blob:; "
                "connect-src 'self'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' https://*.amazonaws.com; "
                "style-src 'self' 'unsafe-inline'"
            )

        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
        return response
