from __future__ import annotations

import json
import os
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


def render_sources(sources: list[dict[str, Any]]) -> None:
    st.markdown("### Evidence used")
    for source in sources:
        with st.expander(f"{source['source_id']} · {source['source_file']} · chunk {source['chunk_index']}"):
            st.write(source["text"])


def build_edited_action_from_form(pending: dict[str, Any], matter: dict[str, Any]) -> dict[str, Any]:
    action_type = pending.get("action_type")

    if action_type == "create_task":
        return {
            "action_type": "create_task",
            "matter_id": matter["matter_id"],
            "title": st.session_state.get("edit_title", "").strip(),
            "assigned_to": st.session_state.get("edit_assigned_to") or None,
            "due_date": parse_optional_date(st.session_state.get("edit_due_date")),
            "reason": st.session_state.get("edit_reason", "").strip(),
        }

    if action_type == "add_note":
        return {
            "action_type": "add_note",
            "matter_id": matter["matter_id"],
            "note_text": st.session_state.get("edit_note_text", "").strip(),
            "author": st.session_state.get("edit_author", "Mini LOIS").strip() or "Mini LOIS",
            "reason": st.session_state.get("edit_reason", "").strip(),
        }

    if action_type == "create_calendar_event":
        return {
            "action_type": "create_calendar_event",
            "matter_id": matter["matter_id"],
            "title": st.session_state.get("edit_title", "").strip(),
            "event_date": parse_optional_date(st.session_state.get("edit_event_date")),
            "owner": st.session_state.get("edit_owner") or None,
            "reason": st.session_state.get("edit_reason", "").strip(),
        }

    raise ValueError(f"Unsupported action_type: {action_type}")


def clear_pending_action() -> None:
    for key in [
        "pending_action",
        "pending_source_refs",
        "pending_sources",
        "pending_action_request",
        "edit_title",
        "edit_assigned_to",
        "edit_due_date",
        "edit_reason",
        "edit_note_text",
        "edit_author",
        "edit_event_date",
        "edit_owner",
    ]:
        st.session_state.pop(key, None)


st.title("Mini LOIS: CaseOps AI")
st.caption(
    "Local prototype: matter-scoped RAG, source-cited answers, editable action approval, approved write-back, and audit trail."
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
    st.caption("v0.2 adds editable action approval and validation warnings.")

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
        value="What are the key risks and next steps in this matter?",
        height=110,
    )
    if st.button("Ask Mini LOIS", type="primary"):
        try:
            answer, sources = answer_question(question=question, matter=matter, model=model)
            st.markdown("### Answer")
            st.write(answer)
            st.markdown("### Retrieved sources")
            for source in sources:
                with st.expander(f"{source['source_id']} · {source['source_file']} · chunk {source['chunk_index']}"):
                    st.write(source["text"])
        except Exception as exc:
            st.error(f"Question failed: {exc}")

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
            st.session_state["pending_action"] = action
            st.session_state["pending_source_refs"] = [s["source_id"] for s in sources]
            st.session_state["pending_sources"] = sources
            st.session_state["pending_action_request"] = action_request

            st.session_state["edit_title"] = action.get("title", "")
            st.session_state["edit_assigned_to"] = action.get("assigned_to") or matter["paralegal"]
            st.session_state["edit_due_date"] = "" if action.get("due_date") is None else str(action.get("due_date"))
            st.session_state["edit_reason"] = action.get("reason", "")
            st.session_state["edit_note_text"] = action.get("note_text", "")
            st.session_state["edit_author"] = action.get("author", "Mini LOIS")
            st.session_state["edit_event_date"] = "" if action.get("event_date") is None else str(action.get("event_date"))
            st.session_state["edit_owner"] = action.get("owner") or matter["paralegal"]
        except Exception as exc:
            st.error(f"Action planning failed: {exc}")

    pending = st.session_state.get("pending_action")
    if pending:
        st.markdown("### Model proposal")
        st.json(pending)

        warnings = action_validation_warnings(
            pending,
            matter,
            st.session_state.get("pending_action_request", action_request),
        )
        if warnings:
            st.markdown("### Validation warnings")
            for warning in warnings:
                st.warning(warning)
        else:
            st.success("No validation warnings on the model proposal.")

        sources = st.session_state.get("pending_sources", [])
        if sources:
            render_sources(sources)

        st.markdown("### Edit before approval")
        st.caption("The audit log stores both the original model proposal and the approved action when edited.")

        with st.form("approve_action_form"):
            st.text_input("Action type", value=pending.get("action_type", ""), disabled=True)
            st.text_input("Matter ID", value=matter["matter_id"], disabled=True)

            if pending.get("action_type") == "create_task":
                st.text_input("Task title", key="edit_title")
                assignee_options = [matter["paralegal"], matter["lead_attorney"], "Mini LOIS"]
                current_assignee = st.session_state.get("edit_assigned_to") or matter["paralegal"]
                if current_assignee not in assignee_options:
                    assignee_options.insert(0, current_assignee)
                st.selectbox(
                    "Assigned to",
                    assignee_options,
                    index=assignee_options.index(current_assignee),
                    key="edit_assigned_to",
                )
                st.text_input("Due date (YYYY-MM-DD or blank)", key="edit_due_date")
                st.text_area("Reason", key="edit_reason", height=90)

            elif pending.get("action_type") == "add_note":
                st.text_area("Note text", key="edit_note_text", height=120)
                st.text_input("Author", key="edit_author")
                st.text_area("Reason", key="edit_reason", height=90)

            elif pending.get("action_type") == "create_calendar_event":
                st.text_input("Event title", key="edit_title")
                st.text_input("Event date (YYYY-MM-DD)", key="edit_event_date")
                owner_options = [matter["paralegal"], matter["lead_attorney"], "Mini LOIS"]
                current_owner = st.session_state.get("edit_owner") or matter["paralegal"]
                if current_owner not in owner_options:
                    owner_options.insert(0, current_owner)
                st.selectbox(
                    "Owner",
                    owner_options,
                    index=owner_options.index(current_owner),
                    key="edit_owner",
                )
                st.text_area("Reason", key="edit_reason", height=90)

            submitted = st.form_submit_button("Approve edited action and execute", type="primary")

        col_a, col_b = st.columns([1, 4])
        with col_a:
            if st.button("Discard proposal"):
                clear_pending_action()
                st.rerun()

        if submitted:
            try:
                edited_action = build_edited_action_from_form(pending, matter)
                post_edit_warnings = action_validation_warnings(
                    edited_action,
                    matter,
                    st.session_state.get("pending_action_request", action_request),
                )
                if any("missing" in warning.lower() or "must use" in warning.lower() for warning in post_edit_warnings):
                    for warning in post_edit_warnings:
                        st.error(warning)
                    st.stop()

                result = execute_action(
                    edited_action,
                    st.session_state.get("pending_source_refs", []),
                    original_action=pending,
                )
                st.success(result)
                clear_pending_action()
                st.rerun()
            except Exception as exc:
                st.error(f"Execution failed: {exc}")

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
