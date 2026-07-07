# CLAUDE.md — gastro_poc

Streamlit proof-of-concept for an AI-assisted gastroenterology EMR. Patients self-register, complete an AI-driven symptom-intake chat, and a doctor reviews an auto-generated clinical summary, then records a diagnosis + prescription. This is POC1; a Django/Postgres rebuild lives in `../gastro_poc2`.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env        # add an AI API key
streamlit run app.py
```

Open the URL Streamlit prints (default http://localhost:8501).

## Credentials

- **Doctor:** `doctor` / `clinic123` — hardcoded in `core/emr_store.py:authenticate_doctor`.
- **Patients:** register via the "New Patient" tab on the login screen.

## Architecture

- [app.py](app.py) — login screen + session-state bootstrap; routes to the right page by `role`.
- [pages/01_Patient_Chat.py](pages/01_Patient_Chat.py) — patient-facing AI symptom intake chat.
- [pages/02_EMR_View.py](pages/02_EMR_View.py) — patient views/edits their own EMR.
- [pages/03_Doctor_View.py](pages/03_Doctor_View.py) — doctor dashboard: patient list, AI summary, diagnosis/prescription entry, EMR view.
- [core/ai_engine.py](core/ai_engine.py) — unified LLM wrapper + use-case helpers.
- [core/prompts.py](core/prompts.py) — all system prompts (centralized for tuning).
- [core/emr_store.py](core/emr_store.py) — JSON persistence layer.
- `data/emr_db.json` — the entire database, auto-created on first run.

Streamlit's `pages/` convention auto-registers pages in the sidebar. Each page guards on `st.session_state` role before rendering.

## Data model

All data is a single JSON file (`data/emr_db.json`) keyed by `patient_id`. Each patient record has EMR sections A–F plus a `visits` list:

- **A** personal info · **B** chief complaint · **C** past medical/surgical history · **D** family history · **E** social habits · **F** GI review of systems (symptoms).
- A **visit** holds: `chat_transcript`, `doctor_summary`, `intake_data`, `diagnosis`, `prescription`, auto-assigned `visit_id` (`V001`...) and `date`.

The chat auto-fills Section B (chief complaint) and Section F (symptoms); Sections A/C/D/E are filled by the patient via the EMR form.

## Intake chat flow

`SYMPTOM_CHAT_SYSTEM` instructs the LLM to ask one MCQ-style question at a time, then emit `INTAKE_COMPLETE` followed by a ```json block. The page detects that sentinel, calls `parse_intake_json()` to extract structured fields, merges them into the EMR via `upsert_patient()`, generates a doctor summary, and saves a `Visit` via `add_visit()`. The raw JSON/sentinel is stripped before display to the patient.

## AI provider

Configured in `.env`:

- `AI_PROVIDER` — `gemini` (code default) | `openai` | `anthropic` | `openrouter`
- `AI_MODEL` — e.g. `gemini-2.5-flash`, `gpt-4o-mini`, `claude-haiku-4-5-20251001`
- Per-provider keys: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`

`core/ai_engine.py:chat()` dispatches to the right provider. OpenRouter reuses the OpenAI SDK with a custom `base_url`.

## Conventions & caveats

- **POC-only shortcuts:** passwords stored in plaintext; single hardcoded doctor; no real sessions/CSRF; JSON file (no concurrency safety). Do not treat as production.
- Pages prepend the project root to `sys.path` so `core/` imports work regardless of CWD.
- The JSON store loads/saves the whole DB on every operation — fine for a POC, not for scale. The `gastro_poc2` Django rebuild replaces this with Postgres + hashed auth.
- Keep prompt edits in `core/prompts.py`; keep the `INTAKE_COMPLETE` + JSON contract intact, since `parse_intake_json()` depends on it.

## Gotchas

- `.env` is required; without a valid key the chat call raises at runtime (the POC does not pre-validate keys).
- Changing the EMR section schema means updating both `create_patient()` in `core/emr_store.py` and the EMR form/display pages.
