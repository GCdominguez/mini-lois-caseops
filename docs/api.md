# Mini LOIS CaseOps API

The API layer demonstrates how the assistant can be exposed as tool-style operations instead of only as a Streamlit UI. v0.8 focuses on live-demo reliability: authenticated `/v1` routes, structured errors, approval-gated writes, safer idempotency, and smoke tests.

## Run the API

```bash
source .venv/bin/activate
python -c "import api_server; print(api_server.health())"
python ingest.py
uvicorn api_server:app --reload
```

Open the interactive docs at:

```text
http://127.0.0.1:8000/docs
```

Protected endpoints require:

```text
X-API-Key: demo-key
```

## Preferred v1 endpoints

```text
GET  /v1/health
GET  /v1/matters
GET  /v1/matters/{matter_id}
GET  /v1/matters/{matter_id}/tasks?status=Open&limit=50&offset=0
POST /v1/matters/{matter_id}/ask
POST /v1/matters/{matter_id}/actions/propose
POST /v1/actions/approve
GET  /v1/matters/{matter_id}/audit?limit=50&offset=0
GET  /v1/webhook-events?event_type=task.created&delivery_status=queued
GET  /v1/matters/{matter_id}/webhook-events?event_type=task.created
POST /v1/databridge/import
```

Unversioned routes still exist for the local prototype, but `/v1` is the contract to demo.

## Example: ask a matter question

```bash
curl -s -X POST http://127.0.0.1:8000/v1/matters/MAT-1001/ask \
  -H "X-API-Key: demo-key" \
  -H "Content-Type: application/json" \
  -d '{"question":"What are the missing next steps?","model":"llama3.2"}' \
  | python3 -m json.tool
```

The response includes `answer`, `sources`, and `task_candidates`. Task candidates are suggestions only; they do not write to the matter record.

## Example: approve a write-back safely

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
    "source_refs": ["S1", "S2"]
  }' \
  | python3 -m json.tool
```

Run the same request again with the same `Idempotency-Key`; the second response should show `"replayed": true` and should not create a duplicate task.

## v0.8 validation behavior

Approved actions are checked before write-back:

- `create_task` requires `title`.
- `add_note` requires `note_text`.
- `create_calendar_event` requires `title` and `event_date`.
- Date fields must use `YYYY-MM-DD`.
- Unsupported action types return `unsupported_action`.

This keeps malformed partner/tool calls from turning into database errors during a live demo.

## Smoke tests

```bash
python -m unittest tests.test_api_v08
```

The tests cover health, auth, approved-action validation, idempotent task write-back, task reads, matter-scoped webhook events, and DataBridge import.
