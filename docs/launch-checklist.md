# Launch Readiness Checklist

This checklist models the cross-functional readiness work needed to ship an AI-assisted API workflow feature.

## Feature

AI-assisted matter action workflow with structured task candidates, approval-gated write-back, API documentation, and audit log.

## Release summary

The release allows users and API consumers to ask matter-scoped questions, receive source-grounded answers, review structured task candidates, approve actions, and verify write-back through an audit log.

## Customer value

- Reduces manual translation from matter context to operational work.
- Helps users identify missing documents and follow-up items.
- Keeps AI-generated changes reviewable before write-back.
- Gives integrators a structured API response instead of unstructured chat text.
- Preserves traceability through source references and audit logs.

## Launch checklist

### Product

- [x] Product spec drafted.
- [x] API contract documented.
- [x] Acceptance criteria documented.
- [x] Known limitations documented.
- [x] Demo flow validated locally.

### Engineering

- [x] API server runs locally with Swagger UI.
- [x] `/ask` returns structured task candidates.
- [x] `/actions/propose` returns proposal without write-back.
- [x] `/actions/approve` writes approved action to local store.
- [x] `/audit` returns approved actions.
- [ ] Automated tests added.
- [ ] Auth and permission model defined.
- [ ] Idempotency and retry behavior defined for write endpoints.

### QA

- [x] Manual acceptance tests documented.
- [ ] Invalid body handling verified.
- [ ] Invalid matter handling verified across endpoints.
- [ ] No-task informational answer scenario verified.
- [ ] Factual bullets do not become task candidates.
- [ ] Approval write-back creates audit record.

### Support readiness

- [ ] Support summary drafted.
- [ ] Common troubleshooting scenarios documented.
- [ ] Known limitations shared.
- [ ] Error behavior documented.

### Sales / GTM readiness

- [ ] Customer-facing value statement drafted.
- [ ] Demo narrative prepared.
- [ ] Non-goals clarified to avoid overpromising.
- [ ] Legal/compliance caveats reviewed.

### Partner readiness

- [x] Swagger UI available locally.
- [x] API docs include curl examples.
- [ ] Webhook/event payload documented.
- [ ] Schema versioning documented.
- [ ] Sandbox data reset instructions documented.

## Support enablement notes

### What changed?

The prototype now exposes a FastAPI layer for matter-scoped AI actions. API users can call `/ask` to get an answer, sources, and structured task candidates. Proposed or candidate actions still require explicit approval before write-back.

### What should Support know?

- `404 Matter not found` means the requested matter ID does not exist in the local demo data.
- `422 Unprocessable Entity` usually means the request body has the wrong field name or missing required field.
- `/ask` expects `question`, while `/actions/propose` expects `request`.
- Apple touch icon 404s in the terminal are harmless browser favicon requests.

### Expected questions

**Q: Why did no task candidates appear?**

A: The answer may have been informational only. The extractor is designed to avoid creating tasks from plain facts or background context.

**Q: Why did the API return 422?**

A: The request body likely used the wrong field. `/ask` requires `question`; `/actions/propose` requires `request`.

**Q: Why does the action not write immediately after proposal?**

A: Proposals are intentionally read-only. Write-back only happens through `/actions/approve`.

## Known limitations

- Local-only prototype.
- Fake matter data.
- No production auth, permissions, or tenant isolation.
- No real Filevine API integration.
- Rule-based task candidate confidence.
- Manual acceptance tests only.
- Source references are chunk-level.

## Release note draft

Mini LOIS CaseOps API now exposes structured task candidates from matter-scoped AI answers. The `/ask` endpoint returns an answer, supporting sources, and action candidate objects that include title, action_type, reason, confidence, source_refs, and original_text. AI-generated actions remain approval-gated: proposed actions do not mutate the matter record until submitted through `/actions/approve`. Approved actions are written to the local matter record and preserved in the audit log.
