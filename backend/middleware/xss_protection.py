"""
backend/middleware/xss_protection.py — Security & XSS Protection Middleware
=============================================================================
1. Enforces Hardened HTTP Security Headers:
   - Content-Security-Policy (CSP)
   - X-XSS-Protection
   - X-Content-Type-Options
   - X-Frame-Options
   - Referrer-Policy
2. Sanitizes dynamic string inputs against Reflected and Stored XSS.
"""

import html
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

def sanitize_xss_data(data):
    """Recursively sanitizes dynamic strings against XSS attacks."""
    if isinstance(data, str):
        return html.escape(data, quote=True)
    elif isinstance(data, dict):
        return {k: sanitize_xss_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_xss_data(item) for item in data]
    return data

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
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self';"
        )
        return response
