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
request payloads. Escaping on the way in corrupts client records permanently and
still leaves any unescaped sink exploitable.
"""

import os

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
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        # Deny powerful features the vault never uses; keep WebAuthn (passkeys),
        # which needs publickey-credentials-get, scoped to same-origin.
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), "
            "publickey-credentials-get=(self)"
        )

        # HSTS only over TLS: pinning localhost/http would brick local dev, and
        # browsers honour HSTS on https responses only. Trust the proxy's
        # X-Forwarded-Proto since TLS is terminated at the reverse proxy.
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
            or os.getenv("ENVIRONMENT", "production").lower() == "production"
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            # No inline script anywhere: every handler is declared with a
            # data-action attribute and dispatched from actions.js, so an injected
            # string cannot execute even if it reaches the DOM.
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'self';"
        )
        return response
