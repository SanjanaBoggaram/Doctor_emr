"""
Gastro EMR POC — Entry point / Login screen.

Run: streamlit run app.py
"""

import streamlit as st
import sys, os

# Make core/ importable regardless of working directory
sys.path.insert(0, os.path.dirname(__file__))

from core.emr_store import (
    authenticate_patient,
    authenticate_doctor,
    create_patient,
    get_patient,
)

st.set_page_config(
    page_title="GastroClinic EMR",
    page_icon="🏥",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Session state defaults ───────────────────────────────────────────────────
for key, default in {
    "logged_in": False,
    "role": None,           # "patient" | "doctor"
    "patient_id": None,
    "patient_name": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Already logged in → redirect to appropriate page ────────────────────────
if st.session_state.logged_in:
    if st.session_state.role == "patient":
        st.switch_page("pages/01_Patient_Chat.py")
    else:
        st.switch_page("pages/03_Doctor_View.py")


# ── Login UI ─────────────────────────────────────────────────────────────────
st.title("🏥 GastroClinic EMR")
st.caption("Powered by AI-assisted intake")

tab_patient, tab_new, tab_doctor = st.tabs(["Patient Login", "New Patient", "Doctor Login"])

# ── Existing patient ─────────────────────────────────────────────────────────
with tab_patient:
    st.subheader("Patient Login")
    pid = st.text_input("Patient ID", key="login_pid")
    pwd = st.text_input("Password", type="password", key="login_pwd")
    if st.button("Login", key="btn_patient_login"):
        patient = authenticate_patient(pid.strip(), pwd.strip())
        if patient:
            st.session_state.logged_in = True
            st.session_state.role = "patient"
            st.session_state.patient_id = pid.strip()
            st.session_state.patient_name = patient.get("name", pid)
            st.rerun()
        else:
            st.error("Invalid ID or password.")

# ── New patient registration ──────────────────────────────────────────────────
with tab_new:
    st.subheader("Register New Patient")
    new_name = st.text_input("Full Name", key="reg_name")
    new_pid = st.text_input(
        "Choose a Patient ID (e.g. your phone number)",
        key="reg_pid",
    )
    new_pwd = st.text_input("Choose Password", type="password", key="reg_pwd")
    new_pwd2 = st.text_input("Confirm Password", type="password", key="reg_pwd2")
    if st.button("Register", key="btn_register"):
        if not (new_name and new_pid and new_pwd):
            st.error("All fields are required.")
        elif new_pwd != new_pwd2:
            st.error("Passwords do not match.")
        elif get_patient(new_pid.strip()):
            st.error("Patient ID already taken.")
        else:
            create_patient(new_pid.strip(), new_name.strip(), new_pwd.strip())
            st.success("Account created! Please log in.")

# ── Doctor ────────────────────────────────────────────────────────────────────
with tab_doctor:
    st.subheader("Doctor Login")
    doc_user = st.text_input("Username", key="doc_user")
    doc_pwd = st.text_input("Password", type="password", key="doc_pwd")
    if st.button("Login as Doctor", key="btn_doctor_login"):
        if authenticate_doctor(doc_user.strip(), doc_pwd.strip()):
            st.session_state.logged_in = True
            st.session_state.role = "doctor"
            st.rerun()
        else:
            st.error("Invalid credentials.")
