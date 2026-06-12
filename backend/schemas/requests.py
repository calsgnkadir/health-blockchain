import re
import html
from datetime import datetime
from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Any

RECORD_TYPES = {
    "diagnosis":     "Diagnosis",
    "lab_result":    "Lab Result",
    "prescription":  "Prescription",
    "surgery":       "Surgery",
    "vaccination":   "Vaccination",
    "imaging":       "Imaging (MRI/CT/X-Ray)",
    "vital_signs":   "Vital Signs",
    "allergy":       "Allergy",
    "psychology":    "Psychology",
    "genetic":       "Genetics",
    "emergency":     "Emergency",
    "other":         "Other",
}

ACCESS_LEVELS = {
    "private":        "Patient Only",
    "doctor_shared":  "Patient + Doctor",
    "emergency":      "Emergency Access",
    "admin_only":     "Administrator Only",
}

def sanitize_html(v: str) -> str:
    """Helper to escape HTML characters and prevent XSS."""
    if isinstance(v, str):
        return html.escape(v.strip())
    return v

def validate_iso_date(v: str) -> str:
    """Helper to validate ISO 8601 date format."""
    if not isinstance(v, str):
        raise ValueError("Date must be a string")
    
    # Try YYYY-MM-DD
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return v
    except ValueError:
        pass
    
    # Try full ISO datetime
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v
    except ValueError:
        raise ValueError("Date must be in ISO 8601 format (e.g., YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")


# ── LOGIN SCHEMAS ───────────────────────────────────────────
class LoginReq(BaseModel):
    username: str
    password: str
    code: Optional[str] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\.\-]{3,50}$", v):
            raise ValueError("Username must contain only alphanumeric characters, underscores, dots, or hyphens.")
        return v


# ── USER CREATION SCHEMAS ───────────────────────────────────
class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    full_name: str
    patient_id: Optional[str] = None
    specialty: Optional[str] = None
    institution: Optional[str] = None

    @field_validator("full_name", "institution", "specialty")
    @classmethod
    def sanitize_fields(cls, v):
        return sanitize_html(v)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        from core.security import validate_password
        valid, msg = validate_password(v)
        if not valid:
            raise ValueError(msg)
        return v

    @field_validator("role")
    @classmethod
    def valid_role(cls, v):
        allowed = {"admin", "doctor", "vip_patient", "nurse", "auditor"}
        if v not in allowed:
            raise ValueError(f"Invalid role. Allowed roles: {allowed}")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\.\-]{3,50}$", v):
            raise ValueError("Username must be between 3 and 50 characters and contain only alphanumeric characters, underscores, dots, or hyphens.")
        return v

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v):
        if v is not None:
            if not re.match(r"^[a-zA-Z0-9_\-]{3,50}$", v):
                raise ValueError("Patient ID must be between 3 and 50 characters and contain only alphanumeric characters, underscores, or hyphens.")
        return v


# ── 2FA & SECURITY SCHEMAS ──────────────────────────────────
class Verify2FAReq(BaseModel):
    code: str


# ── CONSENT SCHEMAS ─────────────────────────────────────────
class ConsentReq(BaseModel):
    patient_id: str
    doctor_username: str
    record_type: str
    duration_days: int

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("patient_id must contain only alphanumeric characters, underscores, and hyphens.")
        return v

    @field_validator("doctor_username")
    @classmethod
    def validate_doctor_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", v):
            raise ValueError("doctor_username must contain only alphanumeric characters, underscores, hyphens, and dots.")
        return v

    @field_validator("duration_days")
    @classmethod
    def validate_duration(cls, v):
        if v <= 0:
            raise ValueError("duration_days must be positive")
        return v


class BreakGlassReq(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def sanitize_reason(cls, v):
        return sanitize_html(v)


# ── HEALTH RECORD SCHEMAS ───────────────────────────────────
class RecordCreate(BaseModel):
    patient_id:      str
    record_type:     str
    title:           str
    doctor_name:     str
    institution:     str
    record_date:     str
    access_level:    str = "doctor_shared"
    is_confidential: bool = False
    confidential_password: Optional[str] = None
    data:            Dict[str, Any]
    notes:           Optional[str] = None
    file_name:       Optional[str] = None
    file_type:       Optional[str] = None
    file_data:       Optional[str] = None

    @field_validator("doctor_name", "institution", "title", "notes")
    @classmethod
    def sanitize_fields(cls, v):
        return sanitize_html(v)

    @field_validator("record_date")
    @classmethod
    def check_record_date(cls, v):
        return validate_iso_date(v)

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("patient_id must contain only alphanumeric characters, underscores, and hyphens.")
        return v

    @field_validator("record_type")
    @classmethod
    def valid_record_type(cls, v):
        if v not in RECORD_TYPES:
            raise ValueError(f"Invalid record type: {v}")
        return v

    @field_validator("access_level")
    @classmethod
    def valid_access_level(cls, v):
        if v not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access level: {v}")
        return v

    @field_validator("file_data")
    @classmethod
    def file_data_size(cls, v):
        if v is not None:
            max_len = int(2 * 1024 * 1024 * 4 / 3)
            if len(v) > max_len:
                raise ValueError("Attachment size exceeds the 2MB limit")
        return v


class DecryptRequest(BaseModel):
    password: str
    block_index: int

    @field_validator("block_index")
    @classmethod
    def validate_block_index(cls, v):
        if v < 0:
            raise ValueError("block_index must be a non-negative integer.")
        return v


# ── DATA SCHEMAS FOR RECORD TYPES ───────────────────────────
class VitalSignsSchema(BaseModel):
    blood_pressure: str
    heart_rate: int
    temperature: float
    oxygen_sat: int

    @field_validator("blood_pressure")
    @classmethod
    def check_bp(cls, v):
        if not re.match(r"^\d{2,3}/\d{2,3}$", v.strip()):
            raise ValueError("Blood pressure must be in format SYS/DIA (e.g. 120/80)")
        return sanitize_html(v)

    @field_validator("heart_rate")
    @classmethod
    def check_heart_rate(cls, v):
        if not (1 <= v <= 300):
            raise ValueError("Heart rate must be between 1 and 300 bpm")
        return v

    @field_validator("temperature")
    @classmethod
    def check_temp(cls, v):
        if not (30.0 <= v <= 45.0):
            raise ValueError("Temperature must be between 30.0°C and 45.0°C")
        return v

    @field_validator("oxygen_sat")
    @classmethod
    def check_spo2(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("SpO2 oxygen saturation must be between 0% and 100%")
        return v


class AllergySchema(BaseModel):
    allergen: str
    reaction: str
    severity: str
    onset_date: str

    @field_validator("allergen", "reaction")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)

    @field_validator("onset_date")
    @classmethod
    def check_onset_date(cls, v):
        return validate_iso_date(v)

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v):
        allowed = {"Mild", "Moderate", "Severe"}
        if v not in allowed:
            raise ValueError(f"Severity must be one of {allowed}")
        return v


class PrescriptionSchema(BaseModel):
    medication: str
    dose: str
    frequency: str
    duration: int

    @field_validator("medication", "dose", "frequency")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)

    @field_validator("duration")
    @classmethod
    def check_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be a positive number of days")
        return v


class VaccinationSchema(BaseModel):
    vaccine_name: str
    lot_number: str
    dose_number: int
    next_dose: Optional[str] = None

    @field_validator("vaccine_name", "lot_number")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)

    @field_validator("next_dose")
    @classmethod
    def check_next_dose(cls, v):
        if v is not None:
            return validate_iso_date(v)
        return v

    @field_validator("dose_number")
    @classmethod
    def check_dose(cls, v):
        if v <= 0:
            raise ValueError("Dose number must be a positive integer")
        return v


class LabResultSchema(BaseModel):
    test_name: str
    result_value: str
    reference_range: str
    unit: str

    @field_validator("test_name", "result_value", "reference_range", "unit")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)


class DiagnosisSchema(BaseModel):
    icd_code: str
    severity: str
    symptoms: str

    @field_validator("icd_code", "severity", "symptoms")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)


class SurgerySchema(BaseModel):
    procedure: str
    anesthesia: str
    duration_min: int
    outcome: str

    @field_validator("procedure", "anesthesia", "outcome")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)

    @field_validator("duration_min")
    @classmethod
    def check_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be a positive number of minutes")
        return v


class ImagingSchema(BaseModel):
    modality: str
    body_part: str
    findings: str
    radiologist: str

    @field_validator("modality", "body_part", "findings", "radiologist")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)


# ── APPOINTMENT SCHEMAS ──────────────────────────────────────
class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_name: str
    department: str
    appointment_date: str
    appointment_time: str
    notes: Optional[str] = ""

    @field_validator("doctor_name", "department", "notes")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)

    @field_validator("appointment_date")
    @classmethod
    def check_app_date(cls, v):
        return validate_iso_date(v)


class TriageRequest(BaseModel):
    symptoms: str
    duration_days: int

    @field_validator("symptoms")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)


class LisWebhookPayload(BaseModel):
    patient_id: str
    doctor_name: str
    institution: str
    title: str
    test_name: str
    result_value: str
    reference_range: str
    unit: str
    notes: Optional[str] = ""

    @field_validator("doctor_name", "institution", "title", "test_name", "result_value", "reference_range", "unit", "notes")
    @classmethod
    def sanitize_strings(cls, v):
        return sanitize_html(v)
