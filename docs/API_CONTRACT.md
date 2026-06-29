# API Contract

This document describes the stable API shapes used by Mini LOIS v0.8. It is intentionally small, but it treats the API as a product surface for another developer or partner integration.

## Versioning

Preferred routes use `/v1`.

```text
/v1/matters
/v1/matters/{matter_id}/ask
/v1/actions/approve
/v1/matters/{matter_id}/webhook-events
/v1/databridge/import
```

Unversioned routes remain available for the local prototype, but `/v1` is the documented contract.

## Authentication

Protected endpoints require a local demo API key.

```text
X-API-Key: demo-key
```

Production equivalent: OAuth client credentials, user tokens, or scoped API credentials.

## Request tracing

Clients may send:

```text
X-Request-ID: any-client-generated-id
```

If omitted, the API generates a `request_id` in structured error responses.

## StructuredError

All API errors should use this shape.

```json
{
  "error": "matter_not_found",
  "message": "No matter exists for matter_id 'MAT-9999'.",
  "request_id": "9fa7...",
  "details": {
    "matter_id": "MAT-9999"
  }
}
```

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `error` | string | yes | Stable machine-readable code. |
| `message` | string | yes | Human-readable explanation. |
| `request_id` | string | yes | Used to trace/debug a request. |
| `details` | object/array | no | Additional validation or resource context. |

Known error codes:

```text
unauthorized
validation_error
matter_not_found
missing_matter_id
unsupported_action
action_validation_error
idempotency_conflict
import_validation_error
```

## Matter

```json
{
  "matter_id": "MAT-1001",
  "matter_name": "Johnson v. RideshareCo",
  "matter_type": "Personal Injury",
  "client": "Alicia Johnson",
  "phase": "Pre-mediation discovery",
  "lead_attorney": "Dana Cruz",
  "paralegal": "Miguel Santos",
  "status": "Active",
  "open_date": "2026-04-12"
}
```

## AskMatter request

```json
{
  "question": "What are the next steps for this matter?",
  "model": "llama3.2"
}
```

## AskMatter response

```json
{
  "matter_id": "MAT-1001",
  "question": "What are the next steps for this matter?",
  "answer": "...",
  "sources": [
    {
      "source_id": "S1",
      "text": "...",
      "matter_id": "MAT-1001",
      "source_file": "MAT-1001_intake_notes.txt",
      "chunk_index": 1,
      "distance": 0.93
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

## TaskCandidate

A `TaskCandidate` is not a write. It is a structured suggestion that still requires approval.

```json
{
  "title": "Request police report",
  "action_type": "create_task",
  "reason": "The matter answer identifies this as missing or incomplete information.",
  "confidence": "high",
  "source_refs": ["S1", "S2"],
  "original_text": "obtain the police report"
}
```

Rules:

- Must be grounded in the answer and source refs.
- Must not write to the matter record by itself.
- Should be ignored by clients unless a human or trusted workflow approves it.

## ApprovedAction

```json
{
  "action_type": "create_task",
  "matter_id": "MAT-1001",
  "title": "Request PT records",
  "assigned_to": "Miguel Santos",
  "due_date": null,
  "reason": "Mini LOIS identified missing PT records after April 19."
}
```

Supported action types:

```text
create_task
add_note
create_calendar_event
```

Validation rules:

- `create_task` requires `title`.
- `add_note` requires `note_text`.
- `create_calendar_event` requires `title` and `event_date`.
- Date fields must use `YYYY-MM-DD`.
- Invalid action fields return `400 action_validation_error`.
- Unknown action types return `400 unsupported_action`.

## ApproveAction request

```json
{
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
    "title": "Request PT records"
  }
}
```

## Idempotency

Mutation endpoints should support idempotency. v0.8 supports it for `/v1/actions/approve`.

```text
Idempotency-Key: approve-MAT-1001-pt-records-001
```

If the same request is sent twice with the same key, the API returns the first result instead of creating a duplicate task. v0.8 stores the idempotency record in the same SQLite transaction as the approved write-back.

If the same key is reused with a different request body, the API returns `409 idempotency_conflict`.

## ApproveAction response

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

## WebhookEvent

Webhook events are written when approved actions mutate the mock matter record.

```json
{
  "id": 1,
  "event_type": "task.created",
  "matter_id": "MAT-1001",
  "resource_type": "task",
  "resource_id": "1",
  "delivery_status": "queued",
  "attempt_count": 0,
  "next_retry_at": null,
  "created_at": "2026-06-27T17:15:00+00:00",
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
    "created_at": "2026-06-27T17:15:00+00:00"
  }
}
```

## Pagination and filtering

List endpoints support `limit` and `offset`.

```text
GET /v1/matters/MAT-1001/tasks?status=Open&limit=25&offset=0
GET /v1/matters/MAT-1001/audit?limit=25&offset=0
GET /v1/webhook-events?event_type=task.created&delivery_status=queued&limit=25&offset=0
GET /v1/matters/MAT-1001/webhook-events?event_type=task.created&delivery_status=queued&limit=25&offset=0
```

Rules:

- `limit` must be between 1 and 100.
- `offset` must be 0 or greater.
- `status`, `event_type`, and `delivery_status` are optional filters.

## DataBridge import

`POST /v1/databridge/import` accepts a fake external-system matter payload and maps it to the Mini LOIS matter schema.

Request:

```json
{
  "external_system": "demo_crm",
  "external_case_id": "ABC-123",
  "client_full_name": "Alicia Johnson",
  "case_type": "Personal Injury",
  "matter_name": "Johnson v. RideshareCo",
  "phase": "Imported intake",
  "lead_attorney": "Dana Cruz",
  "paralegal": "Miguel Santos"
}
```

Response:

```json
{
  "status": "created",
  "external_system": "demo_crm",
  "external_matter_id": "ABC-123",
  "matter": {
    "matter_id": "MAT-EXT-ABC-123",
    "matter_name": "Johnson v. RideshareCo",
    "matter_type": "Personal Injury",
    "client": "Alicia Johnson"
  }
}
```

Product rule: imports should be predictable, validated, and mapped into the platform schema instead of dumping arbitrary partner data into the matter record.
