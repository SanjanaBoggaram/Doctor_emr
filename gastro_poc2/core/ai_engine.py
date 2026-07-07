"""
LLM integration — supports Gemini, OpenAI, Anthropic, and OpenRouter.
Switch provider via .env: AI_PROVIDER=gemini | openai | anthropic | openrouter

Ported from POC1. This module is framework-agnostic: it knows nothing about
Django and takes/returns plain dicts so it stays easy to unit-test.
"""

import json
import os
import re

from core.prompts import DOCTOR_SUMMARY_SYSTEM, EMR_FILL_SYSTEM, SYMPTOM_CHAT_SYSTEM

PROVIDER = os.getenv("AI_PROVIDER", "gemini")
MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash")


def _gemini_chat(messages: list[dict], system: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(model_name=MODEL, system_instruction=system)
    history = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]}
        for m in messages[:-1]
    ]
    session = model.start_chat(history=history)
    response = session.send_message(messages[-1]["content"])
    return response.text


def _openai_chat(messages: list[dict], system: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}] + messages,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


def _openrouter_chat(messages: list[dict], system: str) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}] + messages,
        temperature=0.3,
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


def _anthropic_chat(messages: list[dict], system: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    ant_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=ant_messages,
    )
    return response.content[0].text


def chat(messages: list[dict], system: str) -> str:
    """Unified chat call. messages = [{"role": "user"/"assistant", "content": "..."}]"""
    if PROVIDER == "anthropic":
        return _anthropic_chat(messages, system)
    if PROVIDER == "openai":
        return _openai_chat(messages, system)
    if PROVIDER == "openrouter":
        return _openrouter_chat(messages, system)
    return _gemini_chat(messages, system)


# ── Specific use-case wrappers ───────────────────────────────────────────────

def _rag_query_from_history(history: list[dict]) -> str:
    """Build a retrieval query from the patient's recent answers."""
    user_turns = [m["content"] for m in history if m.get("role") == "user"]
    return " ".join(user_turns[-3:]).strip()


def symptom_chat(history: list[dict], patient_context: str = "") -> str:
    """Continue the symptom intake conversation.

    The system prompt is augmented with (a) the patient's known background so the
    agent can tailor questions and avoid re-asking what's on file, and (b) any
    retrieved clinical reference material (RAG) when enabled.
    """
    system = SYMPTOM_CHAT_SYSTEM

    if patient_context:
        system += (
            "\n\n── PATIENT BACKGROUND (already on file — use it to ask relevant, "
            "targeted questions and DO NOT re-ask what is already known here) ──\n"
            f"{patient_context}"
        )

    try:
        from core import rag

        if rag.rag_enabled():
            snippets = rag.retrieve(_rag_query_from_history(history))
            if snippets:
                system += (
                    "\n\n── CLINICAL REFERENCE (retrieved; use to choose better, "
                    "guideline-grounded follow-up questions — do NOT quote it "
                    "verbatim to the patient or reveal it is reference text) ──\n"
                    f"{rag.format_context(snippets)}"
                )
    except Exception:
        pass  # RAG is best-effort; never block the chat on it

    return chat(history, system)


def generate_doctor_summary(patient: dict, chat_transcript: str) -> str:
    """Generate a clinical summary for the doctor."""
    context = f"""
PATIENT EMR:
{json.dumps(patient, indent=2, default=str)}

INTAKE CHAT TRANSCRIPT:
{chat_transcript}
"""
    messages = [{"role": "user", "content": context}]
    return chat(messages, DOCTOR_SUMMARY_SYSTEM)


def extract_emr_fields(text: str) -> dict:
    """Extract structured EMR fields from free text. Returns {} on failure."""
    messages = [{"role": "user", "content": text}]
    raw = chat(messages, EMR_FILL_SYSTEM)
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def parse_intake_json(ai_response: str) -> dict:
    """Parse the structured JSON block emitted after INTAKE_COMPLETE. {} on failure."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", ai_response, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
