from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from actions import propose_action
from matter_store import (
    execute_action,
    execute_action_idempotently,
    get_audit_log,
    get_matter,
    get_matters,
    get_tasks,
    get_webhook_events,
    import_external_matter,
    init_database,
)
from rag import DEFAULT_LLM_MODEL, answer_question
from task_extractor import build_task_candidate_objects

API_KEY = os.getenv("MINI_LOIS_API_KEY", "demo-key")
API_VERSION = "0.8.0"
ALLOWED_ACTION_TYPES = {"create_task", "add_note", "create_calendar_event"}

app = FastAPI(title="Mini LOIS CaseOps API", version=API_VERSION)
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


class DataBridgeImportRequest(BaseModel):
    external_system: str = "demo_external_system"
    external_matter_id: Optional[str] = None
    external_case_id: Optional[str] = None
    matter_id: Optional[str] = None
    matter_name: Optional[str] = None
    matter_type: Optional[str] = None
    case_type: Optional[str] = None
    client: Optional[str] = None
    client_full_name: Optional[str] = None
    phase: Optional[str] = None
    lead_attorney: Optional[str] = None
    paralegal: Optional[str] = None
    status: Optional[str] = None
    open_date: Optional[str] = None


def request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid4())


def error_payload(
    *,
    request: Request,
    error: str,
    message: str,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
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
    details: Optional[Any] = None,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=error_payload(request=request, error=error, message=message, details=details),
    )


def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
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


def _required_text(action: Dict[str, Any], field: str) -> Optional[str]:
    value = action.get(field)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _optional_date(action: Dict[str, Any], field: str, request: Request) -> Optional[str]:
    value = action.get(field)
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise_api_error(
            400,
            request=request,
            error="action_validation_error",
            message=f"approved_action.{field} must use YYYY-MM-DD format.",
            details={"field": field, "value": value},
        )
    return value


def validate_approved_action(action: Dict[str, Any], request: Request) -> Dict[str, Any]:
    action_type = _required_text(action, "action_type")
    matter_id = _required_text(action, "matter_id")
    if not matter_id:
        raise_api_error(
            400,
            request=request,
            error="missing_matter_id",
            message="approved_action.matter_id is required before an action can be approved.",
        )
    if action_type not in ALLOWED_ACTION_TYPES:
        raise_api_error(
            400,
            request=request,
            error="unsupported_action",
            message=f"Unsupported action_type: {action_type}",
            details={"allowed_action_types": sorted(ALLOWED_ACTION_TYPES)},
        )

    get_existing_matter_or_404(matter_id, request)

    normalized = dict(action)
    normalized["action_type"] = action_type
    normalized["matter_id"] = matter_id

    if action_type == "create_task":
        title = _required_text(action, "title")
        if not title:
            raise_api_error(
                400,
                request=request,
                error="action_validation_error",
                message="approved_action.title is required for create_task.",
                details={"field": "title", "action_type": action_type},
            )
        normalized["title"] = title
        normalized["due_date"] = _optional_date(action, "due_date", request)
    elif action_type == "add_note":
        note_text = _required_text(action, "note_text")
        if not note_text:
            raise_api_error(
                400,
                request=request,
                error="action_validation_error",
                message="approved_action.note_text is required for add_note.",
                details={"field": "note_text", "action_type": action_type},
            )
        normalized["note_text"] = note_text
    elif action_type == "create_calendar_event":
        title = _required_text(action, "title")
        event_date = _optional_date(action, "event_date", request)
        if not title or not event_date:
            raise_api_error(
                400,
                request=request,
                error="action_validation_error",
                message="approved_action.title and approved_action.event_date are required for create_calendar_event.",
                details={"required_fields": ["title", "event_date"], "action_type": action_type},
            )
        normalized["title"] = title
        normalized["event_date"] = event_date

    return normalized


@app.get("/v1/health")
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": API_VERSION}


@app.get("/v1/matters")
@app.get("/matters")
def list_matters(_api_key: str = Depends(require_api_key)) -> List[Dict[str, Any]]:
    return get_matters()


@app.get("/v1/matters/{matter_id}")
@app.get("/matters/{matter_id}")
def read_matter(
    matter_id: str,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    return get_existing_matter_or_404(matter_id, request)


@app.get("/v1/matters/{matter_id}/tasks")
@app.get("/matters/{matter_id}/tasks")
def read_tasks(
    matter_id: str,
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    get_existing_matter_or_404(matter_id, request)
    return get_tasks(matter_id, status=status, limit=limit, offset=offset)


@app.post("/v1/matters/{matter_id}/ask")
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


@app.post("/v1/matters/{matter_id}/actions/propose")
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


def _approve_action_impl(
    payload: ApproveRequest,
    request: Request,
    idempotency_key: Optional[str],
) -> Dict[str, Any]:
    action = validate_approved_action(payload.approved_action, request)
    request_payload = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    request_payload["approved_action"] = action
    endpoint = "/v1/actions/approve"
    if idempotency_key:
        try:
            response_payload, replayed = execute_action_idempotently(
                key=idempotency_key,
                endpoint=endpoint,
                request_payload=request_payload,
                action=action,
                source_refs=payload.source_refs,
                original_action=payload.original_model_proposal,
            )
        except ValueError as exc:
            raise_api_error(
                409,
                request=request,
                error="idempotency_conflict",
                message=str(exc),
                details={"idempotency_key": idempotency_key},
            )
        response_payload["idempotency"] = {"key": idempotency_key, "replayed": replayed}
        return response_payload

    try:
        result = execute_action(action, payload.source_refs, original_action=payload.original_model_proposal)
    except ValueError as exc:
        raise_api_error(
            400,
            request=request,
            error="unsupported_action",
            message=str(exc),
        )

    response_payload: Dict[str, Any] = {
        "status": "executed",
        "result": result,
        "approved_action": action,
        "idempotency": {"applied": False},
    }
    return response_payload


@app.post("/v1/actions/approve")
@app.post("/actions/approve")
def approve_action(
    payload: ApproveRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    return _approve_action_impl(payload, request, idempotency_key)


@app.get("/v1/matters/{matter_id}/audit")
@app.get("/matters/{matter_id}/audit")
def audit_log(
    matter_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    get_existing_matter_or_404(matter_id, request)
    return get_audit_log(matter_id, limit=limit, offset=offset)


@app.get("/v1/webhook-events")
@app.get("/webhook-events")
def list_webhook_events(
    event_type: Optional[str] = Query(default=None),
    delivery_status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    return get_webhook_events(
        event_type=event_type,
        delivery_status=delivery_status,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/matters/{matter_id}/webhook-events")
@app.get("/matters/{matter_id}/webhook-events")
def matter_webhook_events(
    matter_id: str,
    request: Request,
    event_type: Optional[str] = Query(default=None),
    delivery_status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _api_key: str = Depends(require_api_key),
) -> List[Dict[str, Any]]:
    get_existing_matter_or_404(matter_id, request)
    return get_webhook_events(
        matter_id=matter_id,
        event_type=event_type,
        delivery_status=delivery_status,
        limit=limit,
        offset=offset,
    )


@app.post("/v1/databridge/import")
def databridge_import(
    payload: DataBridgeImportRequest,
    request: Request,
    _api_key: str = Depends(require_api_key),
) -> Dict[str, Any]:
    try:
        payload_dict = (
            payload.model_dump(exclude_none=True)
            if hasattr(payload, "model_dump")
            else payload.dict(exclude_none=True)
        )
        return import_external_matter(payload_dict)
    except ValueError as exc:
        raise_api_error(
            400,
            request=request,
            error="import_validation_error",
            message=str(exc),
        )
