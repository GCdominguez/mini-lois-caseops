from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from actions import propose_action
from matter_store import (
    execute_action,
    get_audit_log,
    get_matter,
    get_matters,
    get_tasks,
    get_webhook_events,
    init_database,
)
from rag import DEFAULT_LLM_MODEL, answer_question
from task_extractor import build_task_candidate_objects

API_KEY = os.getenv("MINI_LOIS_API_KEY", "demo-key")

app = FastAPI(title="Mini LOIS CaseOps API", version="0.6.0")
init_database()


class AskRequest(BaseModel):
    question: str
    model: str = DEFAULT_LLM_MODEL


class ProposeRequest(BaseModel):
    request: str
    model: str = DEFAULT_LLM_MODEL


class ApproveRequest(BaseModel):
    approved_action: Dict[str, Any]
    source_refs: List[str] = Field(default_factory=list)
    original_model_proposal: Optional[Dict[str, Any]] = None


def request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid4())


def error_payload(
    *,
    request: Request,
    error: str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": error,
        "message": message,
        "request_id": request_id(request),
    }
    if details is not None:
        payload["details"] = details
    return payload


def raise_api_error(
    status_code: int,
    *,
    request: Request,
    error: str,
    message: str,
    details: Any | None = None,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=error_payload(request=request, error=error, message=message, details=details),
    )


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    if x_api_key != API_KEY:
        raise_api_error(
            401,
            request=request,
            error="unauthorized",
            message="Missing or invalid API key. Send X-API-Key: demo-key for the local prototype.",
        )
    return x_api_key


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            request=request,
            error="http_error",
            message=str(exc.detail),
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            request=request,
            error="validation_error",
            message="The request path, query parameters, or JSON body failed validation.",
            details=exc.errors(),
        ),
    )


def get_existing_matter_or_404(matter_id: str, request: Request) -> dict[str, Any]:
    matter = get_matter(matter_id)
    if matter is None:
        raise_api_error(
            404,
            request=request,
            error="matter_not_found",
            message=f"No matter exists for matter_id '{matter_id}'.",
            details={"matter_id": matter_id},
        )
    return matter


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": "0.6.0"}


@app.get("/matters")
def list_matters(_api_key: str = Depends(require_api_key)) -> List[Dict[str, Any]]:
    return get_matters()


@app.get("/matters/{matter_id}")
def read_matter(
    matter_id: str,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    return get_existing_matter_or_404(matter_id, request)


@app.get("/matters/{matter_id}/tasks")
def read_tasks(
    matter_id: str,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    get_existing_matter_or_404(matter_id, request)
    return get_tasks(matter_id)


@app.post("/matters/{matter_id}/ask")
def ask_matter(
    matter_id: str,
    payload: AskRequest,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    matter = get_existing_matter_or_404(matter_id, request)
    answer, sources = answer_question(payload.question, matter, model=payload.model)
    return {
        "matter_id": matter_id,
        "question": payload.question,
        "answer": answer,
        "sources": sources,
        "task_candidates": build_task_candidate_objects(
            answer,
            sources,
            model=payload.model,
            question=payload.question,
        ),
    }


@app.post("/matters/{matter_id}/actions/propose")
def propose_matter_action(
    matter_id: str,
    payload: ProposeRequest,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    matter = get_existing_matter_or_404(matter_id, request)
    action, sources = propose_action(payload.request, matter, model=payload.model)
    return {
        "proposed_action": action,
        "source_refs": [source["source_id"] for source in sources],
        "sources": sources,
        "requires_approval": True,
    }


@app.post("/actions/approve")
def approve_action(
    payload: ApproveRequest,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    action = payload.approved_action
    matter_id = action.get("matter_id")
    if not matter_id:
        raise_api_error(
            400,
            request=request,
            error="missing_matter_id",
            message="approved_action.matter_id is required before an action can be approved.",
        )
    get_existing_matter_or_404(str(matter_id), request)
    try:
        result = execute_action(action, payload.source_refs, original_action=payload.original_model_proposal)
    except ValueError as exc:
        raise_api_error(
            400,
            request=request,
            error="unsupported_action",
            message=str(exc),
        )
    return {"status": "executed", "result": result, "approved_action": action}


@app.get("/matters/{matter_id}/audit")
def audit_log(
    matter_id: str,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    get_existing_matter_or_404(matter_id, request)
    return get_audit_log(matter_id)


@app.get("/webhook-events")
def list_webhook_events(_api_key: str = Depends(require_api_key)) -> List[Dict[str, Any]]:
    return get_webhook_events()


@app.get("/matters/{matter_id}/webhook-events")
def matter_webhook_events(
    matter_id: str,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    get_existing_matter_or_404(matter_id, request)
    return get_webhook_events(matter_id)
