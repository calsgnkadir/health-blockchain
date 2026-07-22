import uuid
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

# ── COMMON FHIR ELEMENTS ──────────────────────────────────────────
class Coding(BaseModel):
    system: Optional[str] = None
    version: Optional[str] = None
    code: Optional[str] = None
    display: Optional[str] = None
    userSelected: Optional[bool] = None

class CodeableConcept(BaseModel):
    coding: Optional[List[Coding]] = None
    text: Optional[str] = None

class Reference(BaseModel):
    reference: Optional[str] = None
    type: Optional[str] = None
    display: Optional[str] = None

class Quantity(BaseModel):
    value: Optional[float] = None
    comparator: Optional[str] = None
    unit: Optional[str] = None
    system: Optional[str] = None
    code: Optional[str] = None

class ReferenceRange(BaseModel):
    low: Optional[Quantity] = None
    high: Optional[Quantity] = None
    type: Optional[CodeableConcept] = None
    text: Optional[str] = None

# ── OBSERVATION COMPONENT ──────────────────────────────────────────
class ObservationComponent(BaseModel):
    code: CodeableConcept
    valueQuantity: Optional[Quantity] = None
    valueCodeableConcept: Optional[CodeableConcept] = None
    valueString: Optional[str] = None
    valueBoolean: Optional[bool] = None
    valueInteger: Optional[int] = None

# ── OBSERVATION RESOURCE (LOINC Codes for Vitals & Lab) ─────────────
class Observation(BaseModel):
    resourceType: Literal["Observation"] = "Observation"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "final"
    category: Optional[List[CodeableConcept]] = None
    code: CodeableConcept
    subject: Reference
    effectiveDateTime: Optional[str] = None
    valueQuantity: Optional[Quantity] = None
    valueCodeableConcept: Optional[CodeableConcept] = None
    valueString: Optional[str] = None
    valueBoolean: Optional[bool] = None
    valueInteger: Optional[int] = None
    referenceRange: Optional[List[ReferenceRange]] = None
    component: Optional[List[ObservationComponent]] = None

# ── CONDITION RESOURCE (Diagnosis) ──────────────────────────────────
class Condition(BaseModel):
    resourceType: Literal["Condition"] = "Condition"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    clinicalStatus: Optional[CodeableConcept] = None
    verificationStatus: Optional[CodeableConcept] = None
    category: Optional[List[CodeableConcept]] = None
    severity: Optional[CodeableConcept] = None
    code: CodeableConcept
    subject: Reference
    recordedDate: Optional[str] = None

# ── DOSAGE & MEDICATIONREQUEST (Prescription) ───────────────────────
class DoseAndRate(BaseModel):
    doseQuantity: Optional[Quantity] = None

class TimingRepeat(BaseModel):
    duration: Optional[float] = None
    durationUnit: Optional[str] = "d"

class Timing(BaseModel):
    repeat: Optional[TimingRepeat] = None

class Dosage(BaseModel):
    text: Optional[str] = None
    timing: Optional[Timing] = None
    doseAndRate: Optional[List[DoseAndRate]] = None

class MedicationRequest(BaseModel):
    resourceType: Literal["MedicationRequest"] = "MedicationRequest"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "active"
    intent: str = "order"
    medicationCodeableConcept: CodeableConcept
    subject: Reference
    authoredOn: Optional[str] = None
    dosageInstruction: Optional[List[Dosage]] = None


# ── ADAPTERS (CONVERSION FUNCTIONS) ──────────────────────────────────

def convert_vital_signs_to_fhir(patient_id: str, record_date: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a flat VitalSigns schema to FHIR R4 Observation resource dictionary.
    Flat keys: blood_pressure ("SYS/DIA"), heart_rate, temperature, oxygen_sat
    """
    bp_str = data.get("blood_pressure", "").strip()
    hr_val = data.get("heart_rate")
    temp_val = data.get("temperature")
    spo2_val = data.get("oxygen_sat")

    components = []

    # Parse Blood Pressure into Systolic and Diastolic components
    if bp_str and "/" in bp_str:
        try:
            sys_val, dia_val = bp_str.split("/", 1)
            sys_float = float(sys_val.strip())
            dia_float = float(dia_val.strip())
            
            # Systolic Component (LOINC: 8480-6)
            components.append(ObservationComponent(
                code=CodeableConcept(
                    coding=[Coding(system="http://loinc.org", code="8480-6", display="Systolic blood pressure")]
                ),
                valueQuantity=Quantity(
                    value=sys_float,
                    unit="mmHg",
                    system="http://unitsofmeasure.org",
                    code="mm[Hg]"
                )
            ))
            
            # Diastolic Component (LOINC: 8462-4)
            components.append(ObservationComponent(
                code=CodeableConcept(
                    coding=[Coding(system="http://loinc.org", code="8462-4", display="Diastolic blood pressure")]
                ),
                valueQuantity=Quantity(
                    value=dia_float,
                    unit="mmHg",
                    system="http://unitsofmeasure.org",
                    code="mm[Hg]"
                )
            ))
        except Exception:
            pass

    # Heart Rate (LOINC: 8867-4)
    if hr_val is not None:
        components.append(ObservationComponent(
            code=CodeableConcept(
                coding=[Coding(system="http://loinc.org", code="8867-4", display="Heart rate")]
            ),
            valueQuantity=Quantity(
                value=float(hr_val),
                unit="/min",
                system="http://unitsofmeasure.org",
                code="/min"
            )
        ))

    # Temperature (LOINC: 8310-5)
    if temp_val is not None:
        components.append(ObservationComponent(
            code=CodeableConcept(
                coding=[Coding(system="http://loinc.org", code="8310-5", display="Body temperature")]
            ),
            valueQuantity=Quantity(
                value=float(temp_val),
                unit="Cel",
                system="http://unitsofmeasure.org",
                code="Cel"
            )
        ))

    # Oxygen Saturation (LOINC: 2708-6)
    if spo2_val is not None:
        components.append(ObservationComponent(
            code=CodeableConcept(
                coding=[Coding(system="http://loinc.org", code="2708-6", display="Oxygen saturation in Arterial blood")]
            ),
            valueQuantity=Quantity(
                value=float(spo2_val),
                unit="%",
                system="http://unitsofmeasure.org",
                code="%"
            )
        ))

    obs = Observation(
        status="final",
        category=[
            CodeableConcept(
                coding=[Coding(
                    system="http://terminology.hl7.org/CodeSystem/observation-category",
                    code="vital-signs",
                    display="Vital Signs"
                )]
            )
        ],
        code=CodeableConcept(
            coding=[Coding(system="http://loinc.org", code="85353-1", display="Vital signs panel")]
        ),
        subject=Reference(reference=f"Patient/{patient_id}"),
        effectiveDateTime=record_date,
        component=components
    )
    return obs.model_dump()


def convert_lab_result_to_fhir(patient_id: str, record_date: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a flat LabResult schema to FHIR R4 Observation resource dictionary.
    Flat keys: test_name, result_value, reference_range, unit
    """
    test_name = data.get("test_name", "Laboratory Test")
    result_val = data.get("result_value", "")
    ref_range = data.get("reference_range", "")
    unit = data.get("unit", "")

    value_quantity = None
    value_string = None

    try:
        val_float = float(result_val)
        value_quantity = Quantity(
            value=val_float,
            unit=unit,
            system="http://unitsofmeasure.org",
            code=unit
        )
    except ValueError:
        value_string = result_val

    ranges = []
    if ref_range:
        ranges.append(ReferenceRange(text=ref_range))

    obs = Observation(
        status="final",
        category=[
            CodeableConcept(
                coding=[Coding(
                    system="http://terminology.hl7.org/CodeSystem/observation-category",
                    code="laboratory",
                    display="Laboratory"
                )]
            )
        ],
        code=CodeableConcept(text=test_name),
        subject=Reference(reference=f"Patient/{patient_id}"),
        effectiveDateTime=record_date,
        valueQuantity=value_quantity,
        valueString=value_string,
        referenceRange=ranges if ranges else None
    )
    return obs.model_dump()


def convert_diagnosis_to_fhir(patient_id: str, record_date: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a flat Diagnosis schema to FHIR R4 Condition resource dictionary.
    Flat keys: icd_code, severity, symptoms
    """
    icd_code = data.get("icd_code", "R69")
    severity_str = data.get("severity", "Moderate")
    symptoms = data.get("symptoms", "")

    severity_coding = Coding(
        system="http://terminology.hl7.org/CodeSystem/adverse-event-severity",
        code=severity_str.lower(),
        display=severity_str
    )

    cond = Condition(
        clinicalStatus=CodeableConcept(
            coding=[Coding(
                system="http://terminology.hl7.org/CodeSystem/condition-clinical",
                code="active",
                display="Active"
            )]
        ),
        verificationStatus=CodeableConcept(
            coding=[Coding(
                system="http://terminology.hl7.org/CodeSystem/condition-ver-status",
                code="confirmed",
                display="Confirmed"
            )]
        ),
        category=[
            CodeableConcept(
                coding=[Coding(
                    system="http://terminology.hl7.org/CodeSystem/condition-category",
                    code="encounter-diagnosis",
                    display="Encounter Diagnosis"
                )]
            )
        ],
        severity=CodeableConcept(coding=[severity_coding]),
        code=CodeableConcept(
            coding=[Coding(
                system="http://hl7.org/fhir/sid/icd-10",
                code=icd_code,
                display=symptoms or f"ICD-10 Code {icd_code}"
            )]
        ),
        subject=Reference(reference=f"Patient/{patient_id}"),
        recordedDate=record_date
    )
    return cond.model_dump()


def convert_prescription_to_fhir(patient_id: str, record_date: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a flat Prescription schema to FHIR R4 MedicationRequest resource dictionary.
    Flat keys: medication, dose, frequency, duration
    """
    medication = data.get("medication", "Unknown Medication")
    dose_str = data.get("dose", "")
    freq_str = data.get("frequency", "")
    duration_val = data.get("duration")

    timing = None
    if duration_val is not None:
        try:
            dur_float = float(duration_val)
            timing = Timing(repeat=TimingRepeat(duration=dur_float, durationUnit="d"))
        except ValueError:
            pass

    dose_qty = None
    if dose_str:
        import re
        match = re.match(r"^\s*([0-9\.]+)", dose_str)
        if match:
            try:
                val = float(match.group(1))
                unit = dose_str[match.end():].strip()
                dose_qty = Quantity(value=val, unit=unit or "tablet")
            except ValueError:
                pass

    dose_rate = DoseAndRate(doseQuantity=dose_qty) if dose_qty else None

    dosage = Dosage(
        text=f"Dose: {dose_str}, Frequency: {freq_str}, Duration: {duration_val} days",
        timing=timing,
        doseAndRate=[dose_rate] if dose_rate else None
    )

    mr = MedicationRequest(
        status="active",
        intent="order",
        medicationCodeableConcept=CodeableConcept(text=medication),
        subject=Reference(reference=f"Patient/{patient_id}"),
        authoredOn=record_date,
        dosageInstruction=[dosage]
    )
    return mr.model_dump()
