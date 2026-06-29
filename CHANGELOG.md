# Changelog

## v0.8

- Fixed the API import/startup path in the local demo environment.
- Added stricter approved-action validation so missing task titles, missing note text, invalid dates, and unsupported actions return structured API errors before write-back.
- Moved idempotent approval execution into a single SQLite transaction so duplicate approval requests with the same `Idempotency-Key` replay the stored response without creating duplicate tasks.
- Added a local demo reset helper at `scripts/demo_reset.py`.
- Added `unittest` smoke tests for health, auth, approval validation, idempotent task write-back, webhook events, and DataBridge import.
- Updated setup and API docs to match the `/v1` authenticated API surface.

## v0.7

- Added versioned `/v1` API routes while keeping unversioned local prototype routes available.
- Added idempotency support for `/v1/actions/approve` using the `Idempotency-Key` header.
- Added `409 idempotency_conflict` structured errors when an idempotency key is reused with a different request body.
- Added pagination and filtering for task, audit, and webhook event list endpoints.
- Added fake DataBridge-style matter import at `/v1/databridge/import` with external ID mapping.
- Added `docs/API_CONTRACT.md` to document stable API shapes and product rules.
- Updated `docs/API_EXAMPLES.md` with v0.7 curl examples.

## v0.6

- Added local API-key authentication for protected API endpoints.
- Added structured API error responses for auth failures, validation errors, missing matters, and unsupported actions.
- Added webhook-style event logging for approved write-backs, including `task.created`, `note.added`, and `calendar_event.created` events.
- Added webhook event read endpoints for all events and matter-scoped events.
- Added `docs/API_EXAMPLES.md` with curl examples for the full API workflow.

## v0.5

- Added a FastAPI layer with Swagger/OpenAPI documentation.
- Added structured task candidate objects returned from `/ask`.
- Added shared quick-task extraction between the UI and API.
- Added question-intent gating so unrelated prompts do not create task candidates.
- Added PM artifacts for backlog management, beta feedback synthesis, acceptance testing, launch readiness, and tool-contract design.

## v0.2

- Added editable approval form for model-generated actions.
- Added validation warnings for due dates, assignees, missing titles, and brief reasons.
- Updated audit payloads to store the original model proposal plus the approved action when edited.
- Improved matter metadata display.
- Improved task table readability.

## v0.1

- Added matter-scoped RAG over fake matter documents.
- Added source-cited answers.
- Added structured action proposals.
- Added approval-gated write-back to SQLite.
- Added audit logging.
