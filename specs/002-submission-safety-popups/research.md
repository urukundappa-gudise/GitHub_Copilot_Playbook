# Research: Submission Confirmation and Safety Denial Popups

## 1. Final submission identity and recovery

**Evidence**: [repositories.py](../../backend/src/aimplify_intake/persistence/repositories.py)
creates an `IdeaSubmission` as `in_progress`; [models.py](../../backend/src/aimplify_intake/persistence/models.py)
already gives it a unique identifier and status. [app.py](../../backend/src/aimplify_intake/api/app.py)
has session creation and field reads but no final-submit transition.

**Decision**: Finalize the existing record through an authenticated HTTP action. Its
identifier is the idempotency boundary: every retry for that session returns the same
submitted identity and timestamp. Add nullable `submitted_at`; derive readiness without
inventing a persisted ready state. Recover an unknown response using the existing field
read extended with `submitted_at` and readiness.

**Rationale**: Reset must not delete the idea; explicit finalization must be independently
verifiable. Reusing the record prevents duplicate submitted ideas without an idempotency table.

**Alternatives considered**: Treating completion as submission violates the confirmed user
choice. Browser-only success cannot prove persistence. Creating a second submission record
adds identity and retention complexity with no feature benefit.

## 2. Transactional finalization and write races

**Evidence**: [repositories.py](../../backend/src/aimplify_intake/persistence/repositories.py)
currently commits inside both AI and human write helpers. Authorization and extraction in
[app.py](../../backend/src/aimplify_intake/api/app.py) are separate from writes.

**Decision**: Centralize a transaction-scoped editable-submission guard. On PostgreSQL,
all human/AI writes and finalization acquire `SELECT ... FOR UPDATE` on the same parent
row before reading status or values. SQLite uses an explicit immediate write transaction
before the corresponding reads, not ineffective `FOR UPDATE`. Ensure the first database
statement establishes the chosen lock; the transaction caller commits once. Roll back
errors and re-read state on bounded contention recovery; never return success on a lock error.
Run extraction outside the locked section when possible, but recheck editable status before
persisting. Finalization checks current stored values under the same lock.

**Rationale**: An endpoint-only status check permits late writes after success. A common
lock establishes a serial order: a write either commits before final validation or fails
after finalization. Caller-owned transaction boundaries avoid accidentally releasing locks.

**Alternatives considered**: UI-only disabling does not protect another tab or worker.
Process-local locks do not protect multiple workers. Locking only finalization misses
concurrent writers. A new revision field is unnecessary if every mutation obeys the parent lock.

## 3. Readiness and stored-value validation

**Evidence**: [validation.py](../../backend/src/aimplify_intake/schema/validation.py) validates
incoming booleans as Python booleans but stores them as strings. Declaration controls in
[HumanDeclarations.tsx](../../frontend/src/components/HumanDeclarations.tsx) save separately
from final submission and can contain unsaved local edits.

**Decision**: Reuse canonical definitions, origin checks, and value validation in a shared
readiness helper. Decode stored boolean strings only when exactly `true` or `false`;
reject any other representation. Check all 18 mandatory fields and explicitly require
`declaration_accepted == true`, valid date, nonempty signature, and human origin for the
three declarations. Return stable field keys, never values, for missing/invalid items.
Expose readiness to the UI but re-evaluate it in the finalization transaction.

**Rationale**: Presence alone is not validity; `"false"` is a nonempty string, and feeding
stored `"true"` directly into the incoming boolean validator incorrectly fails.
Frontend dirty/busy tracking prevents submitting stale saved declarations.

**Alternatives considered**: Counting populated fields or trusting client readiness misses
invalid data and races. Resubmitting the entire draft in the Submit request duplicates validation.

## 4. NoFacts classification without policy changes

**Evidence**: [no_facts.py](../../backend/src/aimplify_intake/safety/no_facts.py) has six
existing patterns and recursive leaf traversal but returns only pass/drop.
[extraction.py](../../backend/src/aimplify_intake/services/extraction.py) drops rejected
candidates before graph updates; safe candidates carry a mutation-sensitive validation proof.

**Decision**: Introduce one classifier returning the set of matched categories using these
same patterns: `number`, `percentage`, `cost`, `date`, `word_quantity`. Both word-quantity
patterns map to `word_quantity`. Multiple categories can apply to one candidate, and their
union determines drop, preserving the existing behavior exactly. Delegate pass/drop helpers
to the shared classification predicate, preserving their public return types and validation proof.
The detailed extraction path aggregates distinct category codes only from known canonical
candidate fields evaluated by the existing gate.

**Rationale**: Shared detection prevents reason drift. A percentage can legitimately match
both `number` and `percentage`; reporting both is accurate rather than applying a new policy.
Unknown fields and ordinary field-validation failures do not become invented safety denials.

**Alternatives considered**: Client-side inspection misses documents and transcripts.
Model-generated reasons are nondeterministic and may expose content. Including dropped
values in results, logs, or new history would violate privacy and silent-drop invariants.

## 5. Equivalent HTTP and WebSocket notices

**Evidence**: [app.py](../../backend/src/aimplify_intake/api/app.py) routes source and message
processing through common text processing. WebSocket turns emit updates, clarification,
then a terminal `server.submission.status`. [intake.ts](../../frontend/src/services/intake.ts)
currently completes the turn at that event and regenerates request IDs on each transport call.

**Decision**: Add `safety_notice` to HTTP results and to the terminal WebSocket status payload,
not as a new terminal error. Keep source-completed behavior unchanged. Aggregate safe updates,
one existing clarification, and optional notice in the same logical result. Allocate a
logical input request ID in the caller and reuse it across transport fallback; deduplicate
banner presentation by session and request ID. Notices include literal status denied and
reason NoFacts, distinct from top-level intake status. Keep notices in normal typed results, not
exceptions, so a denial cannot accidentally trigger transport retry.

**Rationale**: Mixed acceptance is a successful processing operation with excluded values.
A terminal status payload avoids adding a separately ordered event the current client might miss.

**Alternatives considered**: A new error for any rejection discards safe updates and masks
partial acceptance. Independent UI detection duplicates gate policy. This feature does not
introduce durable message replay or exactly-once extraction across transports.

## 6. Reset ownership, unknown outcome, and dialog accessibility

**Evidence**: [App.tsx](../../frontend/src/App.tsx) owns session and field state;
[IntakeChat.tsx](../../frontend/src/components/IntakeChat.tsx) owns messages and composer;
[HumanDeclarations.tsx](../../frontend/src/components/HumanDeclarations.tsx) owns declaration
edits; [SourcePicker.tsx](../../frontend/src/components/SourcePicker.tsx) owns a file control.
No dialog library is declared in [package.json](../../frontend/package.json).

**Decision**: Keep lifecycle state in App and key the entire intake-local subtree by an
intake generation. Guard all callbacks with generation/session checks, close the previous
socket, and remount the subtree only when a new session and empty field state are ready.
Track active operations and dirty declarations; freeze them during finalization and recovery.
Use a native `dialog.showModal()` confirmation wrapper and a separate inline nonmodal
SafetyDenialBanner. The employee selected banner role=alert without aria-modal/focus trap.
Confirmation uses role=dialog/aria-modal=true and separate aria-live=polite status text.
Escape/Close hides confirmation without reset; a frozen summary retains Start a new idea.
Denial dismissal does not steal focus on arrival and handles Escape only within the banner.

**Correction correlation (A1)**: The employee selected an explicit Correct this input
action, not inference from a shared input control. App holds one visible, cancelable
target notice key. The next dispatched chat/upload snapshots it client-side and consumes
the selection; fallback keeps the snapshot, and already-running operations cannot take it.
Only accepted updates with no field-validation failure and explicitly null safety_notice
clear the linked earlier banner. Empty, failed, legacy-absent, and mixed/rejected results
preserve it; unrelated notices remain. Cleared/dismissed keys prevent replay resurrection.
No transport/schema addition or storage of rejected content is necessary. A shared-control
heuristic was rejected because concurrent operations need not correct one another.

**Rationale**: Resetting just App fields leaves child state behind. A generation prevents
late completions from contaminating new state. Native modality avoids a new dependency,
but browser validation is required because jsdom does not prove focus containment or layout.

**Alternatives considered**: Page reload risks unknown-submit resubmission and poor recovery.
Clearing local storage does not reset component state. A modal denial was rejected by the
employee. Escape may dismiss confirmation but never acknowledge success or reset.

## 7. Verification workflow

**Decision**: Extend existing pytest contract/integration/safety tests, Vitest app and flow
tests, and the golden runner expectations. Use existing Alembic upgrade commands and
TypeScript/lint/build scripts. Run PostgreSQL concurrency checks in addition to SQLite;
test real-browser focus, 320-pixel layout, 200% zoom, and the one-second display bound.
Add extraction metadata unit tests, banner component tests, storage-write spies, and
owned-resource counts over 100 feedback and 10 fresh-intake cycles.

**Rationale**: The golden manifest requires >=50 cases, all six sections, five safety
categories, chat/document/audio, human-only protection, and single-question pacing.
Passing a UI mock suite alone cannot establish source privacy, persistence, or transaction correctness.

**Alternatives considered**: Adding a new test framework or treating mocked dialog behavior
as accessibility proof is unnecessary. Existing tests may be extended without new tooling.

## 8. Email policy refinement (F-04)

**Decision**: The employee approved the exact ASCII/punycode syntax and length limits in
FR-018 of [spec.md](spec.md). Use one canonical backend validator for extraction and stored
readiness. For A2 the employee selected strict IDNA2008 without UTS #46 or transitional
mappings. Decode, validate, and re-encode every xn-- label, comparing ASCII labels
case-insensitively; do not treat a prefix or raw punycode round-trip as validation.
Declare idna>=3,<4 as a direct runtime dependency and regenerate backend/uv.lock during
implementation. Python's built-in codec implements IDNA2003 and is not an alternative.
Profile fixtures include xn--fa-hia.de as valid, xn--e28h.de (emoji) as invalid, malformed
A-labels, and an invalid non-final xn-- label followed by an otherwise valid TLD.
Existing invalid stored email blocks finalization without deletion or silent replacement.

**Rationale**: The existing dot-only regex does not enforce a meaningful TLD policy.
Syntactic validation must be deterministic and must not imply mailbox/domain existence.

**Alternatives considered**: Raw Unicode, quoted local parts, IP literals, numeric TLDs,
DNS lookup, and a second client regex are excluded by the agreed scope.

## 9. Contract type and gate enforcement (F-01, F-02, F-06)

**Decision**: Replace affected bare response assertions with guarded unknown decoding.
Enforce no explicit/implicit any in outcome data, exhaustive states, no floating promises,
and no unreachable handlers with existing lint/TypeScript tooling. Test errors explicitly.
Create one scripts/verify.ps1 entry point used by a tracked .githooks/pre-push launcher and
CI. Installation must inspect existing hook configuration and stop for conflicts, not
overwrite user hooks. Require PowerShell 7/uv/Node and disposable PostgreSQL for that gate.

**Rationale**: CI currently discovers ordinary pytest/Vitest suites, but no active pre-push
hook was found; frontend lint and PostgreSQL race tests need explicit CI wiring. Workflow
existence alone does not establish required GitHub merge checks.

**Alternatives considered**: Separate diverging local/CI command lists, optional database
checks in required mode, and declaring quality scores without executable evidence are rejected.
No new test framework is needed. Native dialog and inline banner require no portal.

All research questions are resolved. Existing CI/startup/migration evidence and runnable
commands are consolidated in [quickstart.md](quickstart.md).
