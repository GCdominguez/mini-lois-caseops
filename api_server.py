from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from actions import propose_action
from matter_store import (
    execute_action,
    get_audit_log,
    get_idempotent_response,
    get_matter,
    get_matters,
    get_tasks,
    get_webhook_events,
    import_external_matter,
    init_database,
    store_idempotent_response,
)
from rag import DEFAULT_LLM_MODEL, answer_question
from task_extractor import build_task_candidate_objects

API_KEY = os.getenv("MINI_LOIS_API_KEY", "demo-key")
API_VERSION = "0.7.0"

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

    request_payload = payload.dict()
    endpoint = "/v1/actions/approve"
    if idempotency_key:
        try:
            prior_response = get_idempotent_response(
                key=idempotency_key,
                endpoint=endpoint,
                request_payload=request_payload,
            )
        except ValueError as exc:
            raise_api_error(
                409,
                request=request,
                error="idempotency_conflict",
                message=str(exc),
                details={"idempotency_key": idempotency_key},
            )
        if prior_response is not None:
            prior_response["idempotency"] = {"key": idempotency_key, "replayed": True}
            return prior_response

    try:
        result = execute_action(action, payload.source_refs, original_action=payload.original_model_proposal)
    except ValueError as exc:
        raise_api_error(
            400,
            request=request,
            error="unsupported_action",
            message=str(exc),
        )

    response_payload: dict[str, Any] = {
        "status": "executed",
        "result": result,
        "approved_action": action,
        "idempotency": {"applied": False},
    }
    if idempotency_key:
        response_payload["idempotency"] = {"key": idempotency_key, "replayed": False}
        store_idempotent_response(
            key=idempotency_key,
            endpoint=endpoint,
            request_payload=request_payload,
            response_payload=response_payload,
        )
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
        return import_external_matter(payload.dict(exclude_none=True))
    except ValueError as exc:
        raise_api_error(
            400,
            request=request,
            error="import_validation_error",
            message=str(exc),
        )
