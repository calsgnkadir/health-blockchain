import time
import threading
from typing import Dict, List
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.dependencies import _get_client_ip

_login_attempts: Dict[str, List[float]] = defaultdict(list)
_rate_lock = threading.Lock()
RATE_LIMIT_WINDOW = 60   # seconds
RATE_LIMIT_MAX = 5       # max 5 login attempts per minute

def _check_rate_limit(ip: str) -> bool:
    """Returns True if allowed, False if rate limit exceeded."""
    now = time.time()
    with _rate_lock:
        attempts = _login_attempts[ip]
        # Clear attempts outside the time window
        _login_attempts[ip] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
        if len(_login_attempts[ip]) >= RATE_LIMIT_MAX:
            return False
        _login_attempts[ip].append(now)
        return True

class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path == "/api/auth/login":
            client_ip = _get_client_ip(request)
            if not _check_rate_limit(client_ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many login attempts. Please wait 1 minute."}
                )
        return await call_next(request)
