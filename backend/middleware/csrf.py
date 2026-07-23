import os
import secrets
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_testing = os.getenv("TESTING", "false").lower() == "true"
        if (
            request.method in ("GET", "HEAD", "OPTIONS")
            or not path.startswith("/api/")
            or path.endswith("/login")
            or path.endswith("/wallet-login")
            or path.endswith("/nonce")
            or path.endswith("/activate")       # Emergency QR activation (no-auth endpoint)
            or "/webauthn/" in path             # WebAuthn flows
            or "/emergency/revoke/" in path     # Revoke is authenticated via JWT bearer
            or "/deadman/" in path              # Dead-Man's switch endpoints use JWT bearer
            or is_testing
        ):
            response = await call_next(request)
            if not request.cookies.get("csrf_token"):
                env = os.environ.get("ENVIRONMENT", "production")
                is_secure = (env == "production")
                response.set_cookie(
                    "csrf_token",
                    secrets.token_hex(32),
                    samesite="strict",
                    secure=is_secure,
                    httponly=False  # Must be readable by JavaScript
                )
            return response

        # Unsafe requests (POST, PUT, DELETE) on API paths
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("x-csrf-token")

        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token validation failed — missing or mismatched token"}
            )

        return await call_next(request)
