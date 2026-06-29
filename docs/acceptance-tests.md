# Acceptance Tests

These tests define expected behavior for the AI-assisted matter action workflow and API layer. v0.8 includes automated smoke coverage in `tests/test_api_v08.py`; the cases below remain useful as manual demo checks.

## Test group 1: API startup and auth

### Test 1.1: API import check

**Given** the virtual environment is active

**When** `python -c "import api_server; print(api_server.health())"` is run

**Then** the command succeeds

**And** the output includes:

```json
{"status": "ok", "version": "0.8.0"}
```

### Test 1.2: Health check

**Given** the API server is running

**When** `GET /v1/health` is called

**Then** the response is 200

**And** the body includes `status` and `version`.

### Test 1.3: Protected endpoints require API key

**When** `GET /v1/matters` is called without `X-API-Key`

**Then** the response is 401

**And** the error code is `unauthorized`.

### Test 1.4: List matters

**When** `GET /v1/matters` is called with `X-API-Key: demo-key`

**Then** the response is 200

**And** the response includes `MAT-1001`.

## Test group 2: Ask Matter API

### Test 2.1: Ask valid matter question

**Given** Ollama is running

**And** Chroma has indexed the fake matter documents

**When** `POST /v1/matters/MAT-1001/ask` is called with:

```json
{
  "question": "Give me some context on the case",
  "model": "llama3.2"
}
```

**Then** the response is 200

**And** the response includes `answer`, `sources`, and `task_candidates`.

### Test 2.2: Missing request field

**When** `/v1/matters/MAT-1001/ask` is called with `request` instead of `question`

**Then** the response is 422

**And** the error code is `validation_error`.

### Test 2.3: Invalid matter for ask

**When** `POST /v1/matters/MAT-9999/ask` is called

**Then** the response is 404

**And** the error code is `matter_not_found`.

## Test group 3: Approval and write-back

### Test 3.1: Approve create_task action with idempotency

**Given** a valid approved action payload:

```json
{
  "approved_action": {
    "action_type": "create_task",
    "matter_id": "MAT-1001",
    "title": "Request police report",
    "assigned_to": "Miguel Santos",
    "due_date": null,
    "reason": "Police report was requested but not yet received."
  },
  "source_refs": ["S1", "S2"]
}
```

**When** `POST /v1/actions/approve` is called with `Idempotency-Key`

**Then** the response is 200

**And** the task appears under `GET /v1/matters/MAT-1001/tasks`.

**And** a `task.created` event appears under `GET /v1/matters/MAT-1001/webhook-events`.

### Test 3.2: Idempotency replay does not duplicate writes

**When** the same approval request is sent again with the same `Idempotency-Key`

**Then** the response includes `"replayed": true`

**And** only one matching task exists.

### Test 3.3: Idempotency conflict

**When** the same `Idempotency-Key` is reused with a different request body

**Then** the response is 409

**And** the error code is `idempotency_conflict`.

### Test 3.4: Invalid approved action fails before database write

**When** `POST /v1/actions/approve` is called for `create_task` without `title`

**Then** the response is 400

**And** the error code is `action_validation_error`.

### Test 3.5: Invalid calendar date fails before database write

**When** `POST /v1/actions/approve` is called for `create_calendar_event` with `event_date: "tomorrow"`

**Then** the response is 400

**And** the error code is `action_validation_error`.

## Test group 4: Pagination, filtering, and DataBridge

### Test 4.1: Tasks support status filtering and pagination

**When** `GET /v1/matters/MAT-1001/tasks?status=Open&limit=10&offset=0` is called

**Then** the response is 200

**And** only matching task rows are returned.

### Test 4.2: Webhook events support matter-scoped filtering

**When** `GET /v1/matters/MAT-1001/webhook-events?event_type=task.created&delivery_status=queued` is called

**Then** the response is 200

**And** each event payload includes `matter_id`, `resource_type`, `resource_id`, and `source_refs`.

### Test 4.3: DataBridge import creates and updates one mapped matter

**When** `POST /v1/databridge/import` is called with `external_system` and `external_case_id`

**Then** the first response has `status: created`

**And** a second call with the same external identifiers has `status: updated`.

## Automated smoke check

Run:

```bash
python -m unittest tests.test_api_v08
```

## Known limitations

- Full RAG answer quality still depends on local Ollama and the selected model.
- Source refs are chunk-level, not paragraph-level.
- Confidence is rule-based, not calibrated from model evaluation.
- Write-back is local SQLite only.
