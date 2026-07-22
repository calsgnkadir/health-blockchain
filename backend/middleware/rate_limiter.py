import time
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.dependencies import _get_client_ip
from database.sql_db import default_sql_db
from infrastructure.repositories.sql_repositories import _to_placeholder

RATE_LIMIT_WINDOW = 60   # seconds
RATE_LIMIT_MAX = 5       # max 5 login attempts per minute

def _check_rate_limit(ip: str) -> bool:
    """Returns True if allowed, False if rate limit exceeded using SQL persistence."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    
    conn = default_sql_db.get_connection()
    cursor = conn.cursor()
    try:
        # General cleanup of expired rate limits to keep database size minimal
        cleanup_sql = _to_placeholder("DELETE FROM rate_limits WHERE timestamp < ?")
        cursor.execute(cleanup_sql, (cutoff,))
        
        # Count attempts for this client IP in the time window
        count_sql = _to_placeholder("SELECT COUNT(*) FROM rate_limits WHERE ip = ? AND timestamp >= ?")
        cursor.execute(count_sql, (ip, cutoff))
        count = cursor.fetchone()[0]
        
        if count >= RATE_LIMIT_MAX:
            conn.commit()
            return False
            
        # Log this attempt
        insert_sql = _to_placeholder("INSERT INTO rate_limits (ip, timestamp) VALUES (?, ?)")
        cursor.execute(insert_sql, (ip, now))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        # Fallback to True under failure conditions to avoid system lockouts
        print(f"[RateLimiter Warning] Database rate limit check failed ({e}). Falling back to permissive mode.")
        return True
    finally:
        cursor.close()
        conn.close()


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
