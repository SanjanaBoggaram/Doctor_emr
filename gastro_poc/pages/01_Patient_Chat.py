"""
Page 1: AI Symptom Intake Chat (patient-facing).

Flow:
  - Start a new visit → AI asks MCQ symptom questions
  - On INTAKE_COMPLETE → parse JSON, update EMR sections, save visit
  - Patient can then navigate to 02_EMR to view/edit their record
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import streamlit as st
from core.ai_engine import symptom_chat, parse_intake_json, generate_doctor_summary
from core.emr_store import get_patient, upsert_patient, add_visit

st.set_page_config(page_title="Symptom Chat", page_icon="💬", layout="wide")

# ── Auth guard ───────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in") or st.session_state.get("role") != "patient":
    st.warning("Please log in as a patient first.")
    st.stop()

patient_id = st.session_state.patient_id
patient = get_patient(patient_id)

# ── Session defaults ─────────────────────────────────────────────────────────
for key, default in {
    "chat_history": [],       # [{"role": ..., "content": ...}]
    "intake_done": False,
    "current_visit_id": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.title(f"💬 Symptom Intake — {patient.get('name', patient_id)}")

# ── Sidebar nav ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**Patient:** {patient.get('name')}")
    st.markdown(f"**ID:** {patient_id}")
    st.divider()
    if st.button("📋 View / Edit My EMR"):
        st.switch_page("pages/02_EMR_View.py")
    if st.button("🚪 Logout"):
        for k in ["logged_in", "role", "patient_id", "patient_name",
                  "chat_history", "intake_done", "current_visit_id"]:
            st.session_state.pop(k, None)
        st.switch_page("app.py")

# ── Start / Reset ─────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.caption("The assistant will ask you questions about your symptoms to prepare for your visit.")
with col2:
    if st.button("🔄 New Visit"):
        st.session_state.chat_history = []
        st.session_state.intake_done = False
        st.session_state.current_visit_id = None
        st.rerun()

# ── Render chat history ───────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    if msg["role"] in ("user", "assistant"):
        with st.chat_message(msg["role"]):
            # Hide the raw JSON block from the patient view
            display_content = msg["content"]
            if "INTAKE_COMPLETE" in display_content:
                display_content = display_content.split("INTAKE_COMPLETE")[0].strip()
                if not display_content:
                    display_content = "Thank you, I have all the information needed. The doctor will review your answers shortly."
            st.markdown(display_content)

# ── Intake complete banner ─────────────────────────────────────────────────────
if st.session_state.intake_done:
    st.success("✅ Intake complete! Your information has been saved. The doctor will review it before your appointment.")
    st.stop()

# ── Kick off the chat if empty ────────────────────────────────────────────────
if not st.session_state.chat_history:
    greeting = (
        f"Hello {patient.get('name', 'there')}! I'm the clinic's intake assistant. "
        "I'll ask you a few questions about what brought you in today so the doctor is prepared for your visit.\n\n"
        "**What is the main reason for your visit today?**\n\n"
        "A) Abdominal / stomach pain\n"
        "B) Nausea or vomiting\n"
        "C) Heartburn or acid reflux\n"
        "D) Bowel changes (diarrhea, constipation)\n"
        "E) Other (please describe briefly)"
    )
    st.session_state.chat_history.append({"role": "assistant", "content": greeting})
    with st.chat_message("assistant"):
        st.markdown(greeting)

# ── User input ────────────────────────────────────────────────────────────────
user_input = st.chat_input("Type your answer here…")

if user_input:
    # Add user message
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Get AI response
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            response = symptom_chat(st.session_state.chat_history)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

        # Check if intake is done
        if "INTAKE_COMPLETE" in response:
            st.session_state.intake_done = True

            # Parse structured fields and save to EMR
            intake_data = parse_intake_json(response)
            if intake_data:
                updates = {}
                if "chief_complaint" in intake_data:
                    updates["section_b"] = {
                        "chief_complaint": intake_data.get("chief_complaint"),
                        "duration": intake_data.get("duration"),
                        "onset": intake_data.get("onset"),
                    }
                if "section_f" in intake_data:
                    updates["section_f"] = intake_data["section_f"]
                if updates:
                    upsert_patient(patient_id, updates)

            # Build transcript and doctor summary
            transcript = "\n".join(
                f"{m['role'].upper()}: {m['content']}"
                for m in st.session_state.chat_history
            )
            summary = generate_doctor_summary(get_patient(patient_id), transcript)

            # Save as a new visit
            visit_id = add_visit(patient_id, {
                "chat_transcript": transcript,
                "doctor_summary": summary,
                "intake_data": intake_data,
                "diagnosis": None,
                "prescription": None,
            })
            st.session_state.current_visit_id = visit_id

            # Show friendly completion message (not the raw JSON)
            st.markdown("Thank you, I have all the information needed. The doctor will review your answers shortly.")
        else:
            st.markdown(response)
