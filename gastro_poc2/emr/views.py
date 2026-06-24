"""
EMR views: patient intake chat (HTMX), EMR form, and the doctor dashboard.

The intake conversation is held in the session until the AI emits
INTAKE_COMPLETE; at that point we persist a Visit (transcript + AI summary +
structured fields) and fold the extracted symptoms back into the patient's EMR.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.ai_engine import generate_doctor_summary, parse_intake_json, symptom_chat

from .models import PatientProfile, Visit

CHAT_SESSION_KEY = "intake_chat_history"
INTAKE_DONE_KEY = "intake_done"

GREETING = (
    "Hello {name}! I'm the clinic's intake assistant. I'll ask you a few questions "
    "about what brought you in today so the doctor is prepared for your visit.\n\n"
    "**What is the main reason for your visit today?**\n\n"
    "A) Abdominal / stomach pain\n"
    "B) Nausea or vomiting\n"
    "C) Heartburn or acid reflux\n"
    "D) Bowel changes (diarrhea, constipation)\n"
    "E) Other (please describe briefly)"
)


# ── Role guards ──────────────────────────────────────────────────────────────

def patient_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_patient:
            return redirect("emr:doctor_dashboard")
        return view(request, *args, **kwargs)
    return wrapper


def doctor_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_doctor:
            return redirect("emr:patient_chat")
        return view(request, *args, **kwargs)
    return wrapper


@login_required
def home(request):
    """Route to the right landing page based on role."""
    if request.user.is_doctor:
        return redirect("emr:doctor_dashboard")
    return redirect("emr:patient_chat")


# ── Patient: intake chat ─────────────────────────────────────────────────────

def _display_content(content: str) -> str:
    """Hide the raw INTAKE_COMPLETE / JSON block from the patient view."""
    if "INTAKE_COMPLETE" in content:
        shown = content.split("INTAKE_COMPLETE")[0].strip()
        return shown or (
            "Thank you, I have all the information needed. "
            "The doctor will review your answers shortly."
        )
    return content


def _ensure_greeting(request):
    history = request.session.get(CHAT_SESSION_KEY)
    if not history:
        greeting = GREETING.format(name=request.user.profile.full_name or "there")
        history = [{"role": "assistant", "content": greeting}]
        request.session[CHAT_SESSION_KEY] = history
    return history


def _chat_context(request):
    history = request.session.get(CHAT_SESSION_KEY, [])
    bubbles = [
        {"role": m["role"], "content": _display_content(m["content"])}
        for m in history
        if m["role"] in ("user", "assistant")
    ]
    return {"bubbles": bubbles, "intake_done": request.session.get(INTAKE_DONE_KEY, False)}


def _render_messages(request):
    return render(request, "emr/_chat_messages.html", _chat_context(request))


@patient_required
def patient_chat(request):
    _ensure_greeting(request)
    return render(request, "emr/patient_chat.html", _chat_context(request))


@patient_required
@require_POST
def chat_send(request):
    """HTMX endpoint: take the patient's message, get the AI reply, return the
    refreshed message list."""
    if request.session.get(INTAKE_DONE_KEY):
        return _render_messages(request)

    user_text = (request.POST.get("message") or "").strip()
    if not user_text:
        return _render_messages(request)

    history = _ensure_greeting(request)
    history.append({"role": "user", "content": user_text})

    try:
        reply = symptom_chat(history)
    except Exception as exc:  # surface provider/config errors to the patient
        reply = f"Sorry — the assistant is unavailable right now. ({exc})"

    history.append({"role": "assistant", "content": reply})
    request.session[CHAT_SESSION_KEY] = history
    request.session.modified = True

    if "INTAKE_COMPLETE" in reply:
        _finalize_intake(request, history, reply)

    return _render_messages(request)


def _finalize_intake(request, history, reply):
    """Persist the completed intake as a Visit and update the EMR sections."""
    profile = request.user.profile
    intake = parse_intake_json(reply)

    if intake.get("chief_complaint"):
        profile.section_b = {
            "chief_complaint": intake.get("chief_complaint"),
            "duration": intake.get("duration"),
            "onset": intake.get("onset"),
        }
    if intake.get("section_f"):
        # Merge so we don't wipe previously known symptom fields.
        merged = {**profile.section_f, **intake["section_f"]}
        profile.section_f = merged
    profile.save()

    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)
    try:
        summary = generate_doctor_summary(profile.as_dict(), transcript)
    except Exception as exc:
        summary = f"(Summary unavailable: {exc})"

    Visit.objects.create(
        patient=profile,
        chief_complaint=intake.get("chief_complaint", "") or "",
        chat_transcript=transcript,
        doctor_summary=summary,
        intake_data=intake,
    )
    request.session[INTAKE_DONE_KEY] = True
    request.session.modified = True


@patient_required
@require_POST
def chat_reset(request):
    request.session.pop(CHAT_SESSION_KEY, None)
    request.session.pop(INTAKE_DONE_KEY, None)
    return redirect("emr:patient_chat")


# ── Patient: EMR form ────────────────────────────────────────────────────────

def _split_lines(raw: str) -> list:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


@patient_required
def emr_view(request):
    profile = request.user.profile

    if request.method == "POST":
        section = request.POST.get("section")
        if section == "a":
            profile.section_a = {
                "age": request.POST.get("age") or None,
                "sex": request.POST.get("sex") or None,
                "dob": request.POST.get("dob") or None,
                "phone": request.POST.get("phone") or None,
                "email": request.POST.get("email") or None,
                "address": request.POST.get("address") or None,
                "occupation": request.POST.get("occupation") or None,
                "marital_status": request.POST.get("marital_status") or None,
            }
            profile.full_name = request.POST.get("full_name") or profile.full_name
        elif section == "c":
            profile.section_c = {
                "chronic_conditions": _split_lines(request.POST.get("chronic_conditions")),
                "past_surgeries": _split_lines(request.POST.get("past_surgeries")),
                "past_hospitalizations": _split_lines(request.POST.get("past_hospitalizations")),
                "current_medications": _split_lines(request.POST.get("current_medications")),
                "allergies": _split_lines(request.POST.get("allergies")),
                "previous_gi_issues": _split_lines(request.POST.get("previous_gi_issues")),
            }
        elif section == "d":
            profile.section_d = {
                "father": request.POST.get("father") or None,
                "mother": request.POST.get("mother") or None,
                "siblings": request.POST.get("siblings") or None,
                "gi_cancers": request.POST.get("gi_cancers") or None,
                "other_relevant": request.POST.get("other_relevant") or None,
            }
        elif section == "e":
            profile.section_e = {
                "smoking": request.POST.get("smoking") or None,
                "smoking_details": request.POST.get("smoking_details") or None,
                "alcohol": request.POST.get("alcohol") or None,
                "alcohol_details": request.POST.get("alcohol_details") or None,
                "diet": request.POST.get("diet") or None,
                "exercise": request.POST.get("exercise") or None,
                "stress_level": request.POST.get("stress_level") or None,
            }
        profile.save()
        messages.success(request, "Saved.")
        return redirect("emr:emr_view")

    return render(
        request,
        "emr/emr_form.html",
        {"p": profile, "visits": profile.visits.all()},
    )


# ── Doctor: dashboard ────────────────────────────────────────────────────────

@doctor_required
def doctor_dashboard(request):
    patients = PatientProfile.objects.select_related("user").all()
    selected_id = request.GET.get("patient")
    selected = None
    latest = None
    if selected_id:
        selected = get_object_or_404(PatientProfile, pk=selected_id)
        latest = selected.visits.first()  # ordered -created_at
    elif patients:
        selected = patients.first()
        latest = selected.visits.first()

    return render(
        request,
        "emr/doctor_dashboard.html",
        {"patients": patients, "selected": selected, "latest": latest},
    )


@doctor_required
@require_POST
def visit_update(request, visit_id):
    visit = get_object_or_404(Visit, pk=visit_id)
    visit.diagnosis = request.POST.get("diagnosis", "")
    visit.prescription = request.POST.get("prescription", "")
    visit.save()
    messages.success(request, "Saved to patient EMR.")
    return redirect(f"{reverse('emr:doctor_dashboard')}?patient={visit.patient_id}")
