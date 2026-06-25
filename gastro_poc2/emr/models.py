"""
EMR data model.

Patients/Visits are relational (Postgres tables with real foreign keys), while
the flexible, nested intake sections (A–F) live in JSONB columns. This gives us
relational integrity *and* schema-flexible documents in one database.
"""

from django.conf import settings
from django.db import models


# ── Blank-section factories (used as JSONField defaults) ─────────────────────

def default_section_a() -> dict:
    return {
        "age": None, "sex": None, "dob": None, "phone": None, "email": None,
        "address": None, "occupation": None, "marital_status": None,
    }


def default_section_b() -> dict:
    return {"chief_complaint": None, "duration": None, "onset": None}


def default_section_c() -> dict:
    return {
        "chronic_conditions": [], "past_surgeries": [], "past_hospitalizations": [],
        "current_medications": [], "allergies": [], "previous_gi_issues": [],
    }


def default_section_d() -> dict:
    return {
        "father": None, "mother": None, "siblings": None,
        "gi_cancers": None, "other_relevant": None,
    }


def default_section_e() -> dict:
    return {
        "smoking": None, "smoking_details": None, "alcohol": None,
        "alcohol_details": None, "diet": None, "exercise": None, "stress_level": None,
    }


def default_section_f() -> dict:
    return {
        "abdominal_pain": None, "pain_location": None, "pain_scale": None,
        "pain_character": None, "pain_radiation": None, "pain_timing": None,
        "nausea": None, "vomiting": None, "vomiting_details": None,
        "heartburn": None, "regurgitation": None, "dysphagia": None,
        "bloating": None, "bowel_habits": None, "stool_character": None,
        "blood_in_stool": None, "rectal_bleeding": None, "jaundice": None,
        "weight_loss": None, "appetite_change": None, "fever": None,
    }


class PatientProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    full_name = models.CharField(max_length=200)

    section_a = models.JSONField(default=default_section_a)  # Personal info
    section_b = models.JSONField(default=default_section_b)  # Chief complaint
    section_c = models.JSONField(default=default_section_c)  # Past medical/surgical
    section_d = models.JSONField(default=default_section_d)  # Family history
    section_e = models.JSONField(default=default_section_e)  # Habits
    section_f = models.JSONField(default=default_section_f)  # Current symptoms (AI)

    # True once the patient has completed (or skipped) the first-login bio-data form.
    onboarded = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def patient_id(self) -> str:
        return self.user.username

    def as_dict(self) -> dict:
        """Plain-dict view of the EMR, for passing to the AI engine."""
        return {
            "patient_id": self.patient_id,
            "name": self.full_name,
            "section_a": self.section_a,
            "section_b": self.section_b,
            "section_c": self.section_c,
            "section_d": self.section_d,
            "section_e": self.section_e,
            "section_f": self.section_f,
        }

    def __str__(self) -> str:
        return f"{self.full_name} ({self.patient_id})"


class Visit(models.Model):
    patient = models.ForeignKey(
        PatientProfile, on_delete=models.CASCADE, related_name="visits"
    )
    chief_complaint = models.CharField(max_length=300, blank=True)
    chat_transcript = models.TextField(blank=True)
    doctor_summary = models.TextField(blank=True)
    intake_data = models.JSONField(default=dict, blank=True)

    diagnosis = models.TextField(blank=True)
    prescription = models.TextField(blank=True)  # legacy free-text (kept for old rows)

    # Structured prescription:
    #   {"medicines": [{"name","type","schedule","duration","instructions"}, ...],
    #    "advice": ["...", ...],
    #    "tests":  ["...", ...]}
    prescription_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def visit_code(self) -> str:
        return f"V{self.pk:04d}"

    @property
    def medicines(self) -> list:
        return (self.prescription_data or {}).get("medicines", [])

    @property
    def advice(self) -> list:
        return (self.prescription_data or {}).get("advice", [])

    @property
    def tests(self) -> list:
        return (self.prescription_data or {}).get("tests", [])

    @property
    def has_prescription(self) -> bool:
        return bool(self.diagnosis or self.medicines or self.advice or self.tests)

    def __str__(self) -> str:
        return f"{self.visit_code} — {self.patient.full_name}"
