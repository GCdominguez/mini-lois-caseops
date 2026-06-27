# Tool Contract and MCP Framing

This document describes how the prototype can be understood as a tool/API contract for AI-assisted legal workflows.

## Purpose

A legal AI assistant is more useful when it can safely operate through explicit tools instead of only producing prose. The tool contract defines what the assistant can read, what it can propose, what requires approval, and what gets audited.

This maps to API Platform work because AI capabilities need stable contracts before they can be used by product surfaces, partners, workflow engines, or MCP-style clients.

## Tool principles

1. Tools should be scoped to a matter.
2. Read tools should not mutate records.
3. Write tools should require explicit approval.
4. Tool outputs should be structured, not just prose.
5. Mutations should preserve source references.
6. Audit logs should store the approved payload.
7. Tool errors should be predictable for integrators.

## Tool catalog

### ask_matter

**Purpose**

Answer a matter-scoped question and return sources and structured task candidates.

**API mapping**

`POST /matters/{matter_id}/ask`

**Input**

```json
{
  "question": "What are the missing next steps?",
  "model": "llama3.2"
}
```

**Output**

```json
{
  "matter_id": "MAT-1001",
  "answer": "...",
  "sources": [],
  "task_candidates": []
}
```

**Mutation risk**: none

**Approval required**: no

### propose_action

**Purpose**

Convert a user request into a structured action proposal.

**API mapping**

`POST /matters/{matter_id}/actions/propose`

**Input**

```json
{
  "request": "Create a task to request the missing police report.",
  "model": "llama3.2"
}
```

**Output**

```json
{
  "proposed_action": {
    "action_type": "create_task",
    "matter_id": "MAT-1001",
    "title": "Request police report"
  },
  "source_refs": ["S1"],
  "requires_approval": true
}
```

**Mutation risk**: none until approved

**Approval required**: yes, before write-back

### approve_action

**Purpose**

Write an approved action to the matter record.

**API mapping**

`POST /actions/approve`

**Input**

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

**Output**

```json
{
  "status": "executed",
  "result": "Task created.",
  "approved_action": {}
}
```

**Mutation risk**: high

**Approval required**: yes

### get_audit_log

**Purpose**

Return approved actions and source references for a matter.

**API mapping**

`GET /matters/{matter_id}/audit`

**Mutation risk**: none

**Approval required**: no

## Product notes

### Why approval is a separate tool

Separating proposal from approval prevents the AI from silently changing a system of record. This is a safer pattern for legal workflows, partner integrations, and internal workflow automation.

### Why task candidates are structured

Structured candidates allow another surface to consume the output. A UI can render action cards. A workflow engine can route approvals. A partner integration can map the candidate to its own task system.

### Why source_refs are part of the contract

Source refs support review and auditability. They also help downstream users understand whether a proposed action was grounded in matter context or generated from weak inference.

## MCP-style interpretation

This prototype can be framed as a simplified MCP-like tool server:

- `ask_matter` is a read tool.
- `propose_action` is a planning tool.
- `approve_action` is a controlled mutation tool.
- `get_audit_log` is a traceability tool.

A production version would add:

- OAuth and user identity
- role-based access checks
- tenant and matter permission boundaries
- idempotency keys
- schema versioning
- webhook/event delivery
- rate limits
- partner sandboxing

## Open API design questions

- Should action candidates be generated inside `/ask` or through a separate `/actions/candidates` endpoint?
- Should approval be synchronous or event-driven?
- Should integrations receive webhook events after approval?
- Should confidence be visible to end users or only used internally for ranking?
- Should source refs be required for all write-back actions?
