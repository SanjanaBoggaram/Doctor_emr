# Gastro EMR — Django + PostgreSQL (POC2)

A rebuild of the Streamlit POC (`../gastro_poc`) on a production-shaped stack:

- **Django 5** — real auth (hashed passwords, sessions), free admin panel, server-rendered templates
- **PostgreSQL** — relational tables for Patients / Visits, with `JSONB` columns for the flexible EMR sections (A–F)
- **HTMX** — live symptom-intake chat without a separate JS frontend
- **Same AI engine** as POC1 (Gemini / OpenAI / Anthropic / OpenRouter), ported into `core/`

## Architecture

```
gastro_poc2/
├── config/            # Django project (settings, urls, wsgi/asgi)
├── core/              # framework-agnostic AI engine + prompts (ported from POC1)
├── accounts/          # custom User model (patient/doctor roles), login/register
├── emr/               # PatientProfile (+ JSONB sections), Visit, chat, dashboard
│   └── management/commands/seed_doctor.py
├── templates/         # base layout
├── docker-compose.yml # Postgres
└── requirements.txt
```

Data model: `User (accounts)` ──1:1──> `PatientProfile` ──1:N──> `Visit`.
EMR sections A–F are `JSONField` (Postgres `JSONB`) on `PatientProfile`, so the
nested/flexible intake data lives alongside relational integrity.

## Quick start (Postgres via Docker — recommended)

```bash
cd gastro_poc2
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then add your AI API key

docker compose up -d db                             # start Postgres
python manage.py migrate
python manage.py seed_doctor                        # creates doctor / clinic123
python manage.py runserver
```

Open http://127.0.0.1:8000/.

### No Docker? Use sqlite for a quick look

Set `DB_ENGINE=sqlite` in `.env`, then `python manage.py migrate` and run. (You
lose Postgres-specific JSONB indexing, but everything else works identically.)

## Credentials

- **Doctor:** `doctor` / `clinic123` (created by `seed_doctor`; also has `/admin` access)
- **Patients:** register via the "Create an account" link on the login page
- **Superuser (full admin):** `python manage.py createsuperuser`

## RAG — grounding the intake agent

The symptom-intake agent can retrieve clinical reference material to ask better,
guideline-grounded follow-up questions.

```bash
# 1. Put reference docs (.txt / .md / .pdf) in rag_data/  (a sample is included)
# 2. Build the index (uses local, offline embeddings — no API key)
python manage.py build_rag
# 3. Enable it in .env
RAG_ENABLED=true
```

- Vector store: **Chroma** (persistent, in `rag_store/`).
- Embeddings: **local ONNX `all-MiniLM-L6-v2`** by default (offline, free). Switch
  to Gemini with `RAG_EMBED_PROVIDER=gemini` + `GEMINI_API_KEY` for higher quality.
- Rebuild with `build_rag` whenever you change `rag_data/`. If RAG is disabled or
  the index is empty, the chat falls back to working exactly as before.

> **Use the project venv.** RAG's native deps (`chromadb`, `onnxruntime`) live in
> `.venv` to avoid clashing with system packages — run `.venv\Scripts\python manage.py …`.
> On Windows, local onnxruntime requires the **VC++ 2015–2022 x64 runtime**
> (`vc_redist.x64.exe`); an outdated one causes a DLL-load or segfault error.

## What changed vs the Streamlit POC

| POC1 (Streamlit)            | POC2 (Django + Postgres)                      |
|-----------------------------|-----------------------------------------------|
| JSON file (`emr_db.json`)   | PostgreSQL (relational + JSONB)               |
| Plaintext passwords         | Django hashed passwords + sessions            |
| Hardcoded single doctor     | Role-based users; `seed_doctor`; admin panel  |
| UI and data layer fused     | Models / views / templates separated          |
| `st.session_state` chat     | HTMX chat, history in Django session          |
| No admin                    | Django admin for patients/visits/users        |

## Roadmap (next)

- Appointment / reservation scheduling
- PDF export of prescriptions
- Multi-doctor assignment + per-doctor patient lists
- REST API (DRF) if a separate frontend is ever wanted
- On-prem SLM swap-in for privacy
