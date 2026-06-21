"""
JSON-based persistence for POC (will be replaced by MongoDB in Django phase).
All patient data lives in data/emr_db.json.
"""

import json
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "emr_db.json")


def _load_db() -> dict:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if not os.path.exists(DB_PATH):
        return {"patients": {}}
    with open(DB_PATH, "r") as f:
        return json.load(f)


def _save_db(db: dict):
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2, default=str)


# ── Patients ────────────────────────────────────────────────────────────────

def get_patient(patient_id: str) -> Optional[dict]:
    return _load_db()["patients"].get(patient_id)


def list_patients() -> list[dict]:
    return list(_load_db()["patients"].values())


def upsert_patient(patient_id: str, data: dict):
    db = _load_db()
    existing = db["patients"].get(patient_id, {})
    existing.update(data)
    existing["patient_id"] = patient_id
    existing["updated_at"] = datetime.now().isoformat()
    db["patients"][patient_id] = existing
    _save_db(db)


def create_patient(patient_id: str, name: str, password: str) -> dict:
    """Create a new patient with blank EMR template."""
    patient = {
        "patient_id": patient_id,
        "name": name,
        "password": password,  # plain text for POC — hash in production
        "created_at": datetime.now().isoformat(),
        # Section A – Personal Info
        "section_a": {
            "full_name": name,
            "age": None,
            "sex": None,
            "dob": None,
            "phone": None,
            "email": None,
            "address": None,
            "occupation": None,
            "marital_status": None,
        },
        # Section B – Chief Complaint / Current Visit Reason
        "section_b": {
            "chief_complaint": None,
            "duration": None,
            "onset": None,
        },
        # Section C – Past Medical & Surgical History
        "section_c": {
            "chronic_conditions": [],       # e.g. ["Type 2 Diabetes", "GERD"]
            "past_surgeries": [],           # e.g. ["Appendectomy 2018"]
            "past_hospitalizations": [],
            "current_medications": [],
            "allergies": [],
            "previous_gi_issues": [],
        },
        # Section D – Family History
        "section_d": {
            "father": None,
            "mother": None,
            "siblings": None,
            "gi_cancers": None,
            "other_relevant": None,
        },
        # Section E – Personal / Social Habits
        "section_e": {
            "smoking": None,            # Never / Ex-smoker / Current
            "smoking_details": None,
            "alcohol": None,            # None / Occasional / Regular / Heavy
            "alcohol_details": None,
            "diet": None,               # Vegetarian / Non-veg / Mixed
            "exercise": None,
            "stress_level": None,
        },
        # Section F – Review of Systems (GI-focused)
        "section_f": {
            "abdominal_pain": None,
            "pain_location": None,
            "pain_scale": None,         # 1-10
            "pain_character": None,     # Burning / Cramping / Dull / Sharp / Colicky
            "pain_radiation": None,
            "pain_timing": None,        # Constant / Intermittent / After meals / etc.
            "nausea": None,
            "vomiting": None,
            "vomiting_details": None,
            "heartburn": None,
            "regurgitation": None,
            "dysphagia": None,          # difficulty swallowing
            "bloating": None,
            "bowel_habits": None,       # Normal / Constipation / Diarrhea / Alternating
            "stool_character": None,    # Bristol scale description
            "blood_in_stool": None,
            "rectal_bleeding": None,
            "jaundice": None,
            "weight_loss": None,
            "appetite_change": None,
            "fever": None,
        },
        "visits": [],   # list of visit records
    }
    upsert_patient(patient_id, patient)
    return patient


# ── Visits ───────────────────────────────────────────────────────────────────

def add_visit(patient_id: str, visit: dict):
    """Append a visit record to the patient's visit history."""
    db = _load_db()
    patient = db["patients"].get(patient_id)
    if not patient:
        raise ValueError(f"Patient {patient_id} not found")
    visit["visit_id"] = f"V{len(patient['visits']) + 1:03d}"
    visit["date"] = datetime.now().isoformat()
    patient["visits"].append(visit)
    _save_db(db)
    return visit["visit_id"]


def update_visit(patient_id: str, visit_id: str, updates: dict):
    db = _load_db()
    patient = db["patients"].get(patient_id)
    if not patient:
        raise ValueError(f"Patient {patient_id} not found")
    for v in patient["visits"]:
        if v["visit_id"] == visit_id:
            v.update(updates)
            break
    _save_db(db)


def get_latest_visit(patient_id: str) -> Optional[dict]:
    patient = get_patient(patient_id)
    if patient and patient.get("visits"):
        return patient["visits"][-1]
    return None


# ── Auth ────────────────────────────────────────────────────────────────────

def authenticate_patient(patient_id: str, password: str) -> Optional[dict]:
    patient = get_patient(patient_id)
    if patient and patient.get("password") == password:
        return patient
    return None


def authenticate_doctor(username: str, password: str) -> bool:
    """Single doctor — hardcoded for POC. Use env vars in production."""
    return username == "doctor" and password == "clinic123"
