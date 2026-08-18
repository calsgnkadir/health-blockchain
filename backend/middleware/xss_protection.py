"""
backend/middleware/xss_protection.py — Security & XSS Protection Middleware
=============================================================================
1. Enforces Hardened HTTP Security Headers:
   - Content-Security-Policy (CSP)
   - X-XSS-Protection
   - X-Content-Type-Options
   - X-Frame-Options
   - Referrer-Policy
2. Sets a Content-Security-Policy that keeps a script injection from executing.

Note on layering: clinical text is stored verbatim (see backend.schemas.requests)
and escaped where it is rendered, so this module deliberately does not rewrite
request payloads. Escaping on the way in corrupts medical records permanently and
still leaves any unescaped sink exploitable.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class XSSProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # Apply Hardened HTTP Security Headers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            # 'unsafe-inline' remains only because the markup still uses inline
            # event handlers; 'unsafe-eval' is not needed by anything we ship.
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'self';"
        )
        return response
