from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Any

import streamlit as st

from actions import propose_action
from matter_store import (
    execute_action,
    get_audit_log,
    get_calendar_events,
    get_matter,
    get_matters,
    get_notes,
    get_tasks,
    init_database,
)
from rag import DEFAULT_LLM_MODEL, answer_question

st.set_page_config(page_title="Mini LOIS: CaseOps AI", page_icon="⚖️", layout="wide")

init_database()


def matter_label(matter: dict[str, Any]) -> str:
    return f"{matter['matter_id']} · {matter['matter_name']}"


def parse_optional_date(raw_value: Any) -> str | None:
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if value.lower() in {"", "none", "null", "n/a"}:
        return None

    datetime.strptime(value, "%Y-%m-%d")
    return value


def action_validation_warnings(
    action: dict[str, Any],
    matter: dict[str, Any],
    action_request: str = "",
) -> list[str]:
    warnings: list[str] = []

    if action.get("matter_id") != matter["matter_id"]:
        warnings.append("Matter ID does not match the selected matter.")

    action_type = action.get("action_type")
    if action_type == "create_task":
        if not action.get("title"):
            warnings.append("Task title is missing.")
        assignee = action.get("assigned_to")
        valid_assignees = {matter["paralegal"], matter["lead_attorney"], "Mini LOIS"}
        if assignee and assignee not in valid_assignees:
            warnings.append("Assignee is not listed in this matter's metadata.")

    if action_type == "create_calendar_event" and not action.get("event_date"):
        warnings.append("Calendar event is missing an event date.")

    due_date = action.get("due_date")
    if due_date:
        try:
            parsed_due = datetime.strptime(str(due_date), "%Y-%m-%d").date()
            if parsed_due < date.today():
                warnings.append("Due date is in the past. Verify before approving.")
            if str(due_date) not in action_request:
                warnings.append("Due date was not explicitly requested. Verify it is source-supported.")
        except ValueError:
            warnings.append("Due date must use YYYY-MM-DD format or be blank.")

    reason = str(action.get("reason") or "")
    if action_type in {"create_task", "create_calendar_event"} and len(reason) < 40:
        warnings.append("Reason is brief. Consider making it more source-specific before approval.")

    return warnings


def render_sources(sources: list[dict[str, Any]], heading: str = "### Evidence used") -> None:
    st.markdown(heading)
    for source in sources:
        with st.expander(f"{source['source_id']} · {source['source_file']} · chunk {source['chunk_index']}"):
            st.write(source["text"])


def _clean_candidate(candidate: str) -> str:
    candidate = re.sub(r"^\*\*(.*?)\**$", r"\1", candidate).strip()
    candidate = re.split(r"\s+to\s+", candidate, maxsplit=1)[0]
    candidate = re.sub(r"^(get our hands on|get|the)\s+", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.strip(" -•\t")
    candidate = candidate.rstrip(".")
    return candidate


def _add_candidate(candidates: list[str], candidate: str) -> None:
    candidate = _clean_candidate(candidate)
    lower = candidate.lower()
    if len(candidate) < 8:
        return
    if len(candidate) > 180:
        return
    if lower.startswith(("however", "unfortunately", "without more information")):
        return
    if lower in {"those missing documents", "missing documents", "requesting those missing documents"}:
        return
    if candidate not in candidates:
        candidates.append(candidate)


def _split_inline_task_candidates(fragment: str) -> list[str]:
    fragment = fragment.strip().rstrip(".")
    fragment = re.sub(r"^[:\s,]+", "", fragment)
    fragment = re.split(r"\.\s+", fragment, maxsplit=1)[0]
    fragment = fragment.replace(";", ",")
    fragment = re.sub(r",\s+and\s+", ", ", fragment)
    fragment = re.sub(r"\s+and\s+", ", ", fragment)
    return [_clean_candidate(part) for part in fragment.split(",") if _clean_candidate(part)]


def _extract_inline_next_steps(line: str) -> list[str]:
    lower = line.lower()
    markers = (
        "next steps discussed were",
        "next steps discussed include",
        "next steps to take, including",
        "next steps include",
        "next steps were",
        "next steps are",
        "we still need to",
        "we also need to",
        "we need to",
        "need to get",
    )
    for marker in markers:
        marker_index = lower.find(marker)
        if marker_index != -1:
            fragment = line[marker_index + len(marker) :]
            return _split_inline_task_candidates(fragment)
    return []


def _add_keyword_gap_candidates(answer: str, candidates: list[str]) -> None:
    lower = answer.lower()
    missing_signals = ("missing", "not received", "hasn't been received", "has not been received", "not available", "incomplete", "need to")

    if "police report" in lower and any(signal in lower for signal in missing_signals):
        _add_candidate(candidates, "police report has not been received")

    if "urgent care records" in lower or "urgent care record" in lower:
        if any(signal in lower for signal in missing_signals):
            _add_candidate(candidates, "urgent care records")

    if "physical therapy notes" in lower or "physical therapy records" in lower or "pt records" in lower:
        if any(signal in lower for signal in missing_signals):
            _add_candidate(candidates, "physical therapy records")

    if "billing ledger" in lower and "urgent care" in lower:
        if any(signal in lower for signal in missing_signals):
            _add_candidate(candidates, "urgent care billing ledger")

    if "available witness" in lower and ("contact" in lower or "witness" in lower):
        _add_candidate(candidates, "contacting the available witness")


def extract_task_candidates(answer: str) -> list[str]:
    """Extract short actionable recommendations from a Mini LOIS answer."""
    candidates: list[str] = []
    capture_following_lines = False

    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line:
            capture_following_lines = False
            continue

        lower = line.lower()
        inline_candidates = _extract_inline_next_steps(line)
        for candidate in inline_candidates:
            _add_candidate(candidates, candidate)

        if lower.endswith("such as:") or lower.endswith("including:") or lower.endswith("for example:"):
            capture_following_lines = True
            continue

        bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", line)
        should_capture = capture_following_lines or bullet_match is not None
        if not should_capture:
            continue

        candidate = bullet_match.group(1) if bullet_match else line
        _add_candidate(candidates, candidate)

    _add_keyword_gap_candidates(answer, candidates)
    return candidates[:8]


def task_title_from_candidate(candidate: str) -> str:
    """Turn a verbose answer bullet into a concise operational task title."""
    base = candidate.strip().rstrip(".")
    lower = base.lower()

    if "police report" in lower:
        return "Request police report"
    if "urgent care records" in lower or "urgent care record" in lower:
        return "Request urgent care records"
    if "physical therapy" in lower or "pt records" in lower or "pt record" in lower:
        if "after april 19" in lower:
            return "Request PT records after April 19"
        return "Request PT records"
    if "billing ledger" in lower and "urgent care" in lower:
        return "Request urgent care billing ledger"
    if "witness" in lower:
        return "Contact available witness"
    if "insurance policy" in lower or "coverage details" in lower:
        return "Request insurance policy or coverage details"
    if "internal communication" in lower or "email chain" in lower:
        return "Request driver-company accident communications"
    if "accident report form" in lower or "incident report" in lower:
        return "Request accident or incident report template"
    if "safety protocol" in lower or "handling accidents" in lower:
        return "Request safety protocols for accident handling"
    if "regulatory" in lower and "document" in lower:
        return "Review regulatory compliance documents"
    if "company policies" in lower or "company policy" in lower:
        return "Review company accident and injury policies"

    gerund_prefixes = {
        "requesting ": "Request ",
        "obtaining ": "Obtain ",
        "contacting ": "Contact ",
        "reviewing ": "Review ",
        "collecting ": "Collect ",
        "following up on ": "Follow up on ",
    }
    for prefix, replacement in gerund_prefixes.items():
        if lower.startswith(prefix):
            return replacement + base[len(prefix) :]

    verbs = (
        "review",
        "request",
        "contact",
        "obtain",
        "follow up",
        "check",
        "confirm",
        "prepare",
        "draft",
        "collect",
    )
    if lower.startswith(verbs):
        return base

    request_signals = ("not received", "not been received", "not available", "not been obtained", "missing", "need ")
    if any(signal in lower for signal in request_signals):
        cleaned = re.sub(r"\b(has|have) not been (received|obtained)\b", "", base, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(is|are) not available\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" .")
        return f"Request {cleaned[:1].lower()}{cleaned[1:]}" if cleaned else f"Request {base}"

    cleaned = re.sub(r"^(a copy of|any relevant|any available)\s+", "", base, flags=re.IGNORECASE)
    return f"Review {cleaned[:1].lower()}{cleaned[1:]}"


def candidate_to_task(candidate: str, matter: dict[str, Any]) -> dict[str, Any]:
    base = candidate.strip().rstrip(".")
    title = task_title_from_candidate(base)

    return {
        "action_type": "create_task",
        "matter_id": matter["matter_id"],
        "title": title,
        "assigned_to": matter["paralegal"],
        "due_date": None,
        "reason": f"Created from Mini LOIS answer recommendation: {base}",
    }


def set_answer_task_batch(actions: list[dict[str, Any]], source_refs: list[str]) -> None:
    st.session_state["answer_task_batch"] = actions
    st.session_state["answer_task_batch_original"] = [dict(action) for action in actions]
    st.session_state["answer_task_batch_source_refs"] = source_refs

    for index, action in enumerate(actions):
        st.session_state[f"batch_title_{index}"] = action.get("title", "")
        st.session_state[f"batch_assigned_to_{index}"] = action.get("assigned_to")
        st.session_state[f"batch_due_date_{index}"] = "" if action.get("due_date") is None else str(action.get("due_date"))
        st.session_state[f"batch_reason_{index}"] = action.get("reason", "")


def clear_answer_task_batch() -> None:
    batch = st.session_state.get("answer_task_batch", [])
    for index in range(len(batch)):
        for key in [
            f"batch_title_{index}",
            f"batch_assigned_to_{index}",
            f"batch_due_date_{index}",
            f"batch_reason_{index}",
        ]:
            st.session_state.pop(key, None)
    st.session_state.pop("answer_task_batch", None)
    st.session_state.pop("answer_task_batch_original", None)
    st.session_state.pop("answer_task_batch_source_refs", None)


def build_edited_action_from_form(pending: dict[str, Any], matter: dict[str, Any], prefix: str) -> dict[str, Any]:
    action_type = pending.get("action_type")

    if action_type == "create_task":
        return {
            "action_type": "create_task",
            "matter_id": matter["matter_id"],
            "title": st.session_state.get(f"{prefix}_edit_title", "").strip(),
            "assigned_to": st.session_state.get(f"{prefix}_edit_assigned_to") or None,
            "due_date": parse_optional_date(st.session_state.get(f"{prefix}_edit_due_date")),
            "reason": st.session_state.get(f"{prefix}_edit_reason", "").strip(),
        }

    if action_type == "add_note":
        return {
            "action_type": "add_note",
            "matter_id": matter["matter_id"],
            "note_text": st.session_state.get(f"{prefix}_edit_note_text", "").strip(),
            "author": st.session_state.get(f"{prefix}_edit_author", "Mini LOIS").strip() or "Mini LOIS",
            "reason": st.session_state.get(f"{prefix}_edit_reason", "").strip(),
        }

    if action_type == "create_calendar_event":
        return {
            "action_type": "create_calendar_event",
            "matter_id": matter["matter_id"],
            "title": st.session_state.get(f"{prefix}_edit_title", "").strip(),
            "event_date": parse_optional_date(st.session_state.get(f"{prefix}_edit_event_date")),
            "owner": st.session_state.get(f"{prefix}_edit_owner") or None,
            "reason": st.session_state.get(f"{prefix}_edit_reason", "").strip(),
        }

    raise ValueError(f"Unsupported action_type: {action_type}")


def clear_pending_action(prefix: str) -> None:
    for key in [
        f"{prefix}_pending_action",
        f"{prefix}_pending_source_refs",
        f"{prefix}_pending_sources",
        f"{prefix}_pending_action_request",
        f"{prefix}_edit_title",
        f"{prefix}_edit_assigned_to",
        f"{prefix}_edit_due_date",
        f"{prefix}_edit_reason",
        f"{prefix}_edit_note_text",
        f"{prefix}_edit_author",
        f"{prefix}_edit_event_date",
        f"{prefix}_edit_owner",
    ]:
        st.session_state.pop(key, None)


def store_pending_action(prefix: str, action: dict[str, Any], sources: list[dict[str, Any]], request: str, matter: dict[str, Any]) -> None:
    st.session_state[f"{prefix}_pending_action"] = action
    st.session_state[f"{prefix}_pending_source_refs"] = [s["source_id"] for s in sources]
    st.session_state[f"{prefix}_pending_sources"] = sources
    st.session_state[f"{prefix}_pending_action_request"] = request

    st.session_state[f"{prefix}_edit_title"] = action.get("title", "")
    st.session_state[f"{prefix}_edit_assigned_to"] = action.get("assigned_to") or matter["paralegal"]
    st.session_state[f"{prefix}_edit_due_date"] = "" if action.get("due_date") is None else str(action.get("due_date"))
    st.session_state[f"{prefix}_edit_reason"] = action.get("reason", "")
    st.session_state[f"{prefix}_edit_note_text"] = action.get("note_text", "")
    st.session_state[f"{prefix}_edit_author"] = action.get("author", "Mini LOIS")
    st.session_state[f"{prefix}_edit_event_date"] = "" if action.get("event_date") is None else str(action.get("event_date"))
    st.session_state[f"{prefix}_edit_owner"] = action.get("owner") or matter["paralegal"]


def render_pending_action_editor(prefix: str, matter: dict[str, Any], action_request: str) -> None:
    pending = st.session_state.get(f"{prefix}_pending_action")
    if not pending:
        return

    st.markdown("### Model proposal")
    st.json(pending)

    warnings = action_validation_warnings(
        pending,
        matter,
        st.session_state.get(f"{prefix}_pending_action_request", action_request),
    )
    if warnings:
        st.markdown("### Validation warnings")
        for warning in warnings:
            st.warning(warning)
    else:
        st.success("No validation warnings on the model proposal.")

    sources = st.session_state.get(f"{prefix}_pending_sources", [])
    if sources:
        render_sources(sources)

    st.markdown("### Edit before approval")
    st.caption("The audit log stores both the original model proposal and the approved action when edited.")

    with st.form(f"{prefix}_approve_action_form"):
        st.text_input("Action type", value=pending.get("action_type", ""), disabled=True)
        st.text_input("Matter ID", value=matter["matter_id"], disabled=True)

        if pending.get("action_type") == "create_task":
            st.text_input("Task title", key=f"{prefix}_edit_title")
            assignee_options = [matter["paralegal"], matter["lead_attorney"], "Mini LOIS"]
            current_assignee = st.session_state.get(f"{prefix}_edit_assigned_to") or matter["paralegal"]
            if current_assignee not in assignee_options:
                assignee_options.insert(0, current_assignee)
            st.selectbox(
                "Assigned to",
                assignee_options,
                index=assignee_options.index(current_assignee),
                key=f"{prefix}_edit_assigned_to",
            )
            st.text_input("Due date (YYYY-MM-DD or blank)", key=f"{prefix}_edit_due_date")
            st.text_area("Reason", key=f"{prefix}_edit_reason", height=90)

        elif pending.get("action_type") == "add_note":
            st.text_area("Note text", key=f"{prefix}_edit_note_text", height=120)
            st.text_input("Author", key=f"{prefix}_edit_author")
            st.text_area("Reason", key=f"{prefix}_edit_reason", height=90)

        elif pending.get("action_type") == "create_calendar_event":
            st.text_input("Event title", key=f"{prefix}_edit_title")
            st.text_input("Event date (YYYY-MM-DD)", key=f"{prefix}_edit_event_date")
            owner_options = [matter["paralegal"], matter["lead_attorney"], "Mini LOIS"]
            current_owner = st.session_state.get(f"{prefix}_edit_owner") or matter["paralegal"]
            if current_owner not in owner_options:
                owner_options.insert(0, current_owner)
            st.selectbox(
                "Owner",
                owner_options,
                index=owner_options.index(current_owner),
                key=f"{prefix}_edit_owner",
            )
            st.text_area("Reason", key=f"{prefix}_edit_reason", height=90)

        submitted = st.form_submit_button("Approve edited action and execute", type="primary")

    if st.button("Discard proposal", key=f"{prefix}_discard"):
        clear_pending_action(prefix)
        st.rerun()

    if submitted:
        try:
            edited_action = build_edited_action_from_form(pending, matter, prefix)
            post_edit_warnings = action_validation_warnings(
                edited_action,
                matter,
                st.session_state.get(f"{prefix}_pending_action_request", action_request),
            )
            if any("missing" in warning.lower() or "must use" in warning.lower() for warning in post_edit_warnings):
                for warning in post_edit_warnings:
                    st.error(warning)
                st.stop()

            result = execute_action(
                edited_action,
                st.session_state.get(f"{prefix}_pending_source_refs", []),
                original_action=pending,
            )
            st.success(result)
            clear_pending_action(prefix)
            st.rerun()
        except Exception as exc:
            st.error(f"Execution failed: {exc}")


def render_candidate_task_picker(answer: str, matter: dict[str, Any]) -> None:
    candidates = extract_task_candidates(answer)
    st.markdown("#### Quick task actions")
    if not candidates:
        st.caption("No discrete recommendations detected.")
        return

    st.caption(f"{len(candidates)} task candidate{'s' if len(candidates) != 1 else ''} found")
    source_refs = [s["source_id"] for s in st.session_state.get("last_answer_sources", [])]

    if st.button("Draft all tasks", type="primary", key="draft_all_inline_tasks"):
        set_answer_task_batch([candidate_to_task(candidate, matter) for candidate in candidates], source_refs)
        st.rerun()

    for index, candidate in enumerate(candidates):
        action = candidate_to_task(candidate, matter)
        with st.container(border=True):
            st.markdown(f"**{action['title']}**")
            st.caption(candidate)
            if st.button("Create task", key=f"candidate_task_{index}"):
                set_answer_task_batch([action], source_refs)
                st.rerun()


def render_batch_task_editor(matter: dict[str, Any]) -> None:
    batch = st.session_state.get("answer_task_batch")
    if not batch:
        return

    st.markdown("### Batch task approval")
    st.caption("Edit each task, then approve the batch. Each approved task is written separately and audited.")

    with st.form("answer_task_batch_form"):
        for index, action in enumerate(batch):
            st.markdown(f"#### Task {index + 1}")
            st.text_input("Task title", key=f"batch_title_{index}")
            assignee_options = [matter["paralegal"], matter["lead_attorney"], "Mini LOIS"]
            current_assignee = st.session_state.get(f"batch_assigned_to_{index}") or matter["paralegal"]
            if current_assignee not in assignee_options:
                assignee_options.insert(0, current_assignee)
            st.selectbox(
                "Assigned to",
                assignee_options,
                index=assignee_options.index(current_assignee),
                key=f"batch_assigned_to_{index}",
            )
            st.text_input("Due date (YYYY-MM-DD or blank)", key=f"batch_due_date_{index}")
            st.text_area("Reason", key=f"batch_reason_{index}", height=80)

        submitted = st.form_submit_button("Approve batch and create tasks", type="primary")

    if st.button("Discard batch"):
        clear_answer_task_batch()
        st.rerun()

    if submitted:
        try:
            originals = st.session_state.get("answer_task_batch_original", batch)
            source_refs = st.session_state.get("answer_task_batch_source_refs", [])
            for index, original_action in enumerate(originals):
                edited_action = {
                    "action_type": "create_task",
                    "matter_id": matter["matter_id"],
                    "title": st.session_state.get(f"batch_title_{index}", "").strip(),
                    "assigned_to": st.session_state.get(f"batch_assigned_to_{index}") or matter["paralegal"],
                    "due_date": parse_optional_date(st.session_state.get(f"batch_due_date_{index}")),
                    "reason": st.session_state.get(f"batch_reason_{index}", "").strip(),
                }
                warnings = action_validation_warnings(edited_action, matter)
                blocking = [warning for warning in warnings if "missing" in warning.lower() or "must use" in warning.lower()]
                if blocking:
                    for warning in blocking:
                        st.error(f"Task {index + 1}: {warning}")
                    st.stop()
                execute_action(edited_action, source_refs, original_action=original_action)

            st.success(f"Created {len(originals)} task(s).")
            clear_answer_task_batch()
            st.rerun()
        except Exception as exc:
            st.error(f"Batch execution failed: {exc}")


st.title("Mini LOIS: CaseOps AI")
st.caption(
    "Local prototype: matter-scoped RAG, source-cited answers, inline task extraction, editable approval, write-back, and audit trail."
)

matters = get_matters()
if not matters:
    st.error("No matters found. Check data/matters.json and restart the app.")
    st.stop()

with st.sidebar:
    st.header("Configuration")
    model = st.text_input("Ollama chat model", value=os.getenv("OLLAMA_MODEL", DEFAULT_LLM_MODEL))
    selected_label = st.selectbox("Matter scope", [matter_label(m) for m in matters])
    selected_matter_id = selected_label.split(" · ")[0]
    matter = get_matter(selected_matter_id)
    st.info("Run `python ingest.py` before asking questions so Chroma has indexed the fake matter docs.")
    st.caption("v0.4.4 adds fallback detection for matter gap tasks.")

if matter is None:
    st.error("Selected matter not found.")
    st.stop()

st.subheader(matter_label(matter))
meta_cols = st.columns(5)
meta_cols[0].markdown(f"**Type**\n\n{matter['matter_type']}")
meta_cols[1].markdown(f"**Phase**\n\n{matter['phase']}")
meta_cols[2].markdown(f"**Client**\n\n{matter['client']}")
meta_cols[3].markdown(f"**Attorney**\n\n{matter['lead_attorney']}")
meta_cols[4].markdown(f"**Paralegal**\n\n{matter['paralegal']}")

ask_tab, action_tab, record_tab, audit_tab = st.tabs(["Ask Matter", "Propose Action", "Matter Record", "Audit Log"])

with ask_tab:
    st.markdown("Ask a question. The assistant should answer only from this matter's retrieved context and cite its sources.")
    question = st.text_area(
        "Question",
        value="What documentation should we review next?",
        height=110,
    )
    if st.button("Ask Mini LOIS", type="primary"):
        try:
            answer, sources = answer_question(question=question, matter=matter, model=model)
            st.session_state["last_answer"] = answer
            st.session_state["last_answer_sources"] = sources
            st.session_state["last_question"] = question
            clear_answer_task_batch()
        except Exception as exc:
            st.error(f"Question failed: {exc}")

    if st.session_state.get("last_answer"):
        answer_col, quick_action_col = st.columns([3, 1])
        with answer_col:
            st.markdown("### Answer")
            st.write(st.session_state["last_answer"])
        with quick_action_col:
            render_candidate_task_picker(st.session_state["last_answer"], matter)

        render_batch_task_editor(matter)
        render_sources(st.session_state.get("last_answer_sources", []), heading="### Retrieved sources")

with action_tab:
    st.markdown(
        "Generate an action proposal, review validation warnings, edit the fields, then approve the final version."
    )
    action_request = st.text_area(
        "Action request",
        value="Create a task for Miguel Santos to request only the missing PT records after April 19 and the urgent care billing ledger. Do not set a due date unless the matter file gives a task deadline.",
        height=120,
    )

    if st.button("Generate action proposal"):
        try:
            action, sources = propose_action(request=action_request, matter=matter, model=model)
            store_pending_action("action", action, sources, action_request, matter)
        except Exception as exc:
            st.error(f"Action planning failed: {exc}")

    render_pending_action_editor("action", matter, action_request)

with record_tab:
    st.markdown("### Tasks")
    tasks = get_tasks(matter["matter_id"])
    st.dataframe(
        tasks,
        use_container_width=True,
        hide_index=True,
        height=180,
        column_config={
            "title": st.column_config.TextColumn("Title", width="large"),
            "reason": st.column_config.TextColumn("Reason", width="large"),
            "created_at": st.column_config.TextColumn("Created", width="medium"),
        },
    )

    st.markdown("### Notes")
    notes = get_notes(matter["matter_id"])
    st.dataframe(notes, use_container_width=True, hide_index=True, height=160)

    st.markdown("### Calendar Events")
    events = get_calendar_events(matter["matter_id"])
    st.dataframe(events, use_container_width=True, hide_index=True, height=160)

with audit_tab:
    st.markdown("Each approved action gets logged with the payload and source references.")
    logs = get_audit_log(matter["matter_id"])
    for row in logs:
        with st.expander(f"#{row['id']} · {row['action_type']} · {row['created_at']}"):
            st.write("Source refs:", row.get("source_refs"))
            try:
                st.json(json.loads(row["action_payload"]))
            except Exception:
                st.code(row["action_payload"])
