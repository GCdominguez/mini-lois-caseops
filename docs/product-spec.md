# Product Spec: AI-Assisted Matter Action Workflow

## Summary

Mini LOIS: CaseOps AI explores a narrow workflow from matter-aware AI reasoning to structured, approval-gated system actions. The prototype demonstrates how an assistant can read matter context, answer questions with sources, generate structured task candidates, propose actions, and write approved actions to a mock matter record with an audit trail.

This is not intended to recreate Filevine LOIS. It is a focused product slice for exploring API Platform concepts around LOIS Workflows, DataBridge-style integrations, and MCP/tool contracts.

## Problem

Legal teams often need to convert unstructured matter context into operational next steps. Matter files contain facts, documents, notes, risks, deadlines, and incomplete records. A chat answer alone may summarize the situation, but it does not automatically translate into safe workflow execution.

The product problem is to determine when AI output should remain informational and when it should become a structured, reviewable action.

## Users

- Paralegal: needs clear next steps and task creation without manual retyping.
- Attorney: needs source-grounded context and confidence before operational changes are made.
- Legal operations admin: needs auditable workflow automation and low-risk adoption.
- Partner or integrator: needs stable API contracts rather than UI-only automation.
- Support or implementation team: needs predictable behavior, release notes, and clear troubleshooting paths.

## Goals

- Answer matter questions from scoped matter context.
- Return cited source chunks with each answer.
- Extract structured task candidates only when the answer contains actionable next steps.
- Prevent factual summaries from becoming tasks.
- Require explicit approval before write-back.
- Store approved actions in a local matter record.
- Preserve an audit log with source references and approved payloads.
- Expose the core workflow through an API contract.

## Non-goals

- Recreate Filevine LOIS.
- Provide legal advice.
- Build production-grade authentication or authorization.
- Replace attorney or paralegal judgment.
- Connect to a real legal case management system.
- Implement a full workflow engine.

## User flow

1. User selects a scoped matter.
2. User asks a matter question.
3. System retrieves relevant matter context.
4. AI generates a source-grounded answer.
5. System extracts structured task candidates when there are explicit action signals.
6. User drafts one or more candidate tasks.
7. User reviews and edits task fields.
8. User approves the action.
9. System writes the task to the matter record.
10. System records the approved action and source references in the audit log.

## Business rules

- The assistant may read matter context without approval.
- The assistant may propose actions without approval.
- The assistant may not mutate the matter record without explicit approval.
- Task candidates require both an actionable signal and a concrete object.
- Matter facts, symptoms, uploaded evidence, and background context are not tasks.
- Missing records, requested-but-not-received documents, explicit next steps, deadlines, and witness follow-up may become task candidates.
- Every write-back must include matter_id, action_type, reason, and source_refs where available.
- Due dates should not be invented. They should be blank unless directly supported by matter context or user instruction.

## API surfaces

### Ask matter

`POST /matters/{matter_id}/ask`

Returns:

- matter_id
- question
- answer
- sources
- task_candidates

Task candidate object:

```json
{
  "title": "Request police report",
  "action_type": "create_task",
  "reason": "The matter context indicates this item has not been received.",
  "confidence": "high",
  "source_refs": ["S1", "S2"],
  "original_text": "police report has not been received"
}
```

### Propose action

`POST /matters/{matter_id}/actions/propose`

Returns an AI-generated structured action proposal and source references. The proposal is not executed.

### Approve action

`POST /actions/approve`

Executes an approved action and writes to the matter record and audit log.

## Error states

- Invalid matter ID returns 404.
- Missing required request body fields return 422.
- Unsupported action type should be rejected or flagged before approval.
- Missing task title should block write-back.
- Invalid date format should block write-back.
- Source refs may be empty, but the audit log should still store the action payload.

## Acceptance criteria

- Given a valid matter ID and question, `/ask` returns an answer and sources.
- Given an invalid matter ID, `/ask` returns 404.
- Given an answer with explicit next steps, task_candidates returns structured objects.
- Given an answer containing only factual bullets, task_candidates returns no tasks.
- Given an approved create_task action, `/actions/approve` writes the task to the matter record.
- Given an approved action, the audit log stores the payload and source refs.
- Given a proposed action, no write occurs until approval.

## Open questions

- Should task candidate confidence be rule-based, model-generated, or both?
- Should task extraction happen inside the model prompt, deterministic post-processing, or a hybrid classifier?
- How should source refs map to long documents, pages, or paragraph-level evidence in a production system?
- Which actions require attorney approval versus paralegal approval?
- How should partner integrations consume proposed actions: polling, webhook, event stream, or MCP tool calls?
