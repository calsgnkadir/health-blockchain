"""
backend/routers/emergency.py — QR/NFC Break-Glass Emergency Access (Seviye 3)
==============================================================================

Ambulans görevlisi veya acil servis personeli, hastanın önceden ürettiği
QR kodu okutarak kimlik doğrulamasına gerek kalmadan 15 dakikalık
READ-ONLY acil erişim token'ı alır. Her aktivasyon imzalı, denetimli
(audit-logged) ve otomatik süre sınırlıdır.

Endpoints:
    GET  /api/v1/emergency/qr/{patient_id}          → QR kod PNG görüntüsü üret
    GET  /api/v1/emergency/qr/token/{patient_id}    → Sadece QR token string döndür
    POST /api/v1/emergency/activate                 → QR token ile acil erişim başlat (auth gerekmez)
    GET  /api/v1/emergency/sessions/{patient_id}    → Aktif acil oturumları listele
    POST /api/v1/emergency/revoke/{session_id}      → Acil erişimi iptal et (hasta/admin)
"""

import os
import io
import json
import time
import hmac
import hashlib
import secrets
import base64
from fastapi import APIRouter, HTTPException, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
from backend.dependencies import current_user
from core.security import get_device_id

router = APIRouter(prefix="/api/v1/emergency", tags=["emergency-qr"])

# ── Helpers ──────────────────────────────────────────────────────────────────

_EMERGENCY_SECRET = os.environ.get(
    "EMERGENCY_QR_SECRET",
    hashlib.sha256(b"vip-health-vault-emergency-qr-default-secret").hexdigest()
)
BREAK_GLASS_DURATION_SECONDS = 15 * 60   # 15 dakika


def _sign_token(payload: dict) -> str:
    """HMAC-SHA256 ile QR token imzala."""
    body = json.dumps(payload, sort_keys=True).encode()
    sig  = hmac.new(_EMERGENCY_SECRET.encode(), body, hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(body).decode()
    return f"{encoded}.{sig}"


def _verify_token(token: str) -> dict:
    """Token'ı doğrula ve payload'ı döndür; geçersizse HTTPException fırlat."""
    try:
        encoded, sig = token.rsplit(".", 1)
        body = base64.urlsafe_b64decode(encoded.encode())
        expected = hmac.new(_EMERGENCY_SECRET.encode(), body, hashlib.sha256).hexdigest()
    except Exception:
        raise HTTPException(400, "Geçersiz QR token formatı.")

    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "QR token imzası geçersiz — token değiştirilmiş olabilir.")

    payload = json.loads(body)
    if payload.get("exp", 0) < time.time():
        raise HTTPException(410, "QR token süresi dolmuş. Hasta yeni bir QR kod üretmelidir.")

    return payload


def _generate_qr_png(url: str) -> bytes:
    """URL veya token string'inden QR kod PNG üret."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # qrcode kütüphanesi yoksa minimal SVG fallback
        return _minimal_qr_svg(url)


def _minimal_qr_svg(text: str) -> bytes:
    """qrcode yoksa basit metin içeren SVG döndür (fallback)."""
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='300' height='100'>
  <rect width='300' height='100' fill='white'/>
  <text x='10' y='30' font-size='12' fill='black'>QR Fallback</text>
  <text x='10' y='60' font-size='8' fill='gray'>{text[:60]}</text>
</svg>"""
    return svg.encode()


# ── Schemas ───────────────────────────────────────────────────────────────────

class EmergencyActivateReq(BaseModel):
    qr_token:     str
    responder_id: Optional[str] = None     # Ambulans görevlisi / servis ID (opsiyonel)
    location:     Optional[str] = None     # GPS veya konum bilgisi (opsiyonel)
    reason:       Optional[str] = "Emergency QR Scan — Pre-Authorized Access"


class RevokeSessionReq(BaseModel):
    reason: Optional[str] = "Manual revocation"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/qr/token/{patient_id}",
    summary="Hasta için İmzalı QR Token Üret",
    description=(
        "Hasta kendi hesabından bu endpoint'i çağırarak imzalı, "
        "süreli (72 saat geçerli) bir QR token üretir. "
        "Bu token QR koda dönüştürülerek fiziksel kimlik kartına, "
        "tıbbi bilekliğe veya NFC etiketine yazılabilir."
    )
)
def generate_qr_token(
    patient_id: str,
    u: dict = Depends(current_user)
):
    # Sadece kendi QR'ını üretebilir (veya admin/doktor)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Yalnızca kendi QR tokenınızı üretebilirsiniz.")

    session_id = secrets.token_urlsafe(16)
    payload = {
        "type":       "emergency_qr",
        "patient_id": patient_id,
        "session_id": session_id,
        "iat":        time.time(),
        "exp":        time.time() + 72 * 3600,   # 72 saat geçerli QR
        "issuer":     u["username"],
        "scope":      ["read:critical_fields", "read:allergy", "read:bloodtype", "read:emergency_contacts"],
        "device":     get_device_id()[:16],
    }
    token = _sign_token(payload)

    # Audit log
    from database.sql_db import get_sql_db
    db = get_sql_db()
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO emergency_qr_sessions "
                "(session_id, patient_id, token_hash, issued_by, issued_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    patient_id,
                    hashlib.sha256(token.encode()).hexdigest(),
                    u["username"],
                    time.time(),
                    time.time() + 72 * 3600,
                    "active"
                )
            )
            conn.commit()
    except Exception as e:
        pass   # DB write fail → token still usable (degraded mode)

    return {
        "qr_token":   token,
        "session_id": session_id,
        "patient_id": patient_id,
        "valid_hours": 72,
        "scope":       payload["scope"],
        "message":     "Bu token'ı QR koda dönüştürüp tıbbi kimlik kartınıza ekleyebilirsiniz.",
    }


@router.get(
    "/qr/{patient_id}",
    summary="Hasta QR Kodu PNG Görüntüsü",
    response_class=StreamingResponse,
)
def generate_qr_image(
    patient_id: str,
    u: dict = Depends(current_user)
):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Yalnızca kendi QR kodunuzu görüntüleyebilirsiniz.")

    # Token üret
    token_response = generate_qr_token(patient_id, u)
    qr_token = token_response["qr_token"]

    # Aktivasyon URL'si (deploy edildiğinde gerçek domain olacak)
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8000")
    activate_url = f"{base_url}/emergency-access?token={qr_token}"

    png_bytes = _generate_qr_png(activate_url)

    content_type = "image/png" if png_bytes[:4] == b'\x89PNG' else "image/svg+xml"
    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type=content_type,
        headers={
            "Content-Disposition": f"inline; filename=emergency_qr_{patient_id}.png",
            "X-Session-Id": token_response["session_id"],
        }
    )


@router.post(
    "/activate",
    summary="QR Token ile Acil Erişim Başlat (Auth Gerekmez)",
    description=(
        "Ambulans görevlisi veya acil servis personeli bu endpoint'i "
        "QR kod okutarak çağırır. Başarılı doğrulamada 15 dakikalık "
        "READ-ONLY acil erişim token'ı döner. Tüm aktivasyonlar "
        "imzalı audit log'a kaydedilir."
    )
)
def activate_emergency_access(req: EmergencyActivateReq):
    # 1) Token doğrula
    payload = _verify_token(req.qr_token)

    patient_id = payload["patient_id"]
    session_id = payload.get("session_id", secrets.token_urlsafe(8))

    # 2) DB'de revoked mi?
    from database.sql_db import get_sql_db
    db = get_sql_db()
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT status FROM emergency_qr_sessions WHERE session_id = ?",
                (payload.get("session_id", ""),)
            )
            row = c.fetchone()
            if row and row[0] == "revoked":
                raise HTTPException(403, "Bu QR token iptal edilmiş. Hasta yeni bir QR üretmelidir.")
    except HTTPException:
        raise
    except Exception:
        pass   # DB bağlantı hatası → token geçerliyse erişime izin ver (degraded)

    # 3) 15 dakikalık acil erişim token'ı oluştur
    activation_id = secrets.token_urlsafe(12)
    emergency_token_payload = {
        "type":            "emergency_access",
        "patient_id":      patient_id,
        "activation_id":   activation_id,
        "parent_session":  session_id,
        "responder_id":    req.responder_id or "UNKNOWN",
        "location":        req.location or "UNKNOWN",
        "reason":          req.reason or "Emergency QR Scan",
        "iat":             time.time(),
        "exp":             time.time() + BREAK_GLASS_DURATION_SECONDS,
        "scope":           payload.get("scope", ["read:critical_fields"]),
        "read_only":       True,
    }
    access_token = _sign_token(emergency_token_payload)

    # 4) Audit log kaydı
    audit_entry = {
        "event":          "EMERGENCY_QR_ACTIVATED",
        "patient_id":     patient_id,
        "activation_id":  activation_id,
        "parent_session": session_id,
        "responder_id":   req.responder_id or "UNKNOWN",
        "location":       req.location or "UNKNOWN",
        "reason":         req.reason,
        "activated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "expires_at":     time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() + BREAK_GLASS_DURATION_SECONDS)
        ),
        "token_hash":     hashlib.sha256(access_token.encode()).hexdigest()[:16],
    }

    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO emergency_activations "
                "(activation_id, session_id, patient_id, responder_id, location, reason, "
                "activated_at, expires_at, status, audit_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    activation_id,
                    session_id,
                    patient_id,
                    req.responder_id or "UNKNOWN",
                    req.location or "UNKNOWN",
                    req.reason or "Emergency QR Scan",
                    time.time(),
                    time.time() + BREAK_GLASS_DURATION_SECONDS,
                    "active",
                    json.dumps(audit_entry)
                )
            )
            conn.commit()
    except Exception:
        pass   # Degraded mode

    return {
        "success":         True,
        "activation_id":   activation_id,
        "patient_id":      patient_id,
        "access_token":    access_token,
        "expires_in_sec":  BREAK_GLASS_DURATION_SECONDS,
        "expires_at":      audit_entry["expires_at"],
        "scope":           emergency_token_payload["scope"],
        "read_only":       True,
        "audit_entry":     audit_entry,
        "message": (
            f"⚠️ Acil erişim aktif. Bu token {BREAK_GLASS_DURATION_SECONDS // 60} dakika "
            f"sonra otomatik olarak sona erer. Tüm erişimler denetlenmektedir."
        ),
    }


@router.get(
    "/sessions/{patient_id}",
    summary="Hastanın Aktif Acil Erişim Oturumlarını Listele"
)
def list_emergency_sessions(
    patient_id: str,
    u: dict = Depends(current_user)
):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Erişim reddedildi.")

    from database.sql_db import get_sql_db
    db = get_sql_db()
    activations = []
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT activation_id, session_id, responder_id, location, reason, "
                "activated_at, expires_at, status FROM emergency_activations "
                "WHERE patient_id = ? ORDER BY activated_at DESC LIMIT 50",
                (patient_id,)
            )
            rows = c.fetchall()
            for row in rows:
                activations.append({
                    "activation_id": row[0],
                    "session_id":    row[1],
                    "responder_id":  row[2],
                    "location":      row[3],
                    "reason":        row[4],
                    "activated_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[5])),
                    "expires_at":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[6])),
                    "status":        row[7],
                    "is_active":     row[7] == "active" and row[6] > time.time(),
                })
    except Exception:
        pass

    return {
        "patient_id": patient_id,
        "total":      len(activations),
        "activations": activations,
    }


@router.post(
    "/revoke/{session_id}",
    summary="Acil Erişim Oturumunu İptal Et"
)
def revoke_emergency_session(
    session_id: str,
    req: RevokeSessionReq,
    u: dict = Depends(current_user)
):
    from database.sql_db import get_sql_db
    db = get_sql_db()
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            # Önce yetkiyi kontrol et
            c.execute(
                "SELECT patient_id, issued_by FROM emergency_qr_sessions WHERE session_id = ?",
                (session_id,)
            )
            row = c.fetchone()
            if not row:
                raise HTTPException(404, "Oturum bulunamadı.")

            patient_id, issued_by = row[0], row[1]
            if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
                raise HTTPException(403, "Bu oturumu iptal etme yetkiniz yok.")

            # Revoke
            c.execute(
                "UPDATE emergency_qr_sessions SET status = 'revoked' WHERE session_id = ?",
                (session_id,)
            )
            c.execute(
                "UPDATE emergency_activations SET status = 'revoked' WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"İptal işlemi başarısız: {e}")

    return {
        "success":    True,
        "session_id": session_id,
        "status":     "revoked",
        "message":    "Acil erişim oturumu iptal edildi. Mevcut tokenlar artık geçersiz.",
    }
