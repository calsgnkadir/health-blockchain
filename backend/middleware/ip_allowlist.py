"""
backend/middleware/ip_allowlist.py — Network Level Isolation Middleware
========================================================================
Restricts incoming API access strictly to authorized internal CIDR subnets,
private VPNs, and loopback addresses. Blocks public internet IP ranges.
"""

import os
import ipaddress
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


DEFAULT_ALLOWED_SUBNETS = [
    "127.0.0.1/32",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
]


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces IP allowlisting for network-level isolation.
    """

    def __init__(self, app):
        super().__init__(app)
        self.enabled = os.getenv("VIP_IP_ALLOWLIST_ENABLED", "true").lower() in ("true", "1", "yes")

        custom_networks = os.getenv("ALLOWLISTED_NETWORKS", "").strip()
        subnet_strings = [s.strip() for s in custom_networks.split(",") if s.strip()] if custom_networks else DEFAULT_ALLOWED_SUBNETS

        self.allowed_networks = []
        for s in subnet_strings:
            try:
                self.allowed_networks.append(ipaddress.ip_network(s, strict=False))
            except ValueError:
                print(f"[IPAllowlist Warning] Invalid CIDR subnet format ignored: {s}")

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    def is_ip_allowed(self, ip_str: str) -> bool:
        if not self.enabled:
            return True

        try:
            ip_obj = ipaddress.ip_address(ip_str)
            return any(ip_obj in net for net in self.allowed_networks)
        except ValueError:
            return False

    async def dispatch(self, request: Request, call_next):
        # Exclude static assets or documentation from IP block if needed
        if request.url.path.startswith("/static") or request.url.path == "/favicon.ico":
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        if not self.is_ip_allowed(client_ip):
            print(f"[SECURITY ALERT] Blocked connection attempt from unauthorized IP: {client_ip} on {request.url.path}")
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Access Denied: IP address {client_ip} is not in the authorized internal network / VPN allowlist.",
                    "ip": client_ip,
                    "error": "NETWORK_LEVEL_ISOLATION_ENFORCED"
                }
            )

        return await call_next(request)
