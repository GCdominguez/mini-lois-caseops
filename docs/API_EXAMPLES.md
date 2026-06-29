# API Examples

These examples show the Mini LOIS API as a small API-platform surface: versioned endpoints, authenticated requests, structured errors, AI-generated task candidates, approval-gated write-back, idempotency, audit logs, webhook-style event records, pagination/filtering, and a fake DataBridge import.

v0.8 adds safer approved-action validation, a transactional idempotency path for approvals, smoke tests, and a demo reset helper.

The local demo API key is `demo-key` unless you override it with `MINI_LOIS_API_KEY`.

## Run the API server

```bash
source .venv/bin/activate
python -c "import api_server; print(api_server.health())"
uvicorn api_server:app --reload
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Pretty-print JSON responses

Most examples pipe through `python3 -m json.tool` so the response is readable in Terminal.

```bash
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool
```

Expected response:

```json
{
  "status": "ok",
  "version": "0.8.0"
}
```

## Authenticated matter list

```bash
curl -s http://127.0.0.1:8000/v1/matters \
  -H "X-API-Key: demo-key" \
  | python3 -m json.tool
```

Without `X-API-Key`, protected endpoints return a structured `401` error.

```bash
curl -s http://127.0.0.1:8000/v1/matters \
  | python3 -m json.tool
```

Expected shape:

```json
{
  "error": "unauthorized",
  "message": "Missing or invalid API key. Send X-API-Key: demo-key for the local prototype.",
  "request_id": "..."
}
```

## Ask a matter question and receive task candidates

```bash
curl -s -X POST http://127.0.0.1:8000/v1/matters/MAT-1001/ask \
  -H "X-API-Key: demo-key" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the next steps for this matter?",
    "model": "llama3.2"
  }' \
  | python3 -m json.tool
```

The response contains:

```json
{
  "matter_id": "MAT-1001",
  "question": "What are the next steps for this matter?",
  "answer": "...",
  "sources": [
    {
      "source_id": "S1",
      "source_file": "MAT-1001_intake_notes.txt",
      "chunk_index": 1
    }
  ],
  "task_candidates": [
    {
      "title": "Request PT records",
      "action_type": "create_task",
      "reason": "Candidate extracted from matter answer: Request physical therapy records.",
      "confidence": "high",
      "source_refs": ["S1", "S2", "S3"],
      "original_text": "Request physical therapy records"
    }
  ]
}
```

## Structured `404` error

```bash
curl -s -X POST http://127.0.0.1:8000/v1/matters/MAT-9999/ask \
  -H "X-API-Key: demo-key" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the next steps?",
    "model": "llama3.2"
  }' \
  | python3 -m json.tool
```

Expected shape:

```json
{
  "error": "matter_not_found",
  "message": "No matter exists for matter_id 'MAT-9999'.",
  "request_id": "...",
  "details": {
    "matter_id": "MAT-9999"
  }
}
```

## Approve a task write-back with idempotency

This simulates another system approving a task candidate that Mini LOIS produced.

```bash
curl -s -X POST http://127.0.0.1:8000/v1/actions/approve \
  -H "X-API-Key: demo-key" \
  -H "Idempotency-Key: approve-MAT-1001-pt-records-001" \
  -H "Content-Type: application/json" \
  -d '{
    "approved_action": {
      "action_type": "create_task",
      "matter_id": "MAT-1001",
      "title": "Request PT records",
      "assigned_to": "Miguel Santos",
      "due_date": null,
      "reason": "Mini LOIS identified missing PT records after April 19."
    },
    "source_refs": ["S1", "S2", "S3"],
    "original_model_proposal": {
      "action_type": "create_task",
      "matter_id": "MAT-1001",
      "title": "Request PT records",
      "assigned_to": "Miguel Santos",
      "due_date": null,
      "reason": "Mini LOIS identified missing PT records after April 19."
    }
  }' \
  | python3 -m json.tool
```

Expected shape:

```json
{
  "status": "executed",
  "result": {
    "message": "Task created.",
    "matter_id": "MAT-1001",
    "resource_type": "task",
    "resource_id": "1",
    "webhook_event_id": 1
  },
  "approved_action": {
    "action_type": "create_task",
    "matter_id": "MAT-1001",
    "title": "Request PT records"
  },
  "idempotency": {
    "key": "approve-MAT-1001-pt-records-001",
    "replayed": false
  }
}
```

Run the same request again with the same `Idempotency-Key`. The API should return the original response with:

```json
{
  "idempotency": {
    "key": "approve-MAT-1001-pt-records-001",
    "replayed": true
  }
}
```

That means the second request did not create a duplicate task.

## Validation error for an unsafe write-back

This shows that the API rejects malformed approved actions before they reach SQLite.

```bash
curl -s -X POST http://127.0.0.1:8000/v1/actions/approve \
  -H "X-API-Key: demo-key" \
  -H "Content-Type: application/json" \
  -d '{
    "approved_action": {
      "action_type": "create_task",
      "matter_id": "MAT-1001"
    }
  }' \
  | python3 -m json.tool
```

Expected shape:

```json
{
  "error": "action_validation_error",
  "message": "approved_action.title is required for create_task.",
  "request_id": "...",
  "details": {
    "field": "title",
    "action_type": "create_task"
  }
}
```

## Confirm the task was written back with filtering and pagination

```bash
curl -s "http://127.0.0.1:8000/v1/matters/MAT-1001/tasks?status=Open&limit=10&offset=0" \
  -H "X-API-Key: demo-key" \
  | python3 -m json.tool
```

## Confirm the audit log with pagination

```bash
curl -s "http://127.0.0.1:8000/v1/matters/MAT-1001/audit?limit=10&offset=0" \
  -H "X-API-Key: demo-key" \
  | python3 -m json.tool
```

## Confirm webhook-style event output with filtering

```bash
curl -s "http://127.0.0.1:8000/v1/matters/MAT-1001/webhook-events?event_type=task.created&delivery_status=queued&limit=10&offset=0" \
  -H "X-API-Key: demo-key" \
  | python3 -m json.tool
```

Expected shape:

```json
[
  {
    "id": 1,
    "event_type": "task.created",
    "matter_id": "MAT-1001",
    "resource_type": "task",
    "resource_id": "1",
    "delivery_status": "queued",
    "attempt_count": 0,
    "next_retry_at": null,
    "created_at": "...",
    "payload": {
      "event_type": "task.created",
      "matter_id": "MAT-1001",
      "resource_type": "task",
      "resource_id": "1",
      "action": {
        "action_type": "create_task",
        "matter_id": "MAT-1001",
        "title": "Request PT records"
      },
      "source_refs": ["S1", "S2", "S3"],
      "created_at": "..."
    }
  }
]
```

## Fake DataBridge import

This simulates a partner or external system sending matter data into the platform.

```bash
curl -s -X POST http://127.0.0.1:8000/v1/databridge/import \
  -H "X-API-Key: demo-key" \
  -H "Content-Type: application/json" \
  -d '{
    "external_system": "demo_crm",
    "external_case_id": "ABC-123",
    "client_full_name": "Alicia Johnson",
    "case_type": "Personal Injury",
    "matter_name": "Johnson v. RideshareCo Imported",
    "phase": "Imported intake",
    "lead_attorney": "Dana Cruz",
    "paralegal": "Miguel Santos",
    "status": "Imported"
  }' \
  | python3 -m json.tool
```

Expected shape:

```json
{
  "status": "created",
  "external_system": "demo_crm",
  "external_matter_id": "ABC-123",
  "matter": {
    "matter_id": "MAT-EXT-ABC-123",
    "matter_name": "Johnson v. RideshareCo Imported",
    "matter_type": "Personal Injury",
    "client": "Alicia Johnson",
    "phase": "Imported intake"
  }
}
```

Run it again with the same `external_system` and `external_case_id`, and it updates the same mapped matter instead of creating a new one.

## v0.8 smoke tests and demo reset

```bash
python -m unittest tests.test_api_v08
python scripts/demo_reset.py
python ingest.py
```

Use `python scripts/demo_reset.py --include-chroma` only when you want to rebuild the retrieval index too.

## Why this matters for API Platform PM work

This turns the prototype from a UI-only demo into a small platform contract. A partner system can ask a matter question, receive structured task candidates, approve a write-back safely, avoid duplicate writes with idempotency, verify the matter record, inspect the audit trail, observe webhook-style events, and import external matter data through a DataBridge-style endpoint.
