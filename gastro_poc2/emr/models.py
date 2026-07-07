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

    def brief(self) -> str:
        """A concise, plain-text background summary for the intake agent — so it
        can tailor questions and avoid re-asking what's already on file.
        Returns "" when nothing is known (e.g. a patient who skipped onboarding)."""
        a, c, d, e = (self.section_a or {}, self.section_c or {},
                      self.section_d or {}, self.section_e or {})
        lines = []

        demo = [str(x) for x in (
            f"{a['age']}y" if a.get("age") else None,
            a.get("sex"), a.get("occupation"),
        ) if x]
        if demo:
            lines.append("Demographics: " + ", ".join(demo))

        for label, key in [
            ("Chronic conditions", "chronic_conditions"),
            ("Current medications", "current_medications"),
            ("Allergies", "allergies"),
            ("Past surgeries", "past_surgeries"),
            ("Previous GI issues", "previous_gi_issues"),
        ]:
            vals = c.get(key) or []
            if vals:
                lines.append(f"{label}: " + ", ".join(str(v) for v in vals))

        fam = [f"{k}: {d[k]}" for k in ("father", "mother", "siblings") if d.get(k)]
        if d.get("gi_cancers") and d["gi_cancers"] not in ("No", "Unknown"):
            fam.append(f"family GI cancers: {d['gi_cancers']}")
        if d.get("other_relevant"):
            fam.append(str(d["other_relevant"]))
        if fam:
            lines.append("Family history: " + "; ".join(fam))

        hab = [f"{label} {e[key]}" for label, key in
               [("smoking", "smoking"), ("alcohol", "alcohol"), ("diet", "diet")]
               if e.get(key)]
        if hab:
            lines.append("Habits: " + ", ".join(hab))

        dx = [f"{v.created_at:%Y-%m-%d}: {v.diagnosis}"
              for v in self.visits.all() if v.diagnosis]
        if dx:
            lines.append("Past diagnoses: " + " | ".join(dx[:5]))

        return "\n".join(f"- {ln}" for ln in lines)

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
