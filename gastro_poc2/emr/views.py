"""
EMR views: patient intake chat (HTMX), EMR form, and the doctor dashboard.

The intake conversation is held in the session until the AI emits
INTAKE_COMPLETE; at that point we persist a Visit (transcript + AI summary +
structured fields) and fold the extracted symptoms back into the patient's EMR.
"""

from functools import wraps
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.ai_engine import generate_doctor_summary, parse_intake_json, symptom_chat

from .models import PatientProfile, Visit

CHAT_SESSION_KEY = "intake_chat_history"
INTAKE_DONE_KEY = "intake_done"

_MCQ_LABEL_RE = re.compile(r"\b([A-D]|[1-4])\b", re.IGNORECASE)
_OPTION_LINE_RE = re.compile(r"^\s*([A-D]|[1-4])[\).:\-]\s*(.+?)\s*$", re.IGNORECASE)

GREETING = (
    "Hello {name}! I'm the clinic's intake assistant. I'll ask you a few questions "
    "about what brought you in today so the doctor is prepared for your visit.\n\n"
    "**Could you please state the purpose of your visit and describe your symptoms?**"
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
    """Hide the raw INTAKE_COMPLETE / JSON block and filter thinking text from the patient view."""
    if "INTAKE_COMPLETE" in content:
        shown = content.split("INTAKE_COMPLETE")[0].strip()
        return shown or (
            "Thank you, I have all the information needed. "
            "The doctor will review your answers shortly."
        )
    
    # Strip internal reasoning: lines that read like thinking/deliberation, not questions
    lines = content.split('\n')
    filtered = []
    for line in lines:
        stripped = line.strip()
        # Skip thinking patterns: lines starting with deliberation words or listing fields
        if stripped and re.match(
            r'^(We |Let\'s |I |Check |So |This |That |Here|Also |Now |Next |Then |'
            r'Duration|Onset|Abdominal|Pain|Nausea|Vomiting|Heartburn|Bowel|Stool|'
            r'Blood|Rectal|Jaundice|Weight|Appetite|Fever|Only |Still |Need|Have|Can|'
            r'\-\s+\w+:|\d+\.|^\s*[a-z]+:)',
            stripped, re.IGNORECASE
        ):
            continue
        filtered.append(line)
    
    result = '\n'.join(filtered).strip()
    return result if result else content


def _normalize_mcq_reply(user_text: str, history: list[dict]) -> str:
    """Expand short MCQ replies into explicit selections for the model."""
    if not history:
        return user_text

    last_assistant = next((m.get("content", "") for m in reversed(history) if m.get("role") == "assistant"), "")
    if not last_assistant:
        return user_text

    labels = [match.group(1).upper() for match in _MCQ_LABEL_RE.finditer(user_text)]
    if not labels:
        return user_text

    selected_label = labels[-1]
    option_map: dict[str, str] = {}
    for line in last_assistant.splitlines():
        match = _OPTION_LINE_RE.match(line)
        if match:
            option_map[match.group(1).upper()] = match.group(2).strip()

    selected_text = option_map.get(selected_label)
    if selected_text:
        return f"Selected option {selected_label}: {selected_text}"
    return f"Selected option {selected_label}"


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
    # First-time patients fill (or skip) their bio-data before the intake chat.
    if not request.user.profile.onboarded:
        return redirect("emr:onboarding")
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
    normalized_user_text = _normalize_mcq_reply(user_text, history)
    if normalized_user_text != user_text:
        normalized_user_text = f"{normalized_user_text} (user said: {user_text})"
    history.append({"role": "user", "content": normalized_user_text})

    try:
        reply = symptom_chat(history, patient_context=request.user.profile.brief())
    except Exception as exc:  # surface provider/config errors to the patient
        reply = f"Sorry — the assistant is unavailable right now. ({exc})"

    # Some models (esp. MoE/reasoning ones via OpenRouter) occasionally return
    # empty/None content for a turn — don't crash, just ask the patient to retry.
    if not reply or not reply.strip():
        reply = "Sorry, I didn't quite catch that — could you rephrase or add a little more detail?"

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


# ── Patient: bio-data sections (shared by onboarding + EMR form) ─────────────

def _split_lines(raw: str) -> list:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _section_a(post, current_name):
    return (
        {
            "age": post.get("age") or None,
            "sex": post.get("sex") or None,
            "dob": post.get("dob") or None,
            "phone": post.get("phone") or None,
            "email": post.get("email") or None,
            "address": post.get("address") or None,
            "occupation": post.get("occupation") or None,
            "marital_status": post.get("marital_status") or None,
        },
        post.get("full_name") or current_name,
    )


def _section_c(post):
    return {
        "chronic_conditions": _split_lines(post.get("chronic_conditions")),
        "past_surgeries": _split_lines(post.get("past_surgeries")),
        "past_hospitalizations": _split_lines(post.get("past_hospitalizations")),
        "current_medications": _split_lines(post.get("current_medications")),
        "allergies": _split_lines(post.get("allergies")),
        "previous_gi_issues": _split_lines(post.get("previous_gi_issues")),
    }


def _section_d(post):
    return {
        "father": post.get("father") or None,
        "mother": post.get("mother") or None,
        "siblings": post.get("siblings") or None,
        "gi_cancers": post.get("gi_cancers") or None,
        "other_relevant": post.get("other_relevant") or None,
    }


def _section_e(post):
    return {
        "smoking": post.get("smoking") or None,
        "smoking_details": post.get("smoking_details") or None,
        "alcohol": post.get("alcohol") or None,
        "alcohol_details": post.get("alcohol_details") or None,
        "diet": post.get("diet") or None,
        "exercise": post.get("exercise") or None,
        "stress_level": post.get("stress_level") or None,
    }


@patient_required
def onboarding(request):
    """First-login bio-data form (sections A, C, D, E in one page). Skippable."""
    profile = request.user.profile

    if request.method == "POST":
        if request.POST.get("action") != "skip":
            profile.section_a, profile.full_name = _section_a(request.POST, profile.full_name)
            profile.section_c = _section_c(request.POST)
            profile.section_d = _section_d(request.POST)
            profile.section_e = _section_e(request.POST)
            messages.success(request, "Thanks! Your details are saved. Now let's talk symptoms.")
        profile.onboarded = True
        profile.save()
        return redirect("emr:patient_chat")

    return render(request, "emr/onboarding.html", {"p": profile})


@patient_required
def emr_view(request):
    profile = request.user.profile

    if request.method == "POST":
        section = request.POST.get("section")
        if section == "a":
            profile.section_a, profile.full_name = _section_a(request.POST, profile.full_name)
        elif section == "c":
            profile.section_c = _section_c(request.POST)
        elif section == "d":
            profile.section_d = _section_d(request.POST)
        elif section == "e":
            profile.section_e = _section_e(request.POST)
        profile.save()
        messages.success(request, "Saved.")
        return redirect("emr:emr_view")

    return render(
        request,
        "emr/emr_form.html",
        {"p": profile, "visits": profile.visits.all()},
    )


# ── Patient: visit history ───────────────────────────────────────────────────

def _parse_transcript(text: str) -> list:
    """Turn the stored 'USER:/ASSISTANT:' transcript into chat bubbles, hiding
    the INTAKE_COMPLETE block."""
    bubbles = []
    role = None
    buf = []

    def flush():
        if role and buf:
            content = "\n".join(buf).strip()
            if role == "assistant":
                content = _display_content(content)
            if content:
                bubbles.append({"role": role, "content": content})

    for line in (text or "").splitlines():
        if line.startswith("USER:"):
            flush(); role, buf = "user", [line[5:].strip()]
        elif line.startswith("ASSISTANT:"):
            flush(); role, buf = "assistant", [line[10:].strip()]
        else:
            buf.append(line)
    flush()
    return bubbles


@patient_required
def visit_list(request):
    visits = request.user.profile.visits.all()  # newest first (model Meta ordering)
    return render(
        request,
        "emr/visits.html",
        {"visits": [(v, _parse_transcript(v.chat_transcript)) for v in visits]},
    )


# ── Doctor: dashboard ────────────────────────────────────────────────────────

@doctor_required
def doctor_dashboard(request):
    # All patients, most-recently-active first (patients with no visit sink to the bottom).
    patients = (
        PatientProfile.objects.select_related("user")
        .annotate(last_visit=Max("visits__created_at"))
        .order_by("-last_visit", "-updated_at")
    )

    selected_id = request.GET.get("patient")
    selected = None
    latest = None
    if selected_id:
        selected = get_object_or_404(PatientProfile, pk=selected_id)
    elif patients:
        selected = patients.first()  # most recently active
    if selected:
        latest = selected.visits.first()  # newest visit (model Meta ordering)

    return render(
        request,
        "emr/doctor_dashboard.html",
        {"patients": patients, "selected": selected, "latest": latest},
    )


def _parse_prescription(post) -> dict:
    """Build the structured prescription dict from the doctor's form POST."""
    names = post.getlist("med_name")
    types = post.getlist("med_type")
    schedules = post.getlist("med_schedule")
    durations = post.getlist("med_duration")
    instructions = post.getlist("med_instructions")

    medicines = []
    for i, name in enumerate(names):
        name = (name or "").strip()
        if not name:
            continue  # skip blank rows

        def at(seq):
            return (seq[i].strip() if i < len(seq) and seq[i] else "")

        medicines.append({
            "name": name,
            "type": at(types) or "Tablet",
            "schedule": at(schedules),
            "duration": at(durations),
            "instructions": at(instructions),
        })

    return {
        "medicines": medicines,
        "advice": _split_lines(post.get("advice")),
        "tests": _split_lines(post.get("tests")),
    }


@doctor_required
@require_POST
def visit_update(request, visit_id):
    visit = get_object_or_404(Visit, pk=visit_id)
    visit.diagnosis = request.POST.get("diagnosis", "")
    visit.prescription_data = _parse_prescription(request.POST)
    visit.save()
    messages.success(request, "Saved to patient EMR.")
    return redirect(f"{reverse('emr:doctor_dashboard')}?patient={visit.patient_id}")
