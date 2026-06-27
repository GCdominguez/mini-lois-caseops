# Backlog: LOIS Workflow / API Platform Prototype

This backlog translates the prototype into well-scoped product issues with acceptance criteria. It is written to model day-to-day PM execution: clear scope, customer value, engineering-ready requirements, and testable outcomes.

## Issue 1: Return structured task candidates from Ask Matter API

**Problem**

The `/ask` endpoint originally returned raw task candidate strings. Partner systems and UI surfaces need structured objects to render, review, and convert candidates into tasks.

**User story**

As an integrator, I want task candidates returned as structured objects so that my workflow can display them, route them for approval, or pass them into an action endpoint.

**Requirements**

- Return `task_candidates` as an array of objects.
- Each object includes `title`, `action_type`, `reason`, `confidence`, `source_refs`, and `original_text`.
- De-duplicate candidates by title.
- Preserve source references from the answer response.

**Acceptance criteria**

- `/matters/MAT-1001/ask` returns task_candidates as objects, not strings.
- Each candidate has all required fields.
- Duplicate candidates are collapsed.
- Existing answer and sources fields remain unchanged.

**Priority**: P0

## Issue 2: Add approval-gated write-back endpoint

**Problem**

AI-generated actions should not mutate the matter record automatically.

**User story**

As a legal operations admin, I want AI-generated actions to require approval before write-back so that workflow automation remains controlled and auditable.

**Requirements**

- Add `POST /actions/approve`.
- Accept an approved action payload.
- Write supported actions to the local matter record.
- Store original proposal when available.
- Store source refs in audit log.

**Acceptance criteria**

- Approved `create_task` action creates a task.
- Unapproved proposals do not create tasks.
- Audit log records the action payload and source refs.
- Invalid matter_id returns 404.

**Priority**: P0

## Issue 3: Prevent factual bullets from becoming task candidates

**Problem**

Early extraction logic over-generated tasks from factual summaries, such as symptoms, uploaded evidence, and background facts.

**User story**

As a paralegal, I only want task candidates when there is actual pending work so that the assistant does not create noise.

**Requirements**

- Require an action or pending-work signal.
- Require a concrete task object.
- Exclude facts, symptoms, uploaded evidence, and confirmed details.
- Keep explicit next steps, missing records, not-yet-received documents, and witness follow-up.

**Acceptance criteria**

- A summary bullet like `She reports neck pain` does not become a task.
- `Police report requested but not yet received` becomes `Request police report`.
- `Contacting the available witness` becomes `Contact available witness`.
- Candidate count drops when the answer is informational only.

**Priority**: P0

## Issue 4: Add API documentation and Swagger examples

**Problem**

Developer and partner users need clear API usage examples.

**User story**

As a partner developer, I want request and response examples so I can understand how to integrate with the workflow API.

**Requirements**

- Document all endpoints in `docs/api.md`.
- Include curl examples for ask, propose, approve, and audit.
- Include example structured task candidate payload.
- Explain read versus write boundaries.

**Acceptance criteria**

- API docs include endpoint list.
- API docs include copyable curl examples.
- API docs explain approval-gated mutation.
- Swagger UI runs locally.

**Priority**: P1

## Issue 5: Add matter-scoped source references to action candidates

**Problem**

Users need to verify why an action was suggested before approving it.

**User story**

As an attorney, I want task candidates linked to source references so I can validate the basis for the suggested action.

**Requirements**

- Include `source_refs` in task candidate objects.
- Preserve source refs through approval.
- Display source refs in the audit log.

**Acceptance criteria**

- `/ask` candidate objects include source_refs.
- `/actions/approve` accepts source_refs.
- Audit log stores source_refs.

**Priority**: P1

## Issue 6: Add invalid matter handling across API endpoints

**Problem**

API consumers need predictable errors when the supplied matter ID does not exist.

**User story**

As an API consumer, I want invalid matter IDs to return a clear 404 so I can handle the error predictably.

**Requirements**

- Validate matter_id in read, ask, propose, task, and audit endpoints.
- Return 404 with `Matter not found`.

**Acceptance criteria**

- `/matters/MAT-9999` returns 404.
- `/matters/MAT-9999/ask` returns 404.
- `/matters/MAT-9999/actions/propose` returns 404.
- `/matters/MAT-9999/audit` returns 404.

**Priority**: P1

## Issue 7: Add mock DataBridge webhook payload for approved task creation

**Problem**

Approved workflow actions may need to trigger external systems or partner integrations.

**User story**

As a partner integrator, I want a stable task-created event payload so I can sync approved actions to another system.

**Requirements**

- Define `task.created` event payload.
- Include matter_id, task title, assignee, due_date, source_refs, created_at, and audit_id when available.
- Document retry and idempotency considerations as future work.

**Acceptance criteria**

- `docs/examples/task-created-webhook.json` exists.
- Payload includes an event type and version.
- Payload does not include unsupported fields.

**Priority**: P2

## Issue 8: Add release-readiness checklist

**Problem**

Support, Sales, and implementation teams need predictable context before a launch.

**User story**

As a GTM stakeholder, I want launch readiness materials so I know what changed, who it affects, and how to explain it to customers.

**Requirements**

- Add release notes.
- Add support enablement notes.
- Add known limitations.
- Add customer-facing value statement.

**Acceptance criteria**

- Launch checklist exists.
- Release notes include impact, limitations, and validation steps.
- Support has at least three expected questions and answers.

**Priority**: P2
