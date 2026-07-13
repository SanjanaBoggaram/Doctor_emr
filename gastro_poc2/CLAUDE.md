# CLAUDE.md — gastro_poc2

Django 5 + PostgreSQL rebuild of the Streamlit POC (`../gastro_poc`) on a production-shaped stack: real hashed-password auth, sessions, the Django admin, server-rendered templates, and an HTMX symptom-intake chat. The AI engine (`core/`) is ported unchanged from POC1.

## Run

```bash
python -m venv .venv && . .venv/Scripts/activate    # Windows
pip install -r requirements.txt
cp .env.example .env                                 # add an AI API key
docker compose up -d db                              # start Postgres
python manage.py migrate
python manage.py seed_doctor                         # creates doctor / clinic123
python manage.py runserver
```

Open http://127.0.0.1:8000/.

**No Docker?** Set `DB_ENGINE=sqlite` in `.env`, then `migrate` and `runserver` — everything works identically minus Postgres JSONB indexing.

## Credentials

- **Doctor:** `doctor` / `clinic123` — created/reset by `python manage.py seed_doctor` (also `is_staff`, so `/admin` works).
- **Patients:** register via "Create an account" on the login page.
- **Superuser:** `python manage.py createsuperuser`.

## Architecture

```
config/    Django project — settings, urls, wsgi/asgi
core/      framework-agnostic AI engine + prompts (ported from POC1)
accounts/  custom User model (patient/doctor roles), login/register
emr/       PatientProfile (JSONB sections), Visit, intake chat, doctor dashboard
templates/ base layout
```

- [config/settings.py](config/settings.py) — env-driven; Postgres by default, sqlite via `DB_ENGINE=sqlite`. `AUTH_USER_MODEL = "accounts.User"`.
- [accounts/models.py](accounts/models.py) — `User(AbstractUser)` with a `role` field; `is_patient` / `is_doctor` properties (doctor also true when `is_staff`).
- [emr/models.py](emr/models.py) — `PatientProfile` (1:1 with User) + `Visit` (1:N).
- [emr/views.py](emr/views.py) — intake chat (HTMX), EMR form, doctor dashboard.
- [core/ai_engine.py](core/ai_engine.py) / [core/prompts.py](core/prompts.py) — same LLM wrapper and prompts as POC1.

## Data model

`User (accounts)` ──1:1──> `PatientProfile` ──1:N──> `Visit`.

Patients/Visits are real relational tables; the flexible EMR sections **A–F live in `JSONField` (Postgres JSONB)** columns on `PatientProfile`, with blank-section factory functions as defaults. This keeps relational integrity *and* schema-flexible documents in one DB.

- Sections: **A** personal · **B** chief complaint · **C** past history · **D** family · **E** habits · **F** GI symptoms.
- `PatientProfile.onboarded` (bool) gates the first-login bio-data form.
- `Visit` holds `chief_complaint`, `chat_transcript`, `doctor_summary`, `intake_data` (JSON), `diagnosis`, legacy `prescription` (free-text, unused by UI), and **`prescription_data`** (JSON). `visit_code` is derived (`V0001`); ordered newest-first.
- `prescription_data` shape: `{"medicines": [{name, type, schedule, duration, instructions}], "advice": [...], "tests": [...]}`. Read via `Visit.medicines` / `.advice` / `.tests` / `.has_prescription` properties; rendered read-only by `emr/_prescription.html`.
- `PatientProfile.as_dict()` produces the plain dict the AI engine expects (bridges JSONB → POC1's data shape).

## Intake chat flow (HTMX)

Chat history lives in the **Django session** (`intake_chat_history`), not the DB, until completion.

1. `patient_chat` seeds a greeting; `_chat_messages.html` renders bubbles.
2. `chat_send` (HTMX POST) appends the user message, calls `symptom_chat()`, returns the refreshed message partial.
3. When the reply contains `INTAKE_COMPLETE`, `_finalize_intake()` parses the JSON, folds Section B + merges Section F into the profile, generates a doctor summary, and creates a `Visit`.
4. The raw sentinel/JSON is hidden from the patient via `_display_content()`.

LLM errors are caught and surfaced as a chat message rather than 500ing.

## Routing & roles

- `config/urls.py` → `/admin`, `/accounts/` (accounts.urls), `/` (emr.urls).
- `emr.urls` namespace `emr:` — `home` routes by role; patient: `onboarding`, `patient_chat`, `chat_send`, `chat_reset`, `emr_view`, `visit_list`; doctor: `doctor_dashboard`, `visit_update`.
- `@patient_required` / `@doctor_required` decorators (in `emr/views.py`) wrap `@login_required` and redirect users to their own area.
- **Onboarding gate:** `patient_chat` redirects to `onboarding` while `profile.onboarded` is False. The onboarding form (sections A/C/D/E in one page) saves all and sets `onboarded=True`; a "Skip" POST (`action=skip`) just sets the flag. Section-parsing helpers `_section_a/c/d/e` in `emr/views.py` are shared by `onboarding` and `emr_view`.
- **Patient visits:** `visit_list` renders `visits.html` (Bootstrap accordion); each visit expands to chief complaint, Section-F symptom snapshot from `intake_data`, the parsed chat (`_parse_transcript`, AI differentials hidden), and the doctor's prescription. The AI `doctor_summary` is **doctor-only**, never shown to patients.
- **Doctor dashboard:** patients listed most-recently-active first (`annotate(last_visit=Max(...))`). Structured prescription editor posts parallel `med_*` lists (+ `advice`/`tests` textareas) to `visit_update`; `_parse_prescription` zips them, skipping blank-name rows. Medicine rows are added/removed client-side via a `<template>` + small JS in the dashboard template.

## AI provider

Same contract as POC1, configured in `.env`:

- `AI_PROVIDER` — `gemini` (default) | `openai` | `anthropic` | `openrouter`
- `AI_MODEL` — e.g. `gemini-2.5-flash`
- Keys: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`

Keep the `INTAKE_COMPLETE` + JSON-block prompt contract intact; `parse_intake_json()` depends on it.

## Common commands

```bash
python manage.py migrate
python manage.py makemigrations
python manage.py seed_doctor --username doctor --password clinic123
python manage.py createsuperuser
python manage.py runserver
docker compose up -d db        # Postgres only
docker compose down            # add -v to also drop the gastro_pgdata volume
```

## Conventions & gotchas

- **`accounts.User` is a custom user model.** Always reference it via `settings.AUTH_USER_MODEL` / `get_user_model()`, never `django.contrib.auth.models.User`.
- Changing an EMR section schema means updating the `default_section_*` factories in `emr/models.py` (and likely the `emr_form.html` template) — but existing rows keep their old JSON shape, so handle missing keys defensively (`.get`, merge with `**`).
- DB credentials come from env; `docker-compose.yml` and `config/settings.py` both default to `gastro`/`gastro`/`gastro`.
- `reset_pg_password.ps1` / `reset_log.txt` / `setup_db.sql` are local Postgres-bootstrap helpers from setup, not part of the app.
- `DEBUG`, `SECRET_KEY`, and `ALLOWED_HOSTS` are env-driven with insecure dev defaults — set real values before any non-local deployment.
