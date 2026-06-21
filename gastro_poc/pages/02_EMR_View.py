"""
Page 2: Patient EMR View & Edit.

Patient can view and update all persistent sections (A–F).
Changes are saved immediately to the JSON store.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from core.emr_store import get_patient, upsert_patient

st.set_page_config(page_title="My Health Record", page_icon="📋", layout="wide")

# ── Auth guard ───────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in") or st.session_state.get("role") != "patient":
    st.warning("Please log in as a patient first.")
    st.stop()

patient_id = st.session_state.patient_id
patient = get_patient(patient_id)

st.title("📋 My Health Record")
st.caption("Review and update your information. Changes are saved immediately.")

with st.sidebar:
    st.markdown(f"**Patient:** {patient.get('name')}")
    if st.button("💬 Go to Symptom Chat"):
        st.switch_page("pages/01_Patient_Chat.py")
    if st.button("🚪 Logout"):
        for k in ["logged_in", "role", "patient_id", "patient_name",
                  "chat_history", "intake_done", "current_visit_id"]:
            st.session_state.pop(k, None)
        st.switch_page("app.py")

# ── Helper: save section ──────────────────────────────────────────────────────
def save_section(section_key: str, data: dict):
    upsert_patient(patient_id, {section_key: data})
    st.toast("Saved ✅", icon="✅")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A — Personal Info
# ═══════════════════════════════════════════════════════════════════════════════
with st.expander("🧑 Section A — Personal Information", expanded=True):
    a = patient.get("section_a", {})
    col1, col2 = st.columns(2)
    with col1:
        a_name = st.text_input("Full Name", value=a.get("full_name") or "")
        a_age = st.number_input("Age", min_value=0, max_value=120,
                                value=int(a["age"]) if a.get("age") else 0)
        a_sex = st.selectbox("Sex", ["", "Male", "Female", "Other"],
                             index=["", "Male", "Female", "Other"].index(a.get("sex") or ""))
        a_dob = st.text_input("Date of Birth (DD/MM/YYYY)", value=a.get("dob") or "")
    with col2:
        a_phone = st.text_input("Phone", value=a.get("phone") or "")
        a_email = st.text_input("Email", value=a.get("email") or "")
        a_occ = st.text_input("Occupation", value=a.get("occupation") or "")
        a_marital = st.selectbox(
            "Marital Status", ["", "Single", "Married", "Divorced", "Widowed"],
            index=["", "Single", "Married", "Divorced", "Widowed"].index(a.get("marital_status") or "")
        )
    if st.button("Save Personal Info", key="save_a"):
        save_section("section_a", {
            "full_name": a_name, "age": a_age or None, "sex": a_sex or None,
            "dob": a_dob or None, "phone": a_phone or None, "email": a_email or None,
            "occupation": a_occ or None, "marital_status": a_marital or None,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C — Past Medical & Surgical History
# ═══════════════════════════════════════════════════════════════════════════════
with st.expander("🏥 Section C — Past Medical & Surgical History"):
    c = patient.get("section_c", {})

    def list_editor(label, key, current):
        st.markdown(f"**{label}**")
        items = list(current or [])
        new_item = st.text_input(f"Add {label.lower()}", key=f"new_{key}")
        if st.button(f"Add", key=f"add_{key}") and new_item:
            items.append(new_item.strip())
        for i, item in enumerate(items):
            cols = st.columns([8, 1])
            with cols[0]:
                items[i] = st.text_input(f"{label} #{i+1}", value=item, key=f"{key}_{i}", label_visibility="collapsed")
            with cols[1]:
                if st.button("✕", key=f"del_{key}_{i}"):
                    items.pop(i)
                    break
        return [x for x in items if x]

    c_conditions = list_editor("Chronic Conditions", "conditions", c.get("chronic_conditions"))
    c_surgeries = list_editor("Past Surgeries", "surgeries", c.get("past_surgeries"))
    c_meds = list_editor("Current Medications", "meds", c.get("current_medications"))
    c_allergies = list_editor("Allergies", "allergies", c.get("allergies"))
    c_gi = list_editor("Previous GI Issues", "gi", c.get("previous_gi_issues"))

    if st.button("Save Medical History", key="save_c"):
        save_section("section_c", {
            "chronic_conditions": c_conditions,
            "past_surgeries": c_surgeries,
            "current_medications": c_meds,
            "allergies": c_allergies,
            "previous_gi_issues": c_gi,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION D — Family History
# ═══════════════════════════════════════════════════════════════════════════════
with st.expander("👨‍👩‍👧 Section D — Family History"):
    d = patient.get("section_d", {})
    d_father = st.text_input("Father's Health Issues", value=d.get("father") or "")
    d_mother = st.text_input("Mother's Health Issues", value=d.get("mother") or "")
    d_siblings = st.text_input("Siblings' Health Issues", value=d.get("siblings") or "")
    d_gi = st.selectbox(
        "GI Cancers in Family?", ["", "Yes", "No", "Unknown"],
        index=["", "Yes", "No", "Unknown"].index(d.get("gi_cancers") or "")
    )
    d_other = st.text_area("Other Relevant Family History", value=d.get("other_relevant") or "")
    if st.button("Save Family History", key="save_d"):
        save_section("section_d", {
            "father": d_father or None, "mother": d_mother or None,
            "siblings": d_siblings or None, "gi_cancers": d_gi or None,
            "other_relevant": d_other or None,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION E — Personal / Social Habits
# ═══════════════════════════════════════════════════════════════════════════════
with st.expander("🚬 Section E — Personal & Social Habits"):
    e = patient.get("section_e", {})
    col1, col2 = st.columns(2)
    with col1:
        e_smoking = st.selectbox(
            "Smoking", ["", "Never", "Ex-smoker", "Current smoker"],
            index=["", "Never", "Ex-smoker", "Current smoker"].index(e.get("smoking") or "")
        )
        e_smoking_detail = st.text_input("Smoking Details (packs/day, years)", value=e.get("smoking_details") or "")
        e_alcohol = st.selectbox(
            "Alcohol", ["", "None", "Occasional", "Regular", "Heavy"],
            index=["", "None", "Occasional", "Regular", "Heavy"].index(e.get("alcohol") or "")
        )
        e_alcohol_detail = st.text_input("Alcohol Details (units/week)", value=e.get("alcohol_details") or "")
    with col2:
        e_diet = st.selectbox(
            "Diet", ["", "Vegetarian", "Non-vegetarian", "Mixed/Omnivore", "Vegan"],
            index=["", "Vegetarian", "Non-vegetarian", "Mixed/Omnivore", "Vegan"].index(e.get("diet") or "")
        )
        e_exercise = st.selectbox(
            "Exercise", ["", "Sedentary", "Light (1-2x/week)", "Moderate (3-4x/week)", "Active (5+/week)"],
            index=["", "Sedentary", "Light (1-2x/week)", "Moderate (3-4x/week)", "Active (5+/week)"].index(e.get("exercise") or "")
        )
        e_stress = st.selectbox(
            "Stress Level", ["", "Low", "Moderate", "High"],
            index=["", "Low", "Moderate", "High"].index(e.get("stress_level") or "")
        )
    if st.button("Save Habits", key="save_e"):
        save_section("section_e", {
            "smoking": e_smoking or None, "smoking_details": e_smoking_detail or None,
            "alcohol": e_alcohol or None, "alcohol_details": e_alcohol_detail or None,
            "diet": e_diet or None, "exercise": e_exercise or None,
            "stress_level": e_stress or None,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION F — Current Symptoms (read-only, filled by AI chat)
# ═══════════════════════════════════════════════════════════════════════════════
with st.expander("🩺 Section F — Current Symptoms (auto-filled by intake chat)"):
    f = patient.get("section_f", {})
    if not any(v for v in f.values()):
        st.info("Complete the symptom chat to auto-fill this section.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            for field in ["abdominal_pain", "pain_location", "pain_scale",
                          "pain_character", "pain_timing", "nausea",
                          "vomiting", "heartburn", "regurgitation", "dysphagia"]:
                val = f.get(field)
                if val is not None:
                    st.markdown(f"**{field.replace('_', ' ').title()}:** {val}")
        with col2:
            for field in ["bloating", "bowel_habits", "stool_character",
                          "blood_in_stool", "rectal_bleeding", "jaundice",
                          "weight_loss", "appetite_change", "fever"]:
                val = f.get(field)
                if val is not None:
                    st.markdown(f"**{field.replace('_', ' ').title()}:** {val}")


# ═══════════════════════════════════════════════════════════════════════════════
# Visit History
# ═══════════════════════════════════════════════════════════════════════════════
visits = patient.get("visits", [])
if visits:
    with st.expander(f"📅 Visit History ({len(visits)} visits)"):
        for v in reversed(visits):
            st.markdown(f"**{v.get('visit_id')} — {v.get('date', '')[:10]}**")
            if v.get("chief_complaint"):
                st.markdown(f"Chief Complaint: {v['chief_complaint']}")
            if v.get("diagnosis"):
                st.markdown(f"🩺 Diagnosis: {v['diagnosis']}")
            if v.get("prescription"):
                st.markdown(f"💊 Prescription: {v['prescription']}")
            st.divider()
