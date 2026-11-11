# Data Model: Submission and Safety Outcomes

## Persistent entities

### IdeaSubmission (existing)

| Attribute | Type / rule |
|-----------|-------------|
| submission_id | Existing primary key; also the final-submission idempotency boundary. |
| subject_ref | Existing owner reference; required for every read and write. |
| schema_version | Existing canonical schema association, unchanged. |
| status | `in_progress` or `submitted` for this workflow; only explicit finalization changes it to `submitted`. |
| submitted_at | New nullable timezone-aware timestamp; set once at finalization and returned unchanged on retry. |
| created_at / updated_at | Existing timestamps; ordinary retries must not alter the confirmed submitted outcome. |

One submission has its existing FieldValue records. Finalization does not copy, delete,
or create another idea. The acknowledged fresh intake is a different IdeaSubmission.

**Migration**: Add nullable `submitted_at` in the next Alembic revision after
`0002_human_only_field_constraints`. Existing drafts remain `in_progress` with null
timestamp; never infer historical submission from completeness. Downgrade drops only this
new column. Verify both upgrade and downgrade/re-upgrade on disposable databases.
No canonical-field/schema-version changes and no persistent safety-notice table.

### FieldValue (existing)

Keep the existing unique `(submission_id, field_key)`, origin restrictions, canonical value
validation, and NoFacts proof checks. Both AI and human mutation paths acquire the common
parent write lock and reject a submitted parent before any update. Rejected replacement
candidates leave existing values unchanged.

## Derived and transient entities

### SubmissionReadiness

| Attribute | Rule |
|-----------|------|
| ready | True only if all required canonical values and declarations validate. |
| missing_fields | Distinct canonical field keys for missing required values in canonical order. |
| invalid_fields | Distinct canonical field keys for present but invalid required values/origins in canonical order. |

Readiness is derived from stored values, not browser truthiness. Validate exactly the 18
mandatory definitions plus the three explicit declaration conditions (deduplicating overlap).
For stored booleans accept only `true`/`false` before decoding; declaration acceptance must
be true. Date and signature must satisfy current canonical validation and all three
declarations must have `human_entered` origin. Optional empty fields do not block submission.
Submitted records have terminal status regardless of their derived readiness.

### SafetyNotice

| Attribute | Rule |
|-----------|------|
| code | Literal `NO_FACTS_REJECTED`. |
| status | Literal `denied`; describes excluded candidates, never the intake lifecycle. |
| reason | Literal `NoFacts`. |
| reasons | Distinct codes in fixed order: number, percentage, cost, date, word_quantity. |

A turn has either null notice or one notice. A known rejection with unavailable detail
may carry an empty reason list; the UI explicitly states detail is unavailable. Classification
normally always supplies at least one reason. Unknown or malformed payloads are explicit
protocol errors, not implicit evidence of safe acceptance.

Never include rejected value, field value, transcript, filename, excerpt, model reasoning,
or personal information. Notices stay transient; existing bounded WebSocket replay may
cache safe codes but no new storage of rejected content is added.

### SubmissionOutcome

Confirmed result: existing session identity, `status: submitted`, immutable `submitted_at`.
Failed validation: safe field-key lists and a domain error. Unknown outcome is a client
state caused by no authoritative response, never a persisted submission status.

### WorkspaceLifecycle (client only)

`editing -> submitting -> confirmed -> starting_fresh -> editing(new generation)`

Recovery transitions:

- `submitting -> validation_failed -> editing` retains the draft and points to required fields.
- `submitting -> outcome_unknown -> recovering`; a successful state read either establishes
  `confirmed` or returns to `editing` for retry against the same session.
- Failed recovery remains `outcome_unknown`, frozen, with explicit retry.
- `starting_fresh -> fresh_start_failed -> starting_fresh` retries fresh preparation only.
  Keep the old submitted intake frozen. If a new session was already allocated, reuse its ID
  to finish field loading/connection rather than allocating another on each retry.

Store generation/session identifiers, active operation count, declaration dirty/busy flags,
shown-notice IDs, confirmed receipt, and the next-session setup identifier in App lifecycle
state/refs. This is not a new persistent model or browser-storage system.

Confirmed lifecycle state also records whether the success modal was dismissed. Escape
or Close changes only that flag and exposes the frozen submitted summary with Start a
new idea; it does not enter starting_fresh or reopen the modal on duplicate delivery.
Nonmodal notices have no dialog-open state, focus trap, or modal acknowledgment gate.
Keep one banner per operation. Correction correlation is client-only and contains no
input text, filenames, or rejected content:

| Attribute | Rule |
|-----------|------|
| correction_target | Null or one existing notice key `(generation, session_id, request_id)` selected by Correct this input. |
| corrects_operation | Immutable snapshot of correction_target on the next dispatched chat/upload operation; null for an unlinked operation. |

Show the selected target and Cancel correction without repeating rejected content. Selecting
another target replaces it; cancellation or dismissing that target clears the undispatched
selection. Dispatch consumes the selection once; canceled file selection or local validation
before dispatch does not consume it. Already-running operations keep their original snapshot.
Keep corrects_operation across fallback using the same logical request ID; no server
schema, HTTP body/header, or WebSocket payload addition is needed.

Clear only the linked target after a current-generation authoritative result has at least
one accepted field update, no field-validation failure, and explicitly null safety_notice.
Field-validation failure is an error reported by the existing operation result/error channel,
not new per-candidate diagnostic metadata; invalid-only input has no accepted updates.
Errors, zero accepted updates, legacy-absent metadata, and mixed/rejected results leave the
target unchanged. A rejected correction receives its own deduplicated banner. Retain
cleared/dismissed notice keys for the current generation so replay cannot resurrect them.
Generation reset clears selection, links, and notice keys; no browser storage is introduced.

### Email value constraints

Apply the exact FR-018 policy in [spec.md](spec.md) to both incoming email values and
stored mandatory-email readiness. Use the existing backend canonical validator as the
authority; avoid a second divergent frontend regex. "Every xn-- label, not only the final
label, MUST decode, validate, and round-trip under strict IDNA2008 without UTS #46 or
transitional mappings, comparing ASCII labels case-insensitively." Use the third-party
idna implementation, not Python's built-in IDNA2003 codec or bare punycode decoding.
No field count, required flag, origin policy, or stored value is silently changed.

## Atomicity and race invariant

Every write and final-submit transaction locks the same IdeaSubmission before reading
its current status or field set. PostgreSQL uses a parent row lock; SQLite begins an
immediate write transaction before reads. Do not use a process-local mutex as the guarantee.
Authorization is enforced inside the authoritative transaction as well as at the route boundary.

Finalization validates all current values, sets status and timestamp, and commits once.
A second finalization returns the existing receipt. An AI/human write serialized after
finalization fails explicitly. Long extraction may run outside the transaction, but must
recheck status when entering the locked persistence path.

The client drains active work before Submit, freezes editing while pending/unknown/confirmed,
and discards stale callbacks by generation and session. Server checks protect additional
tabs/workers, not only the current UI.

## Reset invariant

Only success acknowledgment starts reset. After a new session and its empty field state
are ready, replace the intake generation and all child-local state atomically: fields,
declarations, notes, chat, composer, selected-source control, clarification, errors, progress,
and notices. Restore focus to the new message input. Close the prior connection and clear
operation-specific deduplication state. Preserve the submitted database record.

Reset and feedback produce zero sessionStorage/localStorage writes. Native dialogs and
inline banners require no portal; any owned portal introduced during implementation must
be removed on unmount. Resource tests count owned nodes, listeners, timers, and connections,
not unrelated global browser resources.
