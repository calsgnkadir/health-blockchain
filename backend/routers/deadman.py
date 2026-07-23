"""
backend/routers/deadman.py — Dead-Man's Switch (Miras Kilidi) Router (Seviye 3)
================================================================================

Hastanın belirlenen inaktivite süresi (örn. 30, 90, 180 gün) boyunca sisteme 
giriş yapmaması veya "Hayattayım" (Heartbeat Ping) sinyali vermemesi durumunda 
otomatik olarak tetiklenen miras/vasi erişim sistemidir.

Tetiklendiğinde, hastanın önceden yetkilendirdiği varisler/koruyucular 
(beneficiaries) hastanın tıbbi geçmişine erişim hakkı kazanır.

Endpoints:
    GET  /api/v1/deadman/config/{patient_id}          → Miras kilidi durum ve yapılandırmasını getir
    POST /api/v1/deadman/config                       → Miras kilidi parametrelerini ayarla/güncelle
    POST /api/v1/deadman/ping                         → Heartbeat sinyali gönder (süreyi sıfırla)
    POST /api/v1/deadman/toggle                       → Miras kilidini dondur / tekrar aktif et
    GET  /api/v1/deadman/beneficiary-access/{patient_id} → Tetiklenmişse varis için verileri getir
"""

import json
import time
import secrets
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.dependencies import current_user
from database.sql_db import get_sql_db
from backend.middleware.xss_protection import strip_dangerous_xss_tags

router = APIRouter(prefix="/api/v1/deadman", tags=["deadman-switch"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class BeneficiaryItem(BaseModel):
    username: str
    relation: str = "Guardian / Heir"
    email: Optional[str] = None
    access_scope: str = "all_records"  # all_records, emergency_only, summary_only


class DeadManConfigReq(BaseModel):
    inactivity_days: int = Field(default=90, ge=1, le=365)
    beneficiaries: List[BeneficiaryItem] = Field(default_factory=list)


class ToggleReq(BaseModel):
    status: str  # active, paused


# ── Helpers ──────────────────────────────────────────────────────────────────

def _log_deadman_event(patient_id: str, event_type: str, details: dict):
    """Miras kilidi olaylarını loglar."""
    db = get_sql_db()
    log_id = f"dmlog_{secrets.token_hex(8)}"
    now = time.time()
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO deadman_logs (log_id, patient_id, event_type, timestamp, details_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (log_id, patient_id, event_type, now, json.dumps(details))
            )
            conn.commit()
    except Exception:
        pass


def _evaluate_and_get_config(patient_id: str) -> dict:
    """DB'den config çeker, inaktivite süresi dolmuşsa status'ü 'triggered' yapar."""
    db = get_sql_db()
    now = time.time()
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT patient_id, inactivity_days, last_heartbeat, status, beneficiaries_json, created_at, updated_at "
            "FROM deadman_configs WHERE patient_id = ?",
            (patient_id,)
        )
        row = c.fetchone()
        if not row:
            return None

        cfg = {
            "patient_id": row[0],
            "inactivity_days": row[1],
            "last_heartbeat": row[2],
            "status": row[3],
            "beneficiaries": json.loads(row[4]) if row[4] else [],
            "created_at": row[5],
            "updated_at": row[6],
        }

        # Threshold kontrolü
        inactivity_limit_sec = cfg["inactivity_days"] * 86400
        elapsed_sec = now - cfg["last_heartbeat"]

        if cfg["status"] == "active" and elapsed_sec > inactivity_limit_sec:
            # Status'ü 'triggered' olarak güncelle
            c.execute(
                "UPDATE deadman_configs SET status = 'triggered', updated_at = ? WHERE patient_id = ?",
                (now, patient_id)
            )
            conn.commit()
            cfg["status"] = "triggered"
            cfg["updated_at"] = now
            _log_deadman_event(patient_id, "SWITCH_TRIGGERED", {
                "inactivity_days": cfg["inactivity_days"],
                "elapsed_days": round(elapsed_sec / 86400, 1),
                "triggered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
            })

        # Kalan gün hesabı
        cfg["elapsed_days"] = round(elapsed_sec / 86400, 1)
        cfg["remaining_days"] = max(0, round((inactivity_limit_sec - elapsed_sec) / 86400, 1))
        cfg["is_triggered"] = (cfg["status"] == "triggered")
        return cfg


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/config/{patient_id}",
    summary="Miras Kilidi Durumunu Getir"
)
def get_deadman_config(
    patient_id: str,
    u: dict = Depends(current_user)
):
    # İzin kontrolü: Hasta kendisi, Admin, ya da kayıtlı varis bakabilir
    cfg = _evaluate_and_get_config(patient_id)
    if not cfg:
        # Varsayılan boş config
        return {
            "configured": False,
            "patient_id": patient_id,
            "status": "not_configured",
            "inactivity_days": 90,
            "beneficiaries": [],
            "message": "Henüz miras kilidi yapılandırılmamış."
        }

    is_owner = (u["role"] in ("vip_patient", "patient") and (u.get("patient_id") == patient_id or u.get("username") == patient_id))
    is_admin = u.get("role") == "admin"
    is_beneficiary = any(b.get("username") == u["username"] for b in cfg.get("beneficiaries", []))

    if not (is_owner or is_admin or is_beneficiary):
        raise HTTPException(403, "Bu hastanın miras kilidi durumunu görüntüleme yetkiniz yok.")

    cfg["configured"] = True
    return cfg


@router.post(
    "/config",
    summary="Miras Kilidini Yapılandır / Güncelle"
)
def configure_deadman_switch(
    req: DeadManConfigReq,
    u: dict = Depends(current_user)
):
    if u.get("role") not in ("vip_patient", "patient", "admin"):
        raise HTTPException(403, "Yalnızca hastalar veya yetkili sistem yöneticisi miras kilidi yapılandırabilir.")

    patient_id = u.get("patient_id") or u["username"]
    now = time.time()

    # Beneficiary verilerini sanitize et
    clean_beneficiaries = []
    for b in req.beneficiaries:
        clean_beneficiaries.append({
            "username": strip_dangerous_xss_tags(b.username),
            "relation": strip_dangerous_xss_tags(b.relation),
            "email": strip_dangerous_xss_tags(b.email) if b.email else None,
            "access_scope": b.access_scope
        })

    b_json = json.dumps(clean_beneficiaries)
    db = get_sql_db()

    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT patient_id FROM deadman_configs WHERE patient_id = ?",
            (patient_id,)
        )
        exists = c.fetchone()

        if exists:
            c.execute(
                "UPDATE deadman_configs SET inactivity_days = ?, last_heartbeat = ?, "
                "status = 'active', beneficiaries_json = ?, updated_at = ? WHERE patient_id = ?",
                (req.inactivity_days, now, b_json, now, patient_id)
            )
        else:
            c.execute(
                "INSERT INTO deadman_configs (patient_id, inactivity_days, last_heartbeat, status, beneficiaries_json, created_at, updated_at) "
                "VALUES (?, ?, ?, 'active', ?, ?, ?)",
                (patient_id, req.inactivity_days, now, b_json, now, now)
            )
        conn.commit()

    _log_deadman_event(patient_id, "CONFIG_UPDATED", {
        "inactivity_days": req.inactivity_days,
        "beneficiaries_count": len(clean_beneficiaries)
    })

    return {
        "success": True,
        "patient_id": patient_id,
        "inactivity_days": req.inactivity_days,
        "status": "active",
        "last_heartbeat": now,
        "message": f"Miras kilidi {req.inactivity_days} günlük inaktivite eşiği ile aktif edildi."
    }


@router.post(
    "/ping",
    summary="Heartbeat Sinyali Gönder ('Ben Hayattayım')"
)
def heartbeat_ping(
    u: dict = Depends(current_user)
):
    if u["role"] not in ("vip_patient", "patient"):
        raise HTTPException(403, "Yalnızca hasta hesapları heartbeat sinyali gönderebilir.")

    patient_id = u.get("patient_id") or u["username"]
    now = time.time()
    db = get_sql_db()

    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT status FROM deadman_configs WHERE patient_id = ?",
            (patient_id,)
        )
        row = c.fetchone()
        if not row:
            # Otomatik varsayılan 90 gün ile oluştur
            c.execute(
                "INSERT INTO deadman_configs (patient_id, inactivity_days, last_heartbeat, status, beneficiaries_json, created_at, updated_at) "
                "VALUES (?, 90, ?, 'active', '[]', ?, ?)",
                (patient_id, now, now, now)
            )
        else:
            # Eğer önceden 'triggered' olduysa ve hasta yeniden giriş yapıp ping attıysa status'ü 'active'e döndür
            c.execute(
                "UPDATE deadman_configs SET last_heartbeat = ?, status = 'active', updated_at = ? WHERE patient_id = ?",
                (now, now, patient_id)
            )
        conn.commit()

    _log_deadman_event(patient_id, "HEARTBEAT_PING", {
        "timestamp": now,
        "ping_by": u["username"]
    })

    return {
        "success": True,
        "patient_id": patient_id,
        "last_heartbeat": now,
        "status": "active",
        "message": "Heartbeat sinyali alındı. Miras kilidi süresi sıfırlandı."
    }


@router.post(
    "/toggle",
    summary="Miras Kilidini Dondur veya Tekrar Aktif Et"
)
def toggle_deadman_switch(
    req: ToggleReq,
    u: dict = Depends(current_user)
):
    if u["role"] not in ("vip_patient", "patient", "admin"):
        raise HTTPException(403, "Yetkisiz erişim.")

    if req.status not in ["active", "paused"]:
        raise HTTPException(400, "Durum yalnızca 'active' veya 'paused' olabilir.")

    patient_id = u.get("patient_id") or u["username"]
    now = time.time()
    db = get_sql_db()

    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE deadman_configs SET status = ?, updated_at = ? WHERE patient_id = ?",
            (req.status, now, patient_id)
        )
        conn.commit()

    _log_deadman_event(patient_id, f"SWITCH_{req.status.upper()}", {"by": u["username"]})

    return {
        "success": True,
        "patient_id": patient_id,
        "status": req.status,
        "message": f"Miras kilidi durumu '{req.status}' olarak güncellendi."
    }


@router.get(
    "/beneficiary-access/{patient_id}",
    summary="Mirasçı Tıbbi Kayıt Erişimi"
)
def beneficiary_access_records(
    patient_id: str,
    u: dict = Depends(current_user)
):
    cfg = _evaluate_and_get_config(patient_id)
    if not cfg:
        raise HTTPException(404, "Miras kilidi yapılandırılmamış.")

    # Status kontrolü: 'triggered' olmalı
    if cfg["status"] != "triggered":
        raise HTTPException(403, f"Miras kilidi henüz tetiklenmedi (Mevcut durum: {cfg['status']}). Hasta aktif olarak sisteme erişmektedir.")

    # Varis / Guardian yetki kontrolü
    user_beneficiary_info = None
    for b in cfg.get("beneficiaries", []):
        if b.get("username") == u["username"]:
            user_beneficiary_info = b
            break

    if not user_beneficiary_info and u.get("role") != "admin":
        raise HTTPException(403, "Bu hastanın miras listesinde adınız yer almamaktadır.")

    scope = user_beneficiary_info.get("access_scope", "all_records") if user_beneficiary_info else "all_records"

    # Kayıtları LMDB / SQL üzerinden çek
    from backend.dependencies import get_db_manager
    from database.connection import LMDBConnectionManager
    import database.storage as storage

    db_mgr = get_db_manager()
    project_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"

    records = []
    if db_mgr.project_exists(project_name):
        env = db_mgr.open_db(project_name)
        with env.begin(write=False) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if key.startswith(b"rec_"):
                    try:
                        rdata = json.loads(value.decode("utf-8"))
                        if scope == "emergency_only" and rdata.get("record_type") not in ["emergency", "vital_signs", "allergy"]:
                            continue
                        records.append(rdata)
                    except Exception:
                        continue

    _log_deadman_event(patient_id, "BENEFICIARY_ACCESS", {
        "accessed_by": u["username"],
        "scope": scope,
        "records_count": len(records)
    })

    return {
        "patient_id": patient_id,
        "beneficiary": u["username"],
        "access_scope": scope,
        "switch_status": "triggered",
        "unlocked_records": records,
        "message": f"Miras kilidi tetiklendiği için {len(records)} adet tıbbi kayıt erişime açılmıştır."
    }
