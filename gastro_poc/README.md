# Gastro EMR — Streamlit POC

## Setup

```bash
cd gastro_poc
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add your OpenAI or Anthropic API key
```

## Run

```bash
streamlit run app.py
```

## Credentials

- **Doctor login:** username `doctor` / password `clinic123`  
  _(change in `core/emr_store.py → authenticate_doctor` for now)_
- **Patients:** register via the New Patient tab on the login screen

## File structure

```
gastro_poc/
├── app.py                  # Login screen
├── pages/
│   ├── 01_Patient_Chat.py  # AI symptom intake chat
│   ├── 02_EMR_View.py      # Patient: view & edit their EMR
│   └── 03_Doctor_View.py   # Doctor: summary, diagnosis, prescription
├── core/
│   ├── ai_engine.py        # LLM calls (OpenAI / Anthropic)
│   ├── emr_store.py        # JSON persistence (swap for MongoDB later)
│   └── prompts.py          # All system prompts
├── data/
│   └── emr_db.json         # Auto-created on first run
└── .env                    # Your API key (not committed)
```

## AI Provider

Set in `.env`:
- `AI_PROVIDER=openai` + `AI_MODEL=gpt-4o-mini` ← recommended (cheap, fast)
- `AI_PROVIDER=anthropic` + `AI_MODEL=claude-haiku-4-5-20251001`

## What the POC covers

- Patient login + registration (persistent across sessions)
- EMR sections A–F (personal info, medical history, family, habits, symptoms)
- AI-driven MCQ symptom intake chat with follow-up logic
- Auto-fills Section F (symptoms) and Section B (chief complaint) from chat
- Generates a clinical summary + possible differentials for the doctor
- Doctor adds diagnosis + prescription → saved to patient EMR
- Visit history per patient

## What's NOT in the POC (Django phase)

- Real authentication (hashed passwords, sessions)
- MongoDB storage
- Multi-doctor support
- Appointment / reservation scheduling
- PDF export of prescriptions
- SLM swap-in for on-premise privacy
