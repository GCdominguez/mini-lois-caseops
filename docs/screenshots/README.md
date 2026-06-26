# Screenshots

These screenshots document the Mini LOIS demo flow.

## Matter summary with no actionable recommendations

This cropped screenshot shows Mini LOIS summarizing a matter in plain language while the action panel correctly detects that the answer does not contain discrete task recommendations.

![Matter summary with no actionable recommendations](./04-matter-summary-no-actions.png)

## v0.2 home / matter-scoped RAG

![v0.2 home](./01-v02-home.svg)

## Matter record write-back

![Matter record write-back](./02-matter-record.svg)

## Audit log with human edit

![Audit log with human edit](./03-audit-log.svg)

## Demo story

The demo flow demonstrates the product control loop:

1. Select a scoped matter.
2. Ask a source-grounded question.
3. Extract task candidates only when the answer contains discrete recommendations.
4. Generate an action proposal or task batch.
5. Edit the operational fields before approval.
6. Write the approved action to the matter record.
7. Preserve both the original model proposal and final approved action in the audit log.
