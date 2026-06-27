# Mini LOIS CaseOps API

The API layer demonstrates how the AI assistant can be exposed as tool-style operations instead of only as a Streamlit UI.

## Why this matters

The API is the contract between the AI layer and the matter system. It separates reading, reasoning, proposing, approving, and writing.

The important product boundary is this:

- Read operations can happen directly.
- AI-generated write operations are proposals.
- Mutations require an explicit approval call.
- Approved actions write to the local matter record and audit log.

## Run the API

```bash
pip install -r requirements.txt
python ingest.py
uvicorn api_server:app --reload
```

Open the interactive docs at:

```text
http://127.0.0.1:8000/docs
```

## Endpoints

```text
GET  /health
GET  /matters
GET  /matters/{matter_id}
GET  /matters/{matter_id}/tasks
POST /matters/{matter_id}/ask
POST /matters/{matter_id}/actions/propose
POST /actions/approve
GET  /matters/{matter_id}/audit
```

## Example: ask a matter question

```bash
curl -X POST http://127.0.0.1:8000/matters/MAT-1001/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What are the missing next steps?"}'
```

The response includes the answer, retrieved sources, and task candidates extracted from the answer.

## Example: propose an action

```bash
curl -X POST http://127.0.0.1:8000/matters/MAT-1001/actions/propose \
  -H "Content-Type: application/json" \
  -d '{"request":"Create a task to request the missing police report."}'
```

The response returns a proposed action and source references. The proposal is not executed.

## Example: approve an action

```bash
curl -X POST http://127.0.0.1:8000/actions/approve \
  -H "Content-Type: application/json" \
  -d '{
    "approved_action": {
      "action_type": "create_task",
      "matter_id": "MAT-1001",
      "title": "Request police report",
      "assigned_to": "Miguel Santos",
      "due_date": null,
      "reason": "Police report was requested but not yet received."
    },
    "source_refs": ["S1", "S2"]
  }'
```

This writes to the SQLite matter record and audit log.

## PM/API Tools framing

This API shows the product design of an AI tool platform:

- retrieval endpoint for matter-aware answers
- proposal endpoint for structured action planning
- approval endpoint for safe write-back
- record endpoints for system-of-record state
- audit endpoint for traceability

That is the core API Tools story: define safe contracts between AI reasoning and business-system mutation.
