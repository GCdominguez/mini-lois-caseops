# Changelog

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
