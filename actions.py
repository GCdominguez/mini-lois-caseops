from __future__ import annotations

import json
import re
from typing import Any

import ollama

from rag import DEFAULT_LLM_MODEL, build_context, retrieve_chunks

ALLOWED_ACTION_TYPES = {"create_task", "add_note", "create_calendar_event"}


def _extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response.")
    return json.loads(text[start : end + 1])


def validate_action(action: dict[str, Any], matter_id: str) -> dict[str, Any]:
    action_type = action.get("action_type")
    if action_type not in ALLOWED_ACTION_TYPES:
        raise ValueError(f"Unsupported action_type: {action_type}")

    action["matter_id"] = matter_id

    if action_type == "create_task":
        if not action.get("title"):
            raise ValueError("create_task requires title.")
    elif action_type == "add_note":
        if not action.get("note_text"):
            raise ValueError("add_note requires note_text.")
    elif action_type == "create_calendar_event":
        if not action.get("title") or not action.get("event_date"):
            raise ValueError("create_calendar_event requires title and event_date.")

    return action


def propose_action(
    request: str,
    matter: dict[str, Any],
    model: str = DEFAULT_LLM_MODEL,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chunks = retrieve_chunks(request, matter["matter_id"])
    context = build_context(chunks)

    system = """
You are an action planner for Mini LOIS, a legal operations assistant prototype.
Return exactly one JSON object and nothing else.
Do not execute anything. Only propose one safe action based on the matter context.
Allowed action_type values: create_task, add_note, create_calendar_event.

Schemas:
create_task: {"action_type":"create_task","matter_id":"...","title":"...","assigned_to":"...","due_date":"YYYY-MM-DD or null","reason":"..."}
add_note: {"action_type":"add_note","matter_id":"...","note_text":"...","author":"Mini LOIS","reason":"..."}
create_calendar_event: {"action_type":"create_calendar_event","matter_id":"...","title":"...","event_date":"YYYY-MM-DD","owner":"...","reason":"..."}

Use null for unknown optional dates. Do not invent unsupported facts. Use the request and context to choose the best action.
""".strip()

    user = f"""
Matter metadata:
{matter}

Matter context:
{context}

User request:
{request}
""".strip()

    response = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        options={"temperature": 0},
    )
    raw = response["message"]["content"]
    action = _extract_json(raw)
    return validate_action(action, matter["matter_id"]), chunks
