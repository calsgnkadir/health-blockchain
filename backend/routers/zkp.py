"""
backend/routers/zkp.py — ZKP Selective Disclosure API Router
=============================================================

Endpoints:
  POST  /api/v1/zkp/commitment/{patient_id}   - Create Pedersen commitment for a health attribute
  POST  /api/v1/zkp/prove/{patient_id}        - Generate Schnorr ZKP proof from a commitment
  POST  /api/v1/zkp/verify                    - Verify ZKP proof (no auth required — zero knowledge)
  GET   /api/v1/zkp/commitments/{patient_id}  - List patient's on-chain commitments
"""
import json
import time
import hashlib

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.dependencies import current_user
from core.zkp.pedersen import PedersenZKP, ZKPCommitment, ZKPProof
from database.sql_db import default_sql_db

router = APIRouter(prefix="/api/v1/zkp", tags=["zkp"])
_zkp_engine = PedersenZKP()

# ---------------------------------------------------------------------------
# Supported claim types
# ---------------------------------------------------------------------------
CLAIM_TYPES = {
    "has_allergy":    "Alerji Varligi",
    "has_blood_type": "Kan Grubu",
    "has_vaccination":"Asi Durumu",
    "has_condition":  "Tani / Hastalik",
    "had_surgery":    "Ameliyat Gecmisi",
    "age_over":       "Yas Esigi",
}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class CommitmentRequest(BaseModel):
    claim_type: str  = Field(..., description="has_allergy | has_blood_type | has_vaccination | has_condition | had_surgery | age_over")
    claim_label: str = Field(..., min_length=1, max_length=120, description="Orn: Penisilin | A+ | Covid-19 | Diyabet")

class ProveRequest(BaseModel):
    commitment_hex:  str = Field(..., description="Previously generated commitment hex value")
    randomness_hex:  str = Field(..., description="Blinding factor r (secret, stored by patient)")
    claim_type:      str
    claim_label:     str

class VerifyRequest(BaseModel):
    commitment_hex: str
    R_hex:          str
    s_int:          int
    challenge_hex:  str
    claim_type:     str
    claim_label:    str
    proof_id:       Optional[str] = None
    patient_id:     Optional[str] = None


# ---------------------------------------------------------------------------
# Helper — DB access
# ---------------------------------------------------------------------------
def _save_commitment(patient_id: str, claim_type: str, claim_label: str,
                     commitment_hex: str, proof_metadata: dict) -> str:
    conn = default_sql_db.get_connection()
    cursor = conn.cursor()
    rec_id = hashlib.sha256(
        f"{patient_id}{claim_type}{claim_label}{time.time()}".encode()
    ).hexdigest()[:24]
    ph = "%s" if default_sql_db.is_postgres else "?"
    cursor.execute(
        f"""INSERT INTO zkp_commitments
            (id, patient_id, claim_type, claim_label, commitment_hex, proof_metadata_json, created_at)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
        (rec_id, patient_id, claim_type, claim_label,
         commitment_hex, json.dumps(proof_metadata), time.time())
    )
    conn.commit()
    conn.close()
    return rec_id


def _list_commitments(patient_id: str) -> list:
    conn = default_sql_db.get_connection()
    cursor = conn.cursor()
    ph = "%s" if default_sql_db.is_postgres else "?"
    cursor.execute(
        f"SELECT id, claim_type, claim_label, commitment_hex, created_at FROM zkp_commitments WHERE patient_id={ph} ORDER BY created_at DESC",
        (patient_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        else:
            result.append({
                "id": row[0], "claim_type": row[1], "claim_label": row[2],
                "commitment_hex": row[3], "created_at": row[4]
            })
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/commitment/{patient_id}", summary="Create Pedersen Commitment")
def create_commitment(
    patient_id: str,
    req: CommitmentRequest,
    u: dict = Depends(current_user)
):
    """
    VIP hasta, bir saglik ozelligi icin Pedersen commitment olusturur.
    Commitment blockchain'e kayit edilir; gizli r (randomness) yalnizca hastaya dondurulur.
    """
    if u.get("role") not in ("vip_patient", "patient", "admin"):
        raise HTTPException(403, "Yalnizca VIP hasta veya yetkili kullanici commitment olusturabilir.")

    if u.get("role") == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Yalnizca kendi hasta kaydiniiz icin commitment olusturabilirsiniz.")

    if req.claim_type not in CLAIM_TYPES:
        raise HTTPException(400, f"Gecersiz claim_type. Desteklenenler: {list(CLAIM_TYPES.keys())}")

    comm = _zkp_engine.commit(patient_id, req.claim_type, req.claim_label)
    proof = _zkp_engine.prove(comm)

    rec_id = _save_commitment(
        patient_id, req.claim_type, req.claim_label,
        comm.commitment_hex,
        {
            "proof_id": proof.proof_id,
            "R_hex": proof.R_hex,
            "s_int": proof.s_int,
            "challenge_hex": proof.challenge_hex,
        }
    )

    return {
        "success": True,
        "record_id": rec_id,
        "message": "Commitment blockchain'e kaydedildi. Asagidaki gizli bilgileri guvenli bir yerde saklayiniz.",
        "commitment": comm.public_dict(),
        # Returned to patient ONLY — never stored server-side in plaintext long-term
        "secret": {
            "randomness_hex": comm.randomness_hex,
            "IMPORTANT": "Bu bilgiyi guvenli bir yerde saklayin. Sunucuda saklanmaz."
        },
        "proof": proof.to_dict(),
    }


@router.post("/prove/{patient_id}", summary="Generate ZKP Proof")
def generate_proof(
    patient_id: str,
    req: ProveRequest,
    u: dict = Depends(current_user)
):
    """
    Hasta, daha onceden olusturulmus bir commitment icin ZKP kaniti uretir.
    Bu kanit, ham veriyi aciklamadan dogrulama yapmak icin kullanilir.
    """
    if u.get("role") not in ("vip_patient", "patient", "admin"):
        raise HTTPException(403, "Yalnizca VIP hasta veya yetkili kullanici kanit uretebilir.")

    if u.get("role") == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Yalnizca kendi hasta kaydiniiz icin kanit uretebilirsiniz.")

    if req.claim_type not in CLAIM_TYPES:
        raise HTTPException(400, f"Gecersiz claim_type. Desteklenenler: {list(CLAIM_TYPES.keys())}")

    try:
        comm = ZKPCommitment(
            patient_id=patient_id,
            claim_type=req.claim_type,
            claim_label=req.claim_label,
            commitment_hex=req.commitment_hex,
            randomness_hex=req.randomness_hex,
            value_int=0,  # will be recomputed by engine
            created_at=time.time(),
        )
        # Recompute value_int from deterministic function
        from core.zkp.pedersen import _field_to_int
        comm.value_int = _field_to_int(f"{req.claim_type}:{req.claim_label}")

        proof = _zkp_engine.prove(comm)
    except Exception as e:
        raise HTTPException(400, f"Kanit uretimi basarisiz: {str(e)}")

    return {
        "success": True,
        "message": "ZKP kaniti basariyla uretildi. Bu kaniti doktorunuzla paylasabilirsiniz.",
        "proof": proof.to_dict(),
        "verify_url": "/api/v1/zkp/verify",
        "instructions": "Kanit'i /api/v1/zkp/verify endpoint'ine POST ederek dogrulatabilirsiniz.",
    }


@router.post("/verify", summary="Verify ZKP Proof (No Auth Required)")
def verify_proof(req: VerifyRequest):
    """
    Bir ZKP kanitini dogrular. Kimlik dogrulama gerektirmez.
    Doktor ya da herhangi bir taraf ham veriyi gormeden kaniti dogrulayabilir.
    """
    proof = ZKPProof(
        patient_id=req.patient_id or "anonymous",
        claim_type=req.claim_type,
        claim_label=req.claim_label,
        commitment_hex=req.commitment_hex,
        R_hex=req.R_hex,
        s_int=req.s_int,
        challenge_hex=req.challenge_hex,
        proof_id=req.proof_id or "manual-verify",
        created_at=time.time(),
    )

    is_valid = _zkp_engine.verify_proof(proof)

    if is_valid:
        return {
            "verified": True,
            "claim_type": req.claim_type,
            "claim_label": req.claim_label,
            "message": f"✓ DOGRULANDI: Hasta, '{CLAIM_TYPES.get(req.claim_type, req.claim_type)} — {req.claim_label}' ozelligi icin gecerli bir ZKP kaniti sunmaktadir.",
            "cryptographic_guarantee": "Pedersen Commitment + Schnorr Fiat-Shamir ZKP (RFC3526 Group14 2048-bit)",
            "raw_data_exposed": False,
        }
    else:
        return {
            "verified": False,
            "claim_type": req.claim_type,
            "claim_label": req.claim_label,
            "message": f"✗ DOGRULANAMADI: Kanit gecersiz veya manipule edilmis.",
            "raw_data_exposed": False,
        }


@router.get("/commitments/{patient_id}", summary="List Patient ZKP Commitments")
def list_commitments(
    patient_id: str,
    u: dict = Depends(current_user)
):
    """
    Hasta icin blockchain'e kaydedilmis ZKP commitment listesini getirir.
    """
    role = u.get("role")
    if role == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Yalnizca kendi commitment listenizi gorebilirsiniz.")
    if role not in ("vip_patient", "patient", "doctor", "admin"):
        raise HTTPException(403, "Erisim reddedildi.")

    commitments = _list_commitments(patient_id)
    return {
        "patient_id": patient_id,
        "total": len(commitments),
        "commitments": commitments,
        "supported_claim_types": CLAIM_TYPES,
    }
