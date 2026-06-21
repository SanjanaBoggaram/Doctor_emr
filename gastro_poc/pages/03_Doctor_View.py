"""
Page 3: Doctor Dashboard.

Doctor sees:
  - Patient list
  - For each patient: AI-generated clinical summary of latest visit
  - Ability to add diagnosis + prescription (saved to EMR)
  - Full EMR read-only view
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from core.emr_store import list_patients, get_patient, update_visit

st.set_page_config(page_title="Doctor Dashboard", page_icon="🩺", layout="wide")

# ── Auth guard ───────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in") or st.session_state.get("role") != "doctor":
    st.warning("Doctor login required.")
    st.stop()

st.title("🩺 Doctor Dashboard")

with st.sidebar:
    st.markdown("**Logged in as: Doctor**")
    if st.button("🚪 Logout"):
        for k in ["logged_in", "role"]:
            st.session_state.pop(k, None)
        st.switch_page("app.py")

# ── Patient selector ──────────────────────────────────────────────────────────
patients = list_patients()
if not patients:
    st.info("No patients registered yet.")
    st.stop()

patient_names = {p["patient_id"]: p.get("name", p["patient_id"]) for p in patients}
selected_id = st.selectbox(
    "Select Patient",
    options=list(patient_names.keys()),
    format_func=lambda pid: f"{patient_names[pid]} ({pid})",
)

patient = get_patient(selected_id)
visits = patient.get("visits", [])

st.divider()

# ── Two-column layout: summary | EMR ────────────────────────────────────────
left, right = st.columns([3, 2])

with left:
    st.subheader(f"Latest Visit — {patient.get('name')}")

    if not visits:
        st.info("This patient has not completed an intake chat yet.")
    else:
        latest = visits[-1]
        visit_id = latest.get("visit_id")

        # AI Clinical Summary
        if latest.get("doctor_summary"):
            st.markdown(latest["doctor_summary"])
        else:
            st.info("No AI summary generated for this visit.")

        st.divider()

        # ── Diagnosis & Prescription ──────────────────────────────────────
        st.subheader("📝 Add Diagnosis & Prescription")
        current_dx = latest.get("diagnosis") or ""
        current_rx = latest.get("prescription") or ""

        diagnosis = st.text_area("Diagnosis", value=current_dx, height=80,
                                 placeholder="Enter diagnosis…")
        prescription = st.text_area("Prescription / Management Plan", value=current_rx, height=120,
                                    placeholder="Medications, dosage, follow-up instructions…")

        if st.button("💾 Save to EMR"):
            update_visit(selected_id, visit_id, {
                "diagnosis": diagnosis,
                "prescription": prescription,
            })
            st.success("Saved to patient EMR.")
            st.rerun()

        # ── Chat Transcript ───────────────────────────────────────────────
        with st.expander("📜 View Intake Chat Transcript"):
            transcript = latest.get("chat_transcript", "")
            if transcript:
                for line in transcript.split("\n"):
                    if line.startswith("USER:"):
                        st.markdown(f"🧑 **Patient:** {line[5:].strip()}")
                    elif line.startswith("ASSISTANT:"):
                        content = line[10:].strip()
                        if "INTAKE_COMPLETE" in content:
                            content = content.split("INTAKE_COMPLETE")[0].strip()
                        if content:
                            st.markdown(f"🤖 **Assistant:** {content}")
            else:
                st.info("No transcript available.")

with right:
    st.subheader("📋 Full EMR")

    def show_section(title, data: dict):
        if not data:
            return
        with st.expander(title):
            for k, v in data.items():
                if v is not None and v != [] and v != "":
                    label = k.replace("_", " ").title()
                    if isinstance(v, list):
                        st.markdown(f"**{label}:** {', '.join(str(x) for x in v) if v else '—'}")
                    else:
                        st.markdown(f"**{label}:** {v}")

    show_section("🧑 Personal Info (A)", patient.get("section_a", {}))
    show_section("🏥 Medical History (C)", patient.get("section_c", {}))
    show_section("👨‍👩‍👧 Family History (D)", patient.get("section_d", {}))
    show_section("🚬 Habits (E)", patient.get("section_e", {}))
    show_section("🩺 Symptoms (F)", patient.get("section_f", {}))

    # All visits summary
    if visits:
        with st.expander(f"📅 All Visits ({len(visits)})"):
            for v in reversed(visits):
                st.markdown(f"**{v.get('visit_id')} — {v.get('date', '')[:10]}**")
                if v.get("diagnosis"):
                    st.markdown(f"Dx: {v['diagnosis']}")
                if v.get("prescription"):
                    st.markdown(f"Rx: {v['prescription']}")
                st.divider()
