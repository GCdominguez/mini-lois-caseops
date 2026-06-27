# Beta Feedback Synthesis

This document models how beta feedback for an AI/API workflow feature could be synthesized into prioritized product work.

## Beta context

Feature under review: AI-assisted matter action workflow.

Beta users:

- Paralegal at a personal injury firm
- Managing attorney
- Legal operations admin
- Partner integrator
- Internal support representative

Prototype surfaces:

- Streamlit UI
- FastAPI endpoints
- Structured task candidates
- Approval-gated write-back
- Audit log

## Feedback themes

### Theme 1: Candidate quality matters more than candidate volume

**Feedback**

Paralegal: "The task suggestions are helpful when they point to missing records, but noisy if they convert every fact into a task. I do not want a task that says to review that the client has neck pain."

**Synthesis**

The first product requirement is not extraction volume. It is actionability quality. The assistant should separate facts from operational next steps.

**Product decision**

Require both an action or pending-work signal and a concrete object before producing a task candidate.

**Resulting backlog items**

- Prevent factual bullets from becoming task candidates.
- Add actionability evaluation cases.

**Priority**: P0

### Theme 2: Write-back needs an approval boundary

**Feedback**

Managing attorney: "I am comfortable with the system suggesting tasks, but I do not want it automatically changing the matter unless someone reviews it."

**Synthesis**

AI can propose, but mutation requires approval. This is especially important in legal workflows where records, deadlines, and assignments carry operational risk.

**Product decision**

Separate proposal generation from action approval. Keep `/actions/propose` read-only and route all mutation through `/actions/approve`.

**Resulting backlog items**

- Add approval-gated write-back endpoint.
- Store source references and original proposal in audit history.

**Priority**: P0

### Theme 3: API consumers need structured payloads

**Feedback**

Partner integrator: "I cannot reliably integrate against a paragraph. I need a stable schema with action type, title, reason, confidence, and source references."

**Synthesis**

The API should expose structured candidates, not just chat output. The API contract is the platform feature.

**Product decision**

Return structured `task_candidates` from `/ask`.

**Resulting backlog items**

- Return structured task candidates from Ask Matter API.
- Add API documentation and examples.

**Priority**: P0

### Theme 4: Source references are needed for trust

**Feedback**

Attorney: "Before approving a suggested task, I need to know why the system suggested it and where it found the information."

**Synthesis**

Source refs are not just citations. They support review, trust, and auditability.

**Product decision**

Include source_refs in candidates, approvals, and audit records.

**Resulting backlog items**

- Add matter-scoped source references to action candidates.
- Preserve source refs through approval.

**Priority**: P1

### Theme 5: Support needs predictable error behavior

**Feedback**

Support representative: "If customers call in with integration issues, we need predictable errors and clear examples."

**Synthesis**

API errors need to be stable and documented. This helps Support, implementation, and partners troubleshoot without engineering escalation.

**Product decision**

Return clear 404 for invalid matter IDs and 422 for malformed request bodies.

**Resulting backlog items**

- Add invalid matter handling across API endpoints.
- Add API documentation and Swagger examples.

**Priority**: P1

## Prioritized decisions

| Priority | Decision | Rationale |
|---|---|---|
| P0 | Add structured task candidate objects | Required for API consumers and downstream workflows |
| P0 | Require approval before mutation | Required for legal workflow safety |
| P0 | Filter factual bullets from tasks | Required for user trust and signal quality |
| P1 | Preserve source refs | Required for review and auditability |
| P1 | Document API examples | Required for partner and internal enablement |
| P2 | Add mock webhook/event payload | Useful for DataBridge-style integration story |

## What we will not do yet

- Build full role-based permissions.
- Implement production OAuth.
- Add real Filevine API integration.
- Automate legal deadlines.
- Create attorney-facing legal advice.

## PM notes

The most important beta insight is that users do not want AI automation everywhere. They want controlled acceleration. The product should help users move faster from matter context to operational work, while keeping review, approval, and auditability intact.
