from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from actions import propose_action
from matter_store import execute_action, get_audit_log, get_matter, get_matters, get_tasks, init_database
from rag import DEFAULT_LLM_MODEL, answer_question
from task_extractor import extract_task_candidates

app = FastAPI(title="Mini LOIS CaseOps API", version="0.5.0")
init_database()


class AskRequest(BaseModel):
    question: str
    model: str = DEFAULT_LLM_MODEL


class ProposeRequest(BaseModel):
    request: str
    model: str = DEFAULT_LLM_MODEL


class ApproveRequest(BaseModel):
    approved_action: dict[str, Any]
    source_refs: list[str] = []
    original_model_proposal: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/matters")
def list_matters() -> list[dict[str, Any]]:
    return get_matters()


@app.get("/matters/{matter_id}")
def read_matter(matter_id: str) -> dict[str, Any]:
    matter = get_matter(matter_id)
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    return matter


@app.get("/matters/{matter_id}/tasks")
def read_tasks(matter_id: str) -> list[dict[str, Any]]:
    if get_matter(matter_id) is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    return get_tasks(matter_id)


@app.post("/matters/{matter_id}/ask")
def ask_matter(matter_id: str, payload: AskRequest) -> dict[str, Any]:
    matter = get_matter(matter_id)
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    answer, sources = answer_question(payload.question, matter, model=payload.model)
    return {
        "matter_id": matter_id,
        "question": payload.question,
        "answer": answer,
        "sources": sources,
        "task_candidates": extract_task_candidates(answer),
    }


@app.post("/matters/{matter_id}/actions/propose")
def propose_matter_action(matter_id: str, payload: ProposeRequest) -> dict[str, Any]:
    matter = get_matter(matter_id)
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    action, sources = propose_action(payload.request, matter, model=payload.model)
    return {
        "proposed_action": action,
        "source_refs": [source["source_id"] for source in sources],
        "sources": sources,
        "requires_approval": True,
    }


@app.post("/actions/approve")
def approve_action(payload: ApproveRequest) -> dict[str, Any]:
    action = payload.approved_action
    matter_id = action.get("matter_id")
    if not matter_id or get_matter(matter_id) is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    result = execute_action(action, payload.source_refs, original_action=payload.original_model_proposal)
    return {"status": "executed", "result": result, "approved_action": action}


@app.get("/matters/{matter_id}/audit")
def audit_log(matter_id: str) -> list[dict[str, Any]]:
    if get_matter(matter_id) is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    return get_audit_log(matter_id)
