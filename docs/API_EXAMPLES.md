# API Examples

These examples show the Mini LOIS API as a small API-platform surface: authenticated requests, structured errors, AI-generated task candidates, approval-gated write-back, audit logs, and webhook-style event records.

The local demo API key is `demo-key` unless you override it with `MINI_LOIS_API_KEY`.

## Run the API server

```bash
uvicorn api_server:app --reload
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Pretty-print JSON responses

Most examples pipe through `python3 -m json.tool` so the response is readable in Terminal.

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

Expected response:

```json
{
  "status": "ok",
  "version": "0.6.0"
}
```

## Authenticated matter list

```bash
curl -s http://127.0.0.1:8000/matters \
  -H "X-API-Key: demo-key" \
  | python3 -m json.tool
```

Without `X-API-Key`, protected endpoints return a structured `401` error.

```bash
curl -s http://127.0.0.1:8000/matters \
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
curl -s -X POST http://127.0.0.1:8000/matters/MAT-1001/ask \
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
curl -s -X POST http://127.0.0.1:8000/matters/MAT-9999/ask \
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

## Approve a task write-back

This simulates another system approving a task candidate that Mini LOIS produced.

```bash
curl -s -X POST http://127.0.0.1:8000/actions/approve \
  -H "X-API-Key: demo-key" \
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
  }
}
```

## Confirm the task was written back

```bash
curl -s http://127.0.0.1:8000/matters/MAT-1001/tasks \
  -H "X-API-Key: demo-key" \
  | python3 -m json.tool
```

## Confirm the audit log

```bash
curl -s http://127.0.0.1:8000/matters/MAT-1001/audit \
  -H "X-API-Key: demo-key" \
  | python3 -m json.tool
```

## Confirm webhook-style event output

```bash
curl -s http://127.0.0.1:8000/matters/MAT-1001/webhook-events \
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

## Why this matters for API Platform PM work

This turns the prototype from a UI-only demo into a small platform contract. A partner system can ask a matter question, receive structured task candidates, approve a write-back, verify the matter record, inspect the audit trail, and observe a webhook-style event that another integration could consume.
