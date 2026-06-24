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
    return response.choices[0].message.content


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
    )
    return response.choices[0].message.content


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

def symptom_chat(history: list[dict]) -> str:
    """Continue the symptom intake conversation."""
    return chat(history, SYMPTOM_CHAT_SYSTEM)


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
