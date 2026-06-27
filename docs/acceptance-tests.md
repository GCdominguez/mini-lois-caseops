# Acceptance Tests

These tests define expected behavior for the AI-assisted matter action workflow and API layer.

## Test group 1: Matter API basics

### Test 1.1: Health check

**Given** the API server is running

**When** `GET /health` is called

**Then** the response is 200

**And** the body is:

```json
{"status": "ok"}
```

### Test 1.2: List matters

**Given** the local matter store contains demo matters

**When** `GET /matters` is called

**Then** the response is 200

**And** the response includes `MAT-1001`.

### Test 1.3: Invalid matter ID

**Given** `MAT-9999` does not exist

**When** `GET /matters/MAT-9999` is called

**Then** the response is 404

**And** the error says `Matter not found`.

## Test group 2: Ask Matter API

### Test 2.1: Ask valid matter question

**Given** Chroma has indexed the fake matter documents

**When** `POST /matters/MAT-1001/ask` is called with:

```json
{
  "question": "Give me some context on the case",
  "model": "llama3.2"
}
```

**Then** the response is 200

**And** the response includes `answer`, `sources`, and `task_candidates`.

### Test 2.2: Missing request field

**Given** the API expects `question`

**When** `/ask` is called with `request` instead of `question`

**Then** the response is 422

**And** the error points to the missing `question` field.

### Test 2.3: Invalid matter for ask

**Given** `MAT-9999` does not exist

**When** `POST /matters/MAT-9999/ask` is called

**Then** the response is 404

**And** no retrieval or model call should execute.

## Test group 3: Task candidate quality

### Test 3.1: Explicit missing record becomes task

**Given** the answer states `Police report requested but not yet received`

**When** task candidates are extracted

**Then** the candidate list includes:

```json
{
  "title": "Request police report",
  "action_type": "create_task"
}
```

### Test 3.2: Factual medical symptom does not become task

**Given** the answer states `She reports neck pain, lower back pain, and headaches`

**When** task candidates are extracted

**Then** no task candidate is created from that fact.

### Test 3.3: Uploaded evidence does not become task

**Given** the answer states `Rideshare trip receipt uploaded by client`

**When** task candidates are extracted

**Then** no task candidate is created because the item is already complete.

### Test 3.4: Available witness becomes task only when contact is implied

**Given** the answer states `contacting the available witness`

**When** task candidates are extracted

**Then** the candidate list includes `Contact available witness`.

### Test 3.5: Candidate objects include required fields

**Given** `/ask` returns task candidates

**Then** each task candidate includes:

- title
- action_type
- reason
- confidence
- source_refs
- original_text

## Test group 4: Action proposal

### Test 4.1: Propose action does not mutate record

**Given** an action proposal request

**When** `POST /matters/MAT-1001/actions/propose` is called

**Then** a proposed action is returned

**And** no new task is written to the matter record.

### Test 4.2: Proposed action includes approval flag

**Given** an action proposal request

**When** a proposal is returned

**Then** `requires_approval` is true.

## Test group 5: Approval and write-back

### Test 5.1: Approve create_task action

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

**When** `POST /actions/approve` is called

**Then** the response is 200

**And** the task appears under `GET /matters/MAT-1001/tasks`.

### Test 5.2: Audit log records approved action

**Given** an approved task has been created

**When** `GET /matters/MAT-1001/audit` is called

**Then** the audit log includes the approved action payload and source_refs.

### Test 5.3: Invalid matter approval fails

**Given** an approved action payload references `MAT-9999`

**When** `POST /actions/approve` is called

**Then** the response is 404

**And** no task is written.

## Test group 6: Launch readiness checks

### Test 6.1: Swagger UI loads

**Given** the API server is running

**When** `http://127.0.0.1:8000/docs` is opened

**Then** Swagger UI displays all endpoints.

### Test 6.2: README and API docs are current

**Given** the repo has shipped a new API behavior

**When** docs are reviewed

**Then** `docs/api.md` describes structured task candidate objects.

## Known limitations

- Tests are documented as acceptance cases, not yet automated.
- API auth is not implemented.
- Source refs are chunk-level, not paragraph-level.
- Confidence is rule-based, not calibrated from model evaluation.
- Write-back is local SQLite only.
