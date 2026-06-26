from __future__ import annotations

import json
import os
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


st.title("Mini LOIS: CaseOps AI")
st.caption("Local prototype: matter-scoped RAG, source-cited answers, action proposals, approved write-back, and audit trail.")

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

if matter is None:
    st.error("Selected matter not found.")
    st.stop()

st.subheader(matter_label(matter))
cols = st.columns(5)
cols[0].metric("Type", matter["matter_type"])
cols[1].metric("Phase", matter["phase"])
cols[2].metric("Client", matter["client"])
cols[3].metric("Attorney", matter["lead_attorney"])
cols[4].metric("Paralegal", matter["paralegal"])

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
    st.markdown("Ask for an action. The model proposes JSON only. Nothing changes until you approve execution.")
    action_request = st.text_area(
        "Action request",
        value="Create a task for the paralegal based on the most important missing item.",
        height=110,
    )
    if st.button("Generate action proposal"):
        try:
            action, sources = propose_action(request=action_request, matter=matter, model=model)
            st.session_state["pending_action"] = action
            st.session_state["pending_source_refs"] = [s["source_id"] for s in sources]
            st.markdown("### Proposed action")
            st.json(action)
            st.markdown("### Evidence used")
            for source in sources:
                with st.expander(f"{source['source_id']} · {source['source_file']} · chunk {source['chunk_index']}"):
                    st.write(source["text"])
        except Exception as exc:
            st.error(f"Action planning failed: {exc}")

    pending = st.session_state.get("pending_action")
    if pending:
        st.warning("Approval gate: executing this will write to the local SQLite matter record and audit log.")
        st.json(pending)
        if st.button("Approve and execute action", type="primary"):
            try:
                result = execute_action(pending, st.session_state.get("pending_source_refs", []))
                st.success(result)
                del st.session_state["pending_action"]
                st.session_state.pop("pending_source_refs", None)
            except Exception as exc:
                st.error(f"Execution failed: {exc}")

with record_tab:
    st.markdown("### Tasks")
    tasks = get_tasks(matter["matter_id"])
    st.dataframe(tasks, use_container_width=True, hide_index=True)

    st.markdown("### Notes")
    notes = get_notes(matter["matter_id"])
    st.dataframe(notes, use_container_width=True, hide_index=True)

    st.markdown("### Calendar Events")
    events = get_calendar_events(matter["matter_id"])
    st.dataframe(events, use_container_width=True, hide_index=True)

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
