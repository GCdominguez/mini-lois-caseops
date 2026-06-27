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
from task_extractor import build_task_candidate_objects

st.set_page_config(page_title="Mini LOIS: CaseOps AI", page_icon="⚖️", layout="wide")
init_database()


def matter_label(matter: dict[str, Any]) -> str:
    return f"{matter['matter_id']} · {matter['matter_name']}"


def parse_optional_date(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if value.lower() in {"", "none", "null", "n/a"}:
        return None
    datetime.strptime(value, "%Y-%m-%d")
    return value


def candidate_object_to_task(candidate: dict[str, Any], matter: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": candidate.get("action_type", "create_task"),
        "matter_id": matter["matter_id"],
        "title": candidate.get("title", "").strip(),
        "assigned_to": matter["paralegal"],
        "due_date": None,
        "reason": candidate.get("reason") or f"Created from Mini LOIS answer recommendation: {candidate.get('original_text', '')}",
    }


def validation_warnings(action: dict[str, Any], matter: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if action.get("matter_id") != matter["matter_id"]:
        warnings.append("Matter ID does not match the selected matter.")
    if action.get("action_type") == "create_task" and not action.get("title"):
        warnings.append("Task title is missing.")
    assignee = action.get("assigned_to")
    if assignee and assignee not in {matter["paralegal"], matter["lead_attorney"], "Mini LOIS"}:
        warnings.append("Assignee is not listed in this matter's metadata.")
    due_date = action.get("due_date")
    if due_date:
        parsed_due = datetime.strptime(str(due_date), "%Y-%m-%d").date()
        if parsed_due < date.today():
            warnings.append("Due date is in the past.")
    return warnings


def source_ids() -> list[str]:
    return [source["source_id"] for source in st.session_state.get("last_answer_sources", [])]


def set_batch(actions: list[dict[str, Any]], refs: list[str]) -> None:
    st.session_state["answer_task_batch"] = actions
    st.session_state["answer_task_batch_original"] = [dict(action) for action in actions]
    st.session_state["answer_task_batch_source_refs"] = refs
    for index, action in enumerate(actions):
        st.session_state[f"batch_title_{index}"] = action.get("title", "")
        st.session_state[f"batch_assigned_to_{index}"] = action.get("assigned_to")
        st.session_state[f"batch_due_date_{index}"] = "" if action.get("due_date") is None else str(action.get("due_date"))
        st.session_state[f"batch_reason_{index}"] = action.get("reason", "")


def clear_batch() -> None:
    for index in range(len(st.session_state.get("answer_task_batch", []))):
        for suffix in ("title", "assigned_to", "due_date", "reason"):
            st.session_state.pop(f"batch_{suffix}_{index}", None)
    for key in ("answer_task_batch", "answer_task_batch_original", "answer_task_batch_source_refs"):
        st.session_state.pop(key, None)


def render_sources(sources: list[dict[str, Any]]) -> None:
    st.markdown("### Retrieved sources")
    for source in sources:
        with st.expander(f"{source['source_id']} · {source['source_file']} · chunk {source['chunk_index']}"):
            st.write(source["text"])


def render_quick_actions(answer: str, matter: dict[str, Any], sources: list[dict[str, Any]], model: str) -> None:
    candidates = build_task_candidate_objects(answer, sources, model=model)
    st.markdown("#### Quick task actions")
    if not candidates:
        st.caption("No discrete recommendations detected.")
        return

    st.caption(f"{len(candidates)} task candidate{'s' if len(candidates) != 1 else ''} found")
    if st.button("Draft all tasks", type="primary", key="draft_all_inline_tasks"):
        set_batch([candidate_object_to_task(candidate, matter) for candidate in candidates], source_ids())
        st.rerun()

    for index, candidate in enumerate(candidates):
        action = candidate_object_to_task(candidate, matter)
        with st.container(border=True):
            st.markdown(f"**{candidate['title']}**")
            st.caption(candidate.get("reason", ""))
            with st.expander("Details"):
                st.write("Confidence:", candidate.get("confidence", "unknown"))
                st.write("Original text:", candidate.get("original_text", ""))
                st.write("Source refs:", candidate.get("source_refs", []))
            if st.button("Create task", key=f"candidate_task_{index}"):
                set_batch([action], source_ids())
                st.rerun()


def render_batch_editor(matter: dict[str, Any]) -> None:
    batch = st.session_state.get("answer_task_batch")
    if not batch:
        return

    st.markdown("### Batch task approval")
    st.caption("Edit each task, then approve the batch. Nothing writes until approval.")
    with st.form("answer_task_batch_form"):
        for index, _action in enumerate(batch):
            st.markdown(f"#### Task {index + 1}")
            st.text_input("Task title", key=f"batch_title_{index}")
            assignee_options = [matter["paralegal"], matter["lead_attorney"], "Mini LOIS"]
            current = st.session_state.get(f"batch_assigned_to_{index}") or matter["paralegal"]
            if current not in assignee_options:
                assignee_options.insert(0, current)
            st.selectbox("Assigned to", assignee_options, index=assignee_options.index(current), key=f"batch_assigned_to_{index}")
            st.text_input("Due date (YYYY-MM-DD or blank)", key=f"batch_due_date_{index}")
            st.text_area("Reason", key=f"batch_reason_{index}", height=80)
        approved = st.form_submit_button("Approve batch and create tasks", type="primary")

    if st.button("Discard batch"):
        clear_batch()
        st.rerun()

    if approved:
        try:
            originals = st.session_state.get("answer_task_batch_original", batch)
            refs = st.session_state.get("answer_task_batch_source_refs", [])
            for index, original in enumerate(originals):
                edited = {
                    "action_type": "create_task",
                    "matter_id": matter["matter_id"],
                    "title": st.session_state.get(f"batch_title_{index}", "").strip(),
                    "assigned_to": st.session_state.get(f"batch_assigned_to_{index}") or matter["paralegal"],
                    "due_date": parse_optional_date(st.session_state.get(f"batch_due_date_{index}")),
                    "reason": st.session_state.get(f"batch_reason_{index}", "").strip(),
                }
                blocking = [warning for warning in validation_warnings(edited, matter) if "missing" in warning.lower()]
                if blocking:
                    for warning in blocking:
                        st.error(f"Task {index + 1}: {warning}")
                    st.stop()
                execute_action(edited, refs, original_action=original)
            st.success(f"Created {len(originals)} task(s).")
            clear_batch()
            st.rerun()
        except Exception as exc:
            st.error(f"Batch execution failed: {exc}")


def render_action_editor(action: dict[str, Any], sources: list[dict[str, Any]], matter: dict[str, Any]) -> None:
    st.markdown("### Model proposal")
    st.json(action)
    for warning in validation_warnings(action, matter):
        st.warning(warning)

    with st.form("single_action_form"):
        st.text_input("Task title", key="single_title", value=action.get("title", ""))
        st.selectbox("Assigned to", [matter["paralegal"], matter["lead_attorney"], "Mini LOIS"], key="single_assigned_to")
        st.text_input("Due date (YYYY-MM-DD or blank)", key="single_due_date", value="" if action.get("due_date") is None else str(action.get("due_date")))
        st.text_area("Reason", key="single_reason", value=action.get("reason", ""), height=80)
        approved = st.form_submit_button("Approve edited action and execute", type="primary")

    if approved:
        edited = {
            "action_type": "create_task",
            "matter_id": matter["matter_id"],
            "title": st.session_state["single_title"].strip(),
            "assigned_to": st.session_state["single_assigned_to"],
            "due_date": parse_optional_date(st.session_state["single_due_date"]),
            "reason": st.session_state["single_reason"].strip(),
        }
        execute_action(edited, [source["source_id"] for source in sources], original_action=action)
        st.success("Task created.")
        st.session_state.pop("pending_action", None)
        st.rerun()


st.title("Mini LOIS: CaseOps AI")
st.caption("Local prototype: matter-scoped RAG, source-cited answers, model-assisted structured task candidates, editable approval, write-back, and audit trail.")

matters = get_matters()
if not matters:
    st.error("No matters found. Check data/matters.json and restart the app.")
    st.stop()

with st.sidebar:
    st.header("Configuration")
    model = st.text_input("Ollama chat model", value=os.getenv("OLLAMA_MODEL", DEFAULT_LLM_MODEL))
    selected_label = st.selectbox("Matter scope", [matter_label(item) for item in matters])
    selected_matter_id = selected_label.split(" · ")[0]
    matter = get_matter(selected_matter_id)
    st.info("Run `python ingest.py` before asking questions so Chroma has indexed the fake matter docs.")
    st.caption("v0.5.4 uses the shared API-style task candidate contract in the UI.")

if matter is None:
    st.error("Selected matter not found.")
    st.stop()

st.subheader(matter_label(matter))
cols = st.columns(5)
cols[0].markdown(f"**Type**\n\n{matter['matter_type']}")
cols[1].markdown(f"**Phase**\n\n{matter['phase']}")
cols[2].markdown(f"**Client**\n\n{matter['client']}")
cols[3].markdown(f"**Attorney**\n\n{matter['lead_attorney']}")
cols[4].markdown(f"**Paralegal**\n\n{matter['paralegal']}")

ask_tab, action_tab, record_tab, audit_tab = st.tabs(["Ask Matter", "Propose Action", "Matter Record", "Audit Log"])

with ask_tab:
    st.markdown("Ask a question. The assistant should answer only from this matter's retrieved context and cite its sources.")
    question = st.text_area("Question", value="What documentation should we review next?", height=110)
    if st.button("Ask Mini LOIS", type="primary"):
        try:
            answer, sources = answer_question(question=question, matter=matter, model=model)
            st.session_state["last_answer"] = answer
            st.session_state["last_answer_sources"] = sources
            st.session_state["last_question"] = question
            clear_batch()
        except Exception as exc:
            st.error(f"Question failed: {exc}")

    if st.session_state.get("last_answer"):
        answer_col, actions_col = st.columns([3, 1])
        with answer_col:
            st.markdown("### Answer")
            st.write(st.session_state["last_answer"])
        with actions_col:
            render_quick_actions(
                st.session_state["last_answer"],
                matter,
                st.session_state.get("last_answer_sources", []),
                model,
            )
        render_batch_editor(matter)
        render_sources(st.session_state.get("last_answer_sources", []))

with action_tab:
    st.markdown("Generate an action proposal, edit the fields, then approve the final version.")
    request = st.text_area(
        "Action request",
        value="Create a task for Miguel Santos to request only the missing PT records after April 19 and the urgent care billing ledger. Do not set a due date unless the matter file gives a task deadline.",
        height=120,
    )
    if st.button("Generate action proposal"):
        try:
            action, sources = propose_action(request=request, matter=matter, model=model)
            if action.get("action_type") != "create_task":
                st.warning("This compact editor currently supports create_task approvals.")
            st.session_state["pending_action"] = action
            st.session_state["pending_action_sources"] = sources
        except Exception as exc:
            st.error(f"Action planning failed: {exc}")
    if st.session_state.get("pending_action"):
        render_action_editor(st.session_state["pending_action"], st.session_state.get("pending_action_sources", []), matter)

with record_tab:
    st.markdown("### Tasks")
    st.dataframe(get_tasks(matter["matter_id"]), use_container_width=True, hide_index=True, height=180)
    st.markdown("### Notes")
    st.dataframe(get_notes(matter["matter_id"]), use_container_width=True, hide_index=True, height=160)
    st.markdown("### Calendar Events")
    st.dataframe(get_calendar_events(matter["matter_id"]), use_container_width=True, hide_index=True, height=160)

with audit_tab:
    st.markdown("Each approved action gets logged with the payload and source references.")
    for row in get_audit_log(matter["matter_id"]):
        with st.expander(f"#{row['id']} · {row['action_type']} · {row['created_at']}"):
            st.write("Source refs:", row.get("source_refs"))
            try:
                st.json(json.loads(row["action_payload"]))
            except Exception:
                st.code(row["action_payload"])
