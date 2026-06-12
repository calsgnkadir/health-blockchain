"""
backend/main.py — VIP Health Vault · Backend API v3.0
======================================================
"""

import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Path Configuration
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load .env file if it exists
_dotenv_path = os.path.join(_PROJECT_ROOT, ".env")
if os.path.exists(_dotenv_path):
    with open(_dotenv_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#"):
                continue
            if "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ[_key.strip()] = _val.strip().strip('"').strip("'")


from core.security import get_device_id
import database.storage as storage

# Middlewares
from backend.middleware.csrf import CSRFMiddleware
from backend.middleware.rate_limiter import RateLimiterMiddleware

# Routers
from backend.routers.auth import router as auth_router
from backend.routers.admin import router as admin_router
from backend.routers.consent import router as consent_router
from backend.routers.records import router as records_router
from backend.routers.misc import router as misc_router

app = FastAPI(
    title="VIP Health Vault API",
    version="3.1.0",
    description="Blockchain-based VIP health record system",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

# Custom Middlewares
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimiterMiddleware)

# Register routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(consent_router)
app.include_router(records_router)
app.include_router(misc_router)

@app.on_event("startup")
async def startup_event():
    """Initialize user database on startup."""
    env = os.environ.get("ENVIRONMENT", "production")
    demo_mode = os.getenv("VHV_DEMO_MODE", "false").lower() == "true"
    if env == "development" or demo_mode:
        storage.seed_default_users()
        print("[INFO] Seeding default users (Development/Demo Mode)")
    else:
        print("[INFO] Production Mode — Skipping default user seeding")
    print(f"[OK] VIP Health Vault API v3.0 ready - Device: {get_device_id()[:16]}...")

# Serve static frontend SPA files
STATIC = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    async def frontend_root():
        return FileResponse(os.path.join(STATIC, "index.html"))

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_spa(path: str = ""):
        # Skip API paths
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(os.path.join(STATIC, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
