import os
import sys
import unittest

# Setup project root import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.schemas.fhir import (
    convert_vital_signs_to_fhir,
    convert_lab_result_to_fhir,
    convert_diagnosis_to_fhir,
    convert_prescription_to_fhir,
)

class TestFHIRConversion(unittest.TestCase):
    def test_vital_signs_to_fhir_conversion(self):
        patient_id = "VIP-001"
        record_date = "2026-06-22"
        data = {
            "blood_pressure": "120/80",
            "heart_rate": 72,
            "temperature": 36.5,
            "oxygen_sat": 98
        }
        fhir_res = convert_vital_signs_to_fhir(patient_id, record_date, data)
        
        self.assertEqual(fhir_res["resourceType"], "Observation")
        self.assertEqual(fhir_res["status"], "final")
        self.assertEqual(fhir_res["category"][0]["coding"][0]["code"], "vital-signs")
        self.assertEqual(fhir_res["subject"]["reference"], f"Patient/{patient_id}")
        self.assertEqual(fhir_res["effectiveDateTime"], record_date)
        
        # Check components
        components = fhir_res["component"]
        self.assertEqual(len(components), 5)  # systolic, diastolic, heart rate, temp, spo2
        
        # Verify systolic
        systolic = next(c for c in components if c["code"]["coding"][0]["code"] == "8480-6")
        self.assertEqual(systolic["valueQuantity"]["value"], 120.0)
        self.assertEqual(systolic["valueQuantity"]["unit"], "mmHg")
        
        # Verify spo2
        spo2 = next(c for c in components if c["code"]["coding"][0]["code"] == "2708-6")
        self.assertEqual(spo2["valueQuantity"]["value"], 98.0)
        self.assertEqual(spo2["valueQuantity"]["unit"], "%")

    def test_lab_result_to_fhir_conversion(self):
        patient_id = "VIP-002"
        record_date = "2026-06-21"
        data = {
            "test_name": "Blood Glucose",
            "result_value": "5.6",
            "reference_range": "4.0 - 6.0",
            "unit": "mmol/L"
        }
        fhir_res = convert_lab_result_to_fhir(patient_id, record_date, data)
        
        self.assertEqual(fhir_res["resourceType"], "Observation")
        self.assertEqual(fhir_res["status"], "final")
        self.assertEqual(fhir_res["category"][0]["coding"][0]["code"], "laboratory")
        self.assertEqual(fhir_res["code"]["text"], "Blood Glucose")
        self.assertEqual(fhir_res["valueQuantity"]["value"], 5.6)
        self.assertEqual(fhir_res["valueQuantity"]["unit"], "mmol/L")
        self.assertEqual(fhir_res["referenceRange"][0]["text"], "4.0 - 6.0")

        # Test non-numeric result
        data_text = {
            "test_name": "Urine Culture",
            "result_value": "Negative",
            "reference_range": "Negative",
            "unit": ""
        }
        fhir_res_text = convert_lab_result_to_fhir(patient_id, record_date, data_text)
        self.assertEqual(fhir_res_text["valueString"], "Negative")
        self.assertIsNone(fhir_res_text["valueQuantity"])

    def test_diagnosis_to_fhir_conversion(self):
        patient_id = "VIP-003"
        record_date = "2026-06-20"
        data = {
            "icd_code": "I10",
            "severity": "Mild",
            "symptoms": "Essential hypertension"
        }
        fhir_res = convert_diagnosis_to_fhir(patient_id, record_date, data)
        
        self.assertEqual(fhir_res["resourceType"], "Condition")
        self.assertEqual(fhir_res["clinicalStatus"]["coding"][0]["code"], "active")
        self.assertEqual(fhir_res["verificationStatus"]["coding"][0]["code"], "confirmed")
        self.assertEqual(fhir_res["category"][0]["coding"][0]["code"], "encounter-diagnosis")
        self.assertEqual(fhir_res["severity"]["coding"][0]["code"], "mild")
        self.assertEqual(fhir_res["code"]["coding"][0]["code"], "I10")
        self.assertEqual(fhir_res["code"]["coding"][0]["display"], "Essential hypertension")
        self.assertEqual(fhir_res["recordedDate"], record_date)

    def test_prescription_to_fhir_conversion(self):
        patient_id = "VIP-004"
        record_date = "2026-06-19"
        data = {
            "medication": "Amlodipine 5mg",
            "dose": "1 tablet",
            "frequency": "Once daily",
            "duration": 30
        }
        fhir_res = convert_prescription_to_fhir(patient_id, record_date, data)
        
        self.assertEqual(fhir_res["resourceType"], "MedicationRequest")
        self.assertEqual(fhir_res["status"], "active")
        self.assertEqual(fhir_res["intent"], "order")
        self.assertEqual(fhir_res["medicationCodeableConcept"]["text"], "Amlodipine 5mg")
        self.assertEqual(fhir_res["authoredOn"], record_date)
        
        dosage = fhir_res["dosageInstruction"][0]
        self.assertIn("Amlodipine 5mg", fhir_res["medicationCodeableConcept"]["text"])
        self.assertEqual(dosage["timing"]["repeat"]["duration"], 30.0)
        self.assertEqual(dosage["timing"]["repeat"]["durationUnit"], "d")
        self.assertEqual(dosage["doseAndRate"][0]["doseQuantity"]["value"], 1.0)
        self.assertEqual(dosage["doseAndRate"][0]["doseQuantity"]["unit"], "tablet")
