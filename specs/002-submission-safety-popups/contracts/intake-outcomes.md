# Interface Contracts: Intake Outcomes

These are planned additive contracts, not claims about the current implementation.
Existing identity-cookie, allowed-origin, ownership, size, source-format, and human-only
policies remain authoritative. JSON field names use existing snake_case conventions.

## 1. Final submission

### POST `/api/v1/sessions/{session_id}/submit`

Authenticated, allowed-origin, owner-only finalization of the existing session. No field
values are accepted in the request; use an empty JSON object. The session identifier
provides idempotency, including across response loss, reconnect, or worker restart.

Success: `200 application/json`, returned only after commit:

```json
{
  "session_id": "opaque-existing-session-id",
  "status": "submitted",
  "submitted_at": "2026-11-10T11:00:00Z"
}
```

Repeated calls for the same submitted session return the same identity and timestamp.
Only one transition occurs. Missing/invalid information: `422`:

```json
{
  "error": {
    "code": "SUBMISSION_INCOMPLETE",
    "message": "Complete the required information and save your declaration before submitting.",
    "request_id": "opaque-error-id",
    "missing_fields": ["submitter_signature"],
    "invalid_fields": ["declaration_accepted"]
  }
}
```

Lists contain only known canonical field keys, no submitted values. Ordinary errors
retain the repository envelope: 401 `UNAUTHENTICATED`, 403 `FORBIDDEN`,
404 `SESSION_NOT_FOUND` for missing or unowned records, and explicit 503
`SERVICE_UNAVAILABLE` for unavailable persistence. Unexpected server errors remain
non-success responses with no raw exception or input details.

Do not pass new domain exceptions through the existing generic HTTPException mapping
that would erase their codes or safe field lists. Add narrowly typed domain error handling.
The frontend must preserve code/status/field lists in a typed error instead of flattening
every error into an unstructured string.

A timeout/disconnect is unknown, not successful. Read field state for this same session;
if still in progress, retry this endpoint against the same identity. Never allocate a new
session as a submission retry.

## 2. Authoritative state and readiness

### GET `/api/v1/sessions/{session_id}/fields`

Preserve `session_id`, `schema_version`, `sections`, `status`; add:

```json
{
  "submitted_at": null,
  "readiness": {
    "ready": false,
    "missing_fields": ["submitter_signature"],
    "invalid_fields": []
  }
}
```

For submitted sessions, status is `submitted` and submitted_at is the original timestamp.
The readiness structure follows [data-model.md](../data-model.md); clients cannot use it
to bypass server finalization validation. Refresh state after saved changes as needed;
before Submit the UI must have no active work or unsaved declaration edits.

All field/message/source mutation routes reject a submitted session with HTTP `409`,
code `SUBMISSION_CLOSED`, message `This idea has already been submitted.` Writes are
rechecked inside the common locked transaction, not only at route entry.

## 3. Turn results and safety notices

HTTP message and source results preserve their existing response fields and add a required
`safety_notice` for the upgraded server:

```json
{
  "request_id": "logical-input-operation-id",
  "field_updates": [
    {
      "field_key": "problem_statement",
      "value": "Manual routing delays approvals.",
      "origin": "ai_extracted"
    }
  ],
  "clarification": {
    "field_key": "idea_title",
    "question": "What is the title of your idea?"
  },
  "status": "in_progress",
  "safety_notice": {
    "code": "NO_FACTS_REJECTED",
    "status": "denied",
    "reason": "NoFacts",
    "reasons": ["number", "percentage"]
  }
}
```

No rejection means `"safety_notice": null`. Reason codes are deduplicated and ordered:

The notice's `status: "denied"` and `reason: "NoFacts"` describe excluded candidates.
Top-level `status` remains the intake lifecycle (`in_progress` or `submitted`); mixed safe
updates never mark the whole idea denied. Both fields are required literal values for a
present notice and must survive extraction, graph, HTTP, WebSocket, and client decoding.

| Code | Fixed user-facing explanation |
|------|-------------------------------|
| number | Information containing unverified numbers was not accepted. |
| percentage | Information containing unverified percentages was not accepted. |
| cost | Information containing unverified costs was not accepted. |
| date | Information containing unverified dates was not accepted. |
| word_quantity | Information containing unverified quantities written as words was not accepted. |

Do not insert candidate text into copy. Multiple matching categories may be shown once
each. A known rejection with `reasons: []` displays `NoFacts rejected some information,
but the detailed reason is unavailable.` Unknown reason codes are not fabricated explanations;
report an explicit protocol problem without leaking the payload.

The nonmodal banner title is `Some information was not accepted`; its body describes security
validation, applicable reasons, and the correction action `Please describe the idea
without unsupported claims.` This is not an access denial and must not say the entire
idea was rejected. An entirely rejected turn still preserves the draft and existing
clarification behavior.

### WebSocket parity

Retain subprotocol `aimplify.intake.v1`, update events, at most one clarification, and
source completion. Add the same optional notice to the existing terminal status payload:

```json
{
  "type": "server.submission.status",
  "request_id": "logical-input-operation-id",
  "payload": {
    "status": "in_progress",
    "safety_notice": {
      "code": "NO_FACTS_REJECTED",
      "status": "denied",
      "reason": "NoFacts",
      "reasons": ["word_quantity"]
    }
  }
}
```

The upgraded client assembles updates, clarification, and notice before resolving the
turn. It must not interpret a safety notice as `server.error` or retry merely because a
candidate was rejected. A closed-submission mutation emits a correlated `server.error`
with `SUBMISSION_CLOSED`, without any field-update events. Cover both message and source
commit paths; preserve source buffer cleanup.

Allocate one logical request ID per user operation and reuse it in WebSocket messages,
HTTP message bodies, or HTTP `x-request-id` on source upload. Cache only safe WebSocket
result metadata as before; no durable request replay is introduced. Deduplicate popup
presentation using `(session_id, request_id)`, not notice text.

### Rollout

Deploy server additions before or alongside the client. Existing clients ignore additive
fields; the upgraded client may accept a missing safety_notice from legacy servers as
an explicit compatibility case, but never claim this proves no rejection. Full feature
acceptance requires the upgraded server on every input path. Present-but-invalid notice
structures fail explicitly, not as success-shaped defaults.

## 4. UI outcome contract

| State / action | Required behavior |
|----------------|-------------------|
| Editing | Submit identifies missing information; unsaved declarations explain that saving is required. |
| Active input/save | Do not finalize until all active operations finish; prevent new operations once Submit starts. |
| Confirmed success | One modal titled `Idea submitted`; freeze old intake; action `Start a new idea`. No reset before action. |
| Unknown outcome | Distinct outcome-unknown notice and recovery action; no success or reset; editing stays frozen until resolved. |
| Start-new failure | Explain submission succeeded but a new intake could not be prepared; retry preparation only. |
| Dismiss confirmed modal | Escape or Close hides the modal without reset; focus moves to Start a new idea on the frozen submitted summary. Duplicate receipts do not reopen it. |
| NoFacts denial | One inline nonmodal banner per logical operation; editing remains available; actions Dismiss and Correct this input. No modal acknowledgment gate before Submit. |
| Correction selection | Show the selected operation without rejected content; Cancel correction clears the selection; selecting another banner replaces it. |
| New valid input | No inherited denial from an earlier operation. |

OutcomeDialog owns only confirmation modality: `role="dialog"`, `aria-modal="true"`,
aria-labelledby/aria-describedby, native showModal focus containment, initial focus on
Start a new idea, and a separate confirmation status region with `aria-live="polite"`.
Do not give the dialog container role=alert. Escape/Close dismiss only the modal and
focus the summary action; background click does neither dismiss nor reset. Activating
Start a new idea in either location starts fresh preparation.

SafetyDenialBanner owns inline feedback: `role="alert"` with its implicit assertive live
semantics, accessible title, and native Dismiss and Correct this input buttons. It has no aria-modal, showModal,
focus stealing, or focus trap. Do not override the alert with aria-live=polite. Escape
inside a focused banner dismisses it; Escape elsewhere is not intercepted. Dismissal
from the banner returns to the operation's initiating control if still available.
Use normal Tab/Shift+Tab order and no positive tabindex on either component.

Distinct overlapping operations render separate deduplicated banners rather than
overwriting or queueing a focus-blocking modal. Correct this input selects a notice key
`(generation, session_id, request_id)` and focuses the chat composer; an employee may instead
choose an upload. The next dispatched chat/upload snapshots that key as client-only
corrects_operation, consumes the selection once, and retains the snapshot across fallback.
No HTTP/WebSocket wire-field change is required. File-picker cancellation or validation
before dispatch preserves the selection; already-running operations cannot consume it.
Dismiss cancels an undispatched selection for that target.

Only an authoritative current-generation result with at least one accepted field update,
no field-validation failure, and explicitly null safety_notice clears the linked target.
Here field-validation failure means a validation error reported through the existing
operation result/error channel, not hidden per-candidate diagnostics. The accepted-update
condition excludes invalid-only input that produces no updates; no new diagnostic field
or rejected-value retention is introduced.
Errors, zero accepted updates, legacy-absent metadata, or mixed/rejected results preserve
it; a new rejection gets a separate banner. Unlinked operations never clear other notices.
Deduplication retains cleared/dismissed keys until generation reset so duplicate delivery
cannot reopen feedback. All outcomes wrap and
scroll as needed at 320 CSS pixels and 200% zoom. Generation changes clear old notices
and callbacks. Existing employee message history may remain, but dropped claims never
reappear as assistant facts or in notices.

Cancel correction returns focus to the selected banner's correction button if it survives,
otherwise to the composer. Both correction actions follow normal keyboard order.

## 5. Typed handling, email, and resource boundaries

Decode JSON from `unknown` through guards; remove the existing request<T> bare `as T`
response assertion in the affected client path. Denial metadata and popup/banner state
must have zero explicit or implicit any and no non-null/double casts to bypass validation.
Use exhaustive discriminated lifecycle handling; rejected requests, JSON parse failures,
WebSocket errors, dialog setup failures, reset failures, and retry failures have safe
typed failure feedback. Floating promises and unreachable branches fail verification.

The canonical backend validator enforces FR-018 email syntax and stored readiness; no
DNS calls or schema-field changes. Contract tests cover false-TLD addresses and existing
stored invalid emails as well as approved valid ASCII/punycode fixtures. Validate every
xn-- label using strict IDNA2008 decode/validation/re-encode with no UTS #46 or transitional
mappings; compare the ASCII round-trip case-insensitively. The built-in Python IDNA2003
codec and bare punycode decoding do not satisfy this contract.

Mount/reset must write nothing to browser storage. Test 100 feedback mount/dismiss cycles
and 10 fresh-intake cycles, with zero retained owned resources after teardown. No portal
dependency is necessary; any introduced owned container is removed when its owner unmounts.
