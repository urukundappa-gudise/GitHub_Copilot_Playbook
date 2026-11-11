# Tasks: Submission Confirmation and Safety Denial Popups

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/intake-outcomes.md](contracts/intake-outcomes.md), and [quickstart.md](quickstart.md).

**Prerequisites**: Existing React/TypeScript, FastAPI/SQLAlchemy, Alembic, pytest, Vitest,
golden runner, and the approved 2026-11-10 refinement. No application scaffolding is needed.

**Tests**: Required by FR-016 and the constitution. Write the specified tests first and
confirm behavioral failures before implementation. Missing dependencies are not behavioral
test failures. Mark tasks complete only after their implementation/verification succeeds.

**Refinement**: All eight original analysis gaps and follow-up findings A1/A2 are addressed below as planned remediation, not
verified closure. Confirmation is modal; denial is a nonmodal banner. Success Escape/Close
does not reset; it exposes a frozen summary with Start a new idea. Email follows FR-018.
Existing T001-T052 IDs are retained for this refinement. A1 uses an explicit client-only
correction link; A2 uses strict IDNA2008 without UTS #46/transitional mappings. No application
code, dependency manifest, or lockfile is changed by task generation.

## Format: `[ID] [P?] [Story] Description`

- Every task uses an unchecked checkbox, sequential ID, exact repository-relative paths,
  and a story label only within its story phase.
- `[P]` allows file-disjoint work only after listed prerequisites; never race shared files.
- Protect unrelated worktree edits, canonical counts, origin boundaries, identity checks,
  NoFacts proof checks, RAM-only ingestion, one-question pacing, and the golden merge gate.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the existing project and establish a reproducible baseline.

- [ ] T001 Confirm `.specify/feature.json` and commands in `backend/pyproject.toml`, `frontend/package.json`, and `specs/002-submission-safety-popups/quickstart.md`; run existing targeted intake/safety suites, record pre-existing failures in the implementation session, and restore dependencies only after a missing-dependency failure or manifest change.
- [X] T002 Inventory all mutation/commit callers in `backend/src/aimplify_intake/persistence/repositories.py`, `backend/src/aimplify_intake/api/app.py`, and `backend/src/aimplify_intake/api/http.py`, child-local state in `frontend/src/components/`, and active workflow/hook configuration for `.github/workflows/ci.yml`; preserve callers and stop for existing hook conflicts rather than overwriting them.

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared database fixtures, typed domain failures, and contract vocabulary.

- [X] T003 [P] Add disposable separate-connection SQLite/PostgreSQL fixtures in `backend/tests/integration/persistence/conftest.py`; accept TEST_POSTGRESQL_URL only for isolated test data, refuse unspecified/shared targets, and use VERIFY_REQUIRED=1 to fail rather than skip when PostgreSQL is missing; document optional developer mode versus required gate mode in `specs/002-submission-safety-popups/quickstart.md`.
- [X] T004 [P] Define narrow incomplete/closed/unavailable submission errors in `backend/src/aimplify_intake/persistence/repositories.py` carrying fixed messages and canonical field keys only, separate from ordinary value validation; preserve typed failure identity across HTTP/WebSocket adapters and never retain rejected content.
- [X] T005 [P] Define guarded outcome contracts in `frontend/src/services/intake.ts`: readiness is "True only if all required canonical values and declarations validate."; missing_fields are "Distinct canonical field keys for missing required values in canonical order."; invalid_fields are "Distinct canonical field keys for present but invalid required values/origins in canonical order."; notice code is "Literal `NO_FACTS_REJECTED`."; notice status is "Literal `denied`; describes excluded candidates, never the intake lifecycle."; reason is "Literal `NoFacts`."; reasons are "Distinct codes in fixed order: number, percentage, cost, date, word_quantity."; receipt has "existing session identity, `status: submitted`, immutable `submitted_at`." Decode from unknown and preserve HTTP code/status/field lists.

**Checkpoint**: Complete T001-T005 before implementing story code. No new behavior is yet verified.

## Phase 3: User Story 1 - Confirm Final Submission and Start a Fresh Idea (Priority: P1)

**Goal**: Explicitly finalize a valid idea once; reset only on Start a new idea in the
confirmation modal or frozen summary, retaining the submitted database record.

**Independent Test**: Complete mandatory values and personally save declarations; Submit
and verify a committed receipt and one confirmation. Escape/Close must leave a frozen
summary without reset; Start a new idea must prepare a distinct empty intake. Exercise
incomplete/invalid email, unknown outcome, duplicate submit, races, and fresh-start failure.

### Tests for User Story 1

- [X] T006 [P] [US1] Add `backend/tests/contract/api/test_submission_outcomes.py` covering authenticated owner/origin-only empty-object submit, committed 200 receipt, safe-key 422 SUBMISSION_INCOMPLETE, unavailable 503, GET readiness/timestamp, idempotent retry, and closed 409 mutations across human/message/source HTTP and already-open WebSocket/source commit paths; include stored invalid-email finalization.
- [ ] T007 [P] [US1] Add `backend/tests/integration/persistence/test_submission_transactions.py` covering 18 mandatory fields, all three declaration origins, stored true/false decoding, invalid date/signature, optional blanks, immutable receipts, repeated/concurrent submission, lost-response retry, AI/human-write-versus-submit ordering on separate SQLite/PostgreSQL connections, and migration upgrade/downgrade/re-upgrade without row loss.
- [ ] T008 [P] [US1] Add `frontend/src/tests/submission-outcomes.test.tsx` with Given-When-Then-aligned cases for explicit Submit only, invalid/unsaved declaration feedback, active-work gating, duplicate receipts, unknown-state freeze/recovery, Escape/Close leaving a frozen summary and no reset, Start a new idea from both locations, complete child-state clearing, reused next-session setup ID, fresh-start failure, and ignored late callbacks.
- [X] T009 [P] [US1] Add `backend/tests/unit/test_email_validation.py` with FR-018 positive/negative boundary fixtures for ASCII dot-atom local parts, address/local/domain/label lengths, hyphens, valid round-tripping xn-- labels, malformed punycode, numeric/one-letter TLDs, raw Unicode, single-label domains, and IP literals; exercise shared validation through extraction and stored readiness without DNS or stored-value deletion. For A2 test strict IDNA2008 without UTS #46/transitional mappings on every A-label, including non-final labels: accept user@xn--fa-hia.de, reject user@xn--e28h.de and invalid non-final A-labels, compare ASCII round-trips case-insensitively, and distinguish IDNA2003/bare-punycode behavior.

### Implementation for User Story 1

- [X] T010 [US1] Extend `backend/src/aimplify_intake/persistence/models.py` and add `backend/alembic/versions/0003_submission_timestamp.py` after 0002: submitted_at is "New nullable timezone-aware timestamp; set once at finalization and returned unchanged on retry."; submission_id is "Existing primary key; also the final-submission idempotency boundary."; subject_ref is "Existing owner reference; required for every read and write."; schema_version is "Existing canonical schema association, unchanged."; status is "`in_progress` or `submitted` for this workflow; only explicit finalization changes it to `submitted`."; retries must satisfy "ordinary retries must not alter the confirmed submitted outcome." Preserve old drafts with null timestamp; downgrade removes only the new column.
- [X] T011 [US1] Tighten only email syntax in `backend/src/aimplify_intake/schema/validation.py` to FR-018: ASCII unquoted dot-atom local part <=64 without empty segments, address <=254, domain <=253, >=2 labels each 1-63 alphanumeric/hyphen characters without edge hyphens, final label 2-63 ASCII letters or a valid round-tripping xn-- label; reject raw Unicode/numeric TLD/IP literals/single-label domains, perform no DNS lookup, and reuse this authority in extraction and readiness without changing canonical field counts or duplicating a frontend regex. Enforce "Every xn-- label, not only the final label, MUST decode, validate, and round-trip under strict IDNA2008 without UTS #46 or transitional mappings, comparing ASCII labels case-insensitively." Declare idna>=3,<4 in `backend/pyproject.toml`, regenerate `backend/uv.lock` with uv without unrelated upgrades, and use that runtime library rather than Python's built-in IDNA2003 codec or bare punycode decoding; surface invalid labels through existing canonical validation feedback.
- [X] T012 [US1] Implement stored readiness in `backend/src/aimplify_intake/persistence/repositories.py` via the shared canonical validator: "For stored booleans accept only `true`/`false` before decoding; declaration acceptance must be true."; "Date and signature must satisfy current canonical validation and all three declarations must have `human_entered` origin."; "Optional empty fields do not block submission." Validate the 18 mandatory definitions plus declarations with overlap deduplicated; report ordered distinct keys, including invalid stored emails without modifying them.
- [X] T013 [US1] Implement the common parent-lock transaction and finalization in `backend/src/aimplify_intake/persistence/repositories.py`, preserving "existing unique `(submission_id, field_key)`, origin restrictions, canonical value validation, and NoFacts proof checks."; lock PostgreSQL parent rows or begin SQLite immediate write transactions before authoritative reads, recheck ownership/status, validate readiness under lock, set receipt once, and commit once in the transaction owner; update every affected caller and remove premature internal commits, with explicit rollback/contention errors and no process-local-lock substitute.
- [X] T014 [US1] Wire submit POST, additive GET readiness/submitted_at, narrowly typed errors, and persistence-time closed guards in `backend/src/aimplify_intake/api/app.py` and `backend/src/aimplify_intake/api/http.py`; include HTTP human/message/source mutations and WebSocket messages/source commits, correlated closed errors and buffer cleanup, and rechecks after long extraction so late work cannot mutate a submitted idea.
- [X] T015 [US1] Implement final-submit/read-state calls and guarded receipt/error decoding in `frontend/src/services/intake.ts`; replace the affected request<T> bare `as T` response assertion with decoder-backed unknown handling, preserve safe code/status/field lists, retry/recover using the same session, and never fabricate success from completeness or network failure.
- [ ] T016 [US1] Expose dirty/busy/disabled lifecycle coordination in `frontend/src/components/HumanDeclarations.tsx` for declaration and notes edits/saves; reject final-submit readiness while unsaved edits remain, disable frozen controls, preserve human-only ownership, and handle each save failure and unmount completion explicitly.
- [X] T017 [US1] Add parent-visible active-operation tracking and lifecycle disabling in `frontend/src/components/IntakeChat.tsx` and `frontend/src/components/SourcePicker.tsx`; count success/failure completions, preserve message/upload behavior outside submission, and guard stale callbacks after generation changes.
- [X] T018 [US1] Implement the explicit Submit lifecycle in `frontend/src/App.tsx`: drain active operations, block unsaved declarations with useful feedback, refresh server readiness, freeze submitting/outcome_unknown/confirmed states, recover authoritative state on the same session, and use exhaustive typed transitions and handled async failures with no success-shaped catches.
- [X] T019 [US1] Create confirmation-only `frontend/src/components/OutcomeDialog.tsx` and integrate it in `frontend/src/App.tsx`: title Idea submitted, Start a new idea and Close actions, role=dialog, aria-modal=true, labeled description, separate polite status announcement, and initial action focus; Escape/Close hides once into the frozen submitted summary and focuses its Start a new idea action, background clicks do nothing, and duplicate receipts cannot reopen the modal or trigger reset.
- [X] T020 [US1] Implement Start a new idea from modal/summary in `frontend/src/App.tsx`: acknowledgment alone starts fresh setup, closes the old socket, invalidates late callbacks, reuses an allocated next-session ID after partial setup failure, and atomically remounts all intake-local state only after fresh field loading; clear fields/declarations/notes/chat/composer/source/clarification/errors/progress/notices, retain submitted records, and add zero browser-storage writes.
- [ ] T021 [US1] Run `backend/tests/contract/api/test_submission_outcomes.py`, `backend/tests/integration/persistence/test_submission_transactions.py`, `backend/tests/unit/test_email_validation.py`, and existing human-only/intake tests together; prove disposable PostgreSQL and SQLite race/migration behavior, approved email outcomes, receipt idempotency and preserved callers, reporting missing database evidence as incomplete rather than passing.
- [ ] T022 [US1] Run `frontend/src/tests/submission-outcomes.test.tsx` with `frontend/src/tests/human_declarations.test.tsx` and `frontend/src/tests/intake-flow.test.tsx`; prove explicit-submit GWT cases, success dismissal without reset, complete acknowledgment reset, stale-result rejection, and unknown/fresh-start recovery before completing US1.

**Checkpoint**: US1 is independently demonstrable without denial feedback. Accessibility
and resource checks in US3 and release gates are still required for final acceptance.

## Phase 4: User Story 2 - Understand a NoFacts Rejection and Correct Input (Priority: P1)

**Goal**: Propagate exact safe denial metadata and render a nonmodal alert banner while
preserving accepted values, editing availability, existing gate decisions, and corrections.

**Independent Test**: Exercise every rejection category through chat and six source
formats on HTTP/WebSocket; verify nested denial status/reason, exact categories, no leaked
values, mixed acceptance, operation deduplication, and valid correction without reset.

### Tests for User Story 2

- [X] T023 [P] [US2] Extend `backend/tests/unit/safety/test_no_facts.py` and `backend/tests/unit/safety/test_no_facts_properties.py` for ordered category unions, nested leaves, overlapping patterns, pass/drop equivalence, and mutation-sensitive proof preservation using all six existing patterns; map both word-number patterns to word_quantity.
- [X] T024 [P] [US2] Extend `backend/tests/unit/test_extraction.py` for detailed safe-only, rejected-only, mixed, unknown-field and ordinary validation-failure results; assert literal status denied/reason NoFacts, deduplicated category-only metadata, unchanged legacy list interface, retained safe validation proofs, and no rejected content in results/errors.
- [ ] T025 [P] [US2] Add `backend/tests/contract/api/test_safety_notices.py` for HTTP and terminal WebSocket parity of safety_notice.status=denied, reason=NoFacts, code and ordered reasons, null safe results, mixed acceptance with intake status in_progress, unavailable detailed reasons, source event ordering, and distinct ordinary source errors.
- [ ] T026 [P] [US2] Extend `backend/tests/integration/test_no_facts_boundaries.py` with category-by-input-by-transport coverage for chat/PDF/DOCX/PPTX/WAV/MP3/WebM using RAM/provider fixtures; assert metadata survives graph/persistence/event paths, rejected replacements preserve old values, safe updates remain accepted, and rejected claims never enter records/notices/events/logs.
- [ ] T027 [P] [US2] Add `frontend/src/tests/safety-notices.test.tsx` for guarded HTTP/WebSocket literal metadata, malformed/unknown-code errors, documented legacy absence, same logical request ID on fallback, no denial-triggered retry, mixed acceptance, nonmodal role=alert banner rendering, no focus stealing, per-operation deduplication, unavailable detail, dismiss/correction without reset, and distinct concurrent notices. Cover US2.5/US2.8/US2.9: explicit Correct this input selection/replacement/cancel; next dispatched chat/upload consumes one snapshot while already-running operations and canceled file selection do not; accepted updates with no field-validation failure and explicitly null safety_notice clear only the linked target. Failures, empty/legacy/mixed/rejected results preserve it, new rejections get distinct banners, unlinked operations clear none, fallback retains links, dismissal cancels an undispatched target, and duplicate/old-generation results cannot resurrect or clear feedback.

### Implementation for User Story 2

- [X] T028 [US2] Add the shared classifier in `backend/src/aimplify_intake/safety/no_facts.py` using existing patterns only; preserve legacy pass/drop/proof behavior and "Distinct codes in fixed order: number, percentage, cost, date, word_quantity." with no rejected-value serialization.
- [X] T029 [US2] Add detailed extraction in `backend/src/aimplify_intake/services/extraction.py` while retaining the legacy list-returning interface; classify only known candidates actually dropped by the gate, distinguish ordinary validation failures, preserve proof-carrying safe updates, and enforce "A turn has either null notice or one notice." with literal code/status/reason and no new rejected-content retention.
- [X] T030 [US2] Propagate the notice with field_updates through `backend/src/aimplify_intake/graph/intake_graph.py`; retain mixed safe values and at most one existing clarification question, and do not treat alert copy as another question or failure.
- [X] T031 [US2] Wire notice metadata through `backend/src/aimplify_intake/api/app.py` for all HTTP input paths and terminal WebSocket status payloads, preserving top-level intake status, correlated operation IDs, source-completed ordering, safe bounded replay, closed-write guards, and RAM buffer cleanup; never encode a normal safety notice as server.error.
- [X] T032 [US2] Implement decoder-backed safety metadata and caller-owned logical operation IDs in `frontend/src/services/intake.ts`; reuse IDs across transport fallback, assemble notices before terminal resolution, distinguish explicit legacy absence from safe acceptance, and enforce "Unknown or malformed payloads are explicit protocol errors, not implicit evidence of safe acceptance." without casts, any data, or raw-payload error reflection.
- [X] T033 [US2] Create `frontend/src/components/SafetyDenialBanner.tsx` with fixed partial-exclusion category copy, role=alert, accessible title, native Dismiss and Correct this input buttons, and no aria-modal/showModal/focus trap; emit the selected notice key via a typed callback without copying input text; preserve "A known rejection with unavailable detail may carry an empty reason list; the UI explicitly states detail is unavailable." and never repeat dropped values or steal focus on arrival.
- [X] T034 [US2] Coordinate inline notices in `frontend/src/App.tsx` with dispatch callbacks in `frontend/src/components/IntakeChat.tsx` and `frontend/src/components/SourcePicker.tsx`: deduplicate by session/request ID, preserve distinct banners/accepted values and editing/valid Submit, and implement client-only correction_target: "Null or one existing notice key `(generation, session_id, request_id)` selected by Correct this input." and corrects_operation: "Immutable snapshot of correction_target on the next dispatched chat/upload operation; null for an unlinked operation." Show the selection and Cancel correction; selection replacement/cancel/dismiss clears only an undispatched target, Correct this input focuses the composer, and dispatch consumes the selection once while canceled file selection/local pre-dispatch validation retains it. Keep immutable links across fallback with no wire changes. Clear only the linked target for current-generation accepted updates with no field-validation failure and explicitly null safety_notice; preserve it on empty/error/legacy/mixed/rejected results, render new rejections separately, and retain cleared/dismissed keys against replay until generation reset clears all links/notices. Never infer correction from shared controls or affect already-running operations.
- [X] T035 [US2] Extend `backend/src/aimplify_intake/evaluation/golden_runner.py`, `backend/tests/golden/cases.jsonl`, and `backend/tests/unit/evaluation/test_golden_runner.py` with actual status/reason/category propagation expectations, preserving existing outcomes and >=50 cases covering six sections, five categories, chat/document/audio, human-only protection, and single-question pacing.
- [ ] T036 [US2] Run `backend/tests/unit/test_extraction.py`, classifier/property tests, new safety contracts, input-boundary matrix, `frontend/src/tests/safety-notices.test.tsx`, and the complete golden runner; prove no content leakage, equivalent metadata on both transports, explicit linked chat/upload corrections across fallback, concurrent-target isolation, failed/empty/legacy/mixed correction preservation, deduplication after clear/dismiss, stale-generation isolation, and no safety-triggered retries.

**Checkpoint**: US2 works on an in-progress idea without final submission. UI integration
reuses the transport/lifecycle changes from US1, not its modal presentation.

For T027/T034, field-validation failure means a validation error reported through the
existing operation result/error channel; do not introduce per-candidate diagnostics.
Invalid-only input cannot clear a target because it has no accepted field updates.

## Phase 5: User Story 3 - Operate Outcome Feedback Accessibly (Priority: P2)

**Goal**: Correct modal/nonmodal semantics, keyboard behavior, announcement, responsive
layout, and clean feedback lifecycle without storage loops or resource retention.

**Independent Test**: Keyboard/screen-reader success and denial journeys verify polite
confirmation versus alert banner semantics, modal-only containment, Escape behavior and
focus restoration, 320-pixel/200%-zoom layout, plus repeat-cycle resource bounds.

### Tests for User Story 3

- [X] T037 [P] [US3] Add `frontend/src/tests/outcome-dialog.test.tsx` for confirmation mount, role=dialog/aria-modal=true, title/description, separate aria-live=polite status, action focus, Escape/Close without reset, frozen-summary focus, normal Tab order, and unmount cleanup; extend `frontend/src/tests/safety-notices.test.tsx` for banner role=alert with no aria-modal/trap, dismiss focus restoration, scoped Escape, keyboard-operable Correct this input/Cancel correction, accessible selected-target text, and composer focus only after explicit correction selection, using scoped jsdom shims rather than claiming real-browser proof.
- [X] T038 [US3] Complete confirmation focus/cancel/unmount behavior in `frontend/src/components/OutcomeDialog.tsx` and summary integration in `frontend/src/App.tsx`; contain focus only while modal is open, close to the frozen summary without reset, clean listeners/timers/owned nodes, avoid positive tabindex, and focus the fresh composer only after explicit Start a new idea succeeds.
- [X] T039 [US3] Complete banner-specific keyboard/focus behavior in `frontend/src/components/SafetyDenialBanner.tsx` with initiating-control tracking in `frontend/src/App.tsx`, `frontend/src/components/IntakeChat.tsx`, and `frontend/src/components/SourcePicker.tsx`; announce without stealing focus on arrival, dismiss on Escape only when focus is inside the banner, restore a surviving initiating control after focused dismissal, make Correct this input and Cancel correction keyboard-reachable with accessible selected-target text and explicit-action composer focus, restore the selected banner's correction button after Cancel correction if it survives (otherwise the composer), and never trap/disable background editing.
- [X] T040 [P] [US3] Add bounded wrapping/scrolling, visible focus, and modal/banner responsive styling in `frontend/src/index.css` for 320 CSS pixels and 200% zoom, preserving unrelated workspace styling and reachable actions.
- [ ] T041 [US3] Add/run `frontend/src/tests/outcome-resources.test.tsx` for 100 feedback mount/dismiss cycles and 10 fresh-intake cycles with storage/serialization spies, owned DOM/container/listener/timer/socket counts, and rejected-promise observation; require zero new sessionStorage/localStorage writes and zero retained resource growth after teardown, fix coupled lifecycle leaks in the owning components, and verify any introduced portal container is removed without introducing portals solely for this test.
- [ ] T042 [US3] Run outcome component/resource suites and execute real-browser keyboard, screen-reader, 320-pixel and 200%-zoom checks from `specs/002-submission-safety-popups/quickstart.md`; verify modal versus banner semantics and exact Escape/focus behavior, record browser/assistive-technology evidence in the implementation session, and leave unavailable checks incomplete.

**Checkpoint**: US3 proves the distinct accessible journeys and SC-009 resource bounds;
jsdom cannot alone establish real focus containment, layout, or screen-reader behavior.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Close verification-gate gaps, enforce contract quality, and prove release outcomes.

- [ ] T043 [P] Extend `backend/tests/integration/test_pii_log_exclusion.py` and `backend/tests/contract/ingestion/test_ingress_no_disk.py` for new outcome/error paths; prove no personal/rejected content in logs/notices and no source/derived bytes on disk, preserving canonical counts, human-only protection, and one-question behavior.
- [ ] T044 [P] Add gate regression tests in `backend/tests/contract/test_verification_gates.py` using isolated fixture repositories/process commands for missing PostgreSQL, failed lint/test/sentinel, nonzero propagation, hook install conflicts, .disabled workflow detection, and discovery of every new suite; define expected fail-fast behavior before implementing `scripts/verify.ps1` and `.githooks/pre-push`, without pushing deliberately broken shared branches or running destructive migrations.
- [X] T045 Enforce strict outcome handling in `frontend/eslint.config.js` and `frontend/tsconfig.app.json` with existing tooling: ban explicit/implicit any in affected transport/modal/banner/state paths, require decoder-backed responses and exhaustive discriminated states, flag unreachable handlers and floating promises, and add rejection-path regression cases in `frontend/src/tests/submission-outcomes.test.tsx` and `frontend/src/tests/safety-notices.test.tsx`; handle parse/socket/dialog/setup/reset/retry failures with safe distinct feedback, no bare/double/non-null assertion bypasses or silent defaults.
- [ ] T046 Implement fail-fast `scripts/verify.ps1 -Required` as the single local/CI entry point: run full pytest and Vitest discovery including new suites, frontend lint/type/build, complete golden evaluation, PostgreSQL race tests and migration round-trips against disposable databases; require pwsh/uv/Node and TEST_POSTGRESQL_URL, set VERIFY_REQUIRED=1 in its child test processes, prohibit skips of required checks, propagate failures, and never install dependencies automatically or expose credentials.
- [X] T047 Add tracked `.githooks/pre-push` forwarding to `scripts/verify.ps1 -Required` and `scripts/install-hooks.ps1` that inspects core.hooksPath/active hooks before installation, stops for conflicts without overwriting user hooks, supports documented Windows/CI execution, forwards failure codes, and does not change hook configuration during ordinary test execution.
- [X] T048 Wire `.github/workflows/ci.yml` to the same required verification entry point with disposable PostgreSQL service, isolated migration/race databases and safe connection configuration; ensure PR triggers, frontend lint/type/build and all new suites/golden cases execute without exclusions/continue-on-error, reject executable .disabled workflows via `backend/tests/contract/test_verification_gates.py`, and preserve existing identity and golden gate jobs.
- [X] T049 Update `backend/README.md` and `specs/002-submission-safety-popups/quickstart.md` with actual selectors, hook prerequisites/conflict resolution, email policy, nested denial contract and new summary/banner flows; reconcile the requirement/scenario/task/selector and audit maps in `specs/002-submission-safety-popups/tasks.md` to actual test names, recording runtime evidence only in the implementation session and not marking coverage as passed before execution.
- [ ] T050 Run `scripts/verify.ps1 -Required` after feature and gate implementation, including complete golden evaluation >=50 cases at 100% pass/zero omissions and all backend/frontend/type/lint/build/PostgreSQL/migration suites; fix introduced/coupled failures, preserve unrelated findings, and fail required mode for any unavailable prerequisite rather than hiding omissions.
- [ ] T051 Validate pre-push and Actions failure propagation using `backend/tests/contract/test_verification_gates.py` and isolated sentinel fixtures, confirm no executable disabled workflows, and inspect required-check settings for the job names in `.github/workflows/ci.yml` with authorized repository access; report unconfigured/inaccessible branch protection as a release blocker, never infer it from YAML or change remote protections automatically.
- [ ] T052 Execute all live acceptance scenarios in `specs/002-submission-safety-popups/quickstart.md` against `frontend/src/App.tsx` and `backend/src/aimplify_intake/api/app.py`, including invalid-email blocking, banner correction, Escape without reset, unknown outcome, duplicates and fresh-start recovery; measure confirmation/banner visibility <=1,000 ms from available outcome, confirm SC-001 through SC-010 with actual evidence, and leave external/browser/merge-gate checks incomplete when unavailable.

## Dependencies & Execution Order

### Phase and story graph

```text
Setup T001-T002 -> Foundation T003-T005
  -> US1 submission/readiness -> lifecycle/modal/reset -> US1 validation
  -> US2 safety unit tests -> classifier/extraction/graph -> transport -> banner -> validation
       US1 API/client/lifecycle ---------------------------^
  -> US3 modal/banner keyboard + resource tests -> real-browser proof
US1 + US2 + US3 -> privacy + quality + shared pre-push/CI gate -> live acceptance
```

US1 is independently testable as the MVP. US2 backend work can start after foundation;
its API/client/App integration serializes with US1 shared-file changes. US3 integrates
both outcomes; it does not turn the banner into a modal. No requirement makes submission
a prerequisite for seeing a denial.

### Authoritative task prerequisites

Ranges are inclusive; every task in a prerequisite range must be complete.

| Task(s) | Prerequisites |
|---------|---------------|
| T001 | None |
| T002 | T001 |
| T003-T005 | T002; mutually file-disjoint |
| T006-T009 | T003-T005; file-disjoint test authoring |
| T010 | T006-T009 |
| T011 | T010 |
| T012 | T011 |
| T013 | T012 |
| T014 | T013 |
| T015 | T014 |
| T016 | T015 |
| T017 | T016; coordinate parent callback signatures |
| T018 | T017 |
| T019 | T018 |
| T020 | T019 |
| T021 | T014 |
| T022 | T020 |
| T023-T027 | T003-T005; file-disjoint test authoring |
| T028 | T023-T027 |
| T029 | T028, T011 (shared email validation behavior) |
| T030 | T029 |
| T031 | T030, T014 (shared API file) |
| T032 | T031, T015 (shared service file) |
| T033 | T032 |
| T034 | T033, T020 (shared App lifecycle) |
| T035 | T030 |
| T036 | T034-T035 |
| T037 | T034; shared safety test file must be free |
| T038 | T037 |
| T039 | T038 |
| T040 | T037; file-disjoint from T038-T039 |
| T041 | T039-T040; author resource assertions before fixing leaks |
| T042 | T041, T021-T022, T036 |
| T043-T044 | T042; file-disjoint |
| T045 | T043-T044 |
| T046 | T045 |
| T047 | T046 |
| T048 | T047 |
| T049 | T048 |
| T050 | T049 |
| T051 | T050 |
| T052 | T051 |

Within each story, tests precede implementations. Parent locking/readiness precedes routes;
extraction precedes graph/transport; component behavior precedes live acceptance.
The task table, not numerical adjacency alone, determines prerequisites.

## Parallel Examples

### User Story 1

After foundation, author T006 API contracts, T007 transaction tests, T008 frontend lifecycle
tests, and T009 email fixtures concurrently in distinct files. After T014, T021 backend
validation can run while T015-T020 implement frontend behavior using isolated test resources.

### User Story 2

T023-T027 test authoring is file-disjoint. After T030, T035 golden expectations can proceed
alongside T031-T034 transport/banner work. Do not edit API/client/App concurrently with
US1 changes to those files.

### User Story 3

After T037, T040 CSS can run alongside T038-T039 focus implementation. T041 waits for
both chains, and T042 waits for both functional story validations. T043 privacy and T044
gate tests can subsequently run in parallel.

## Requirement -> Scenario -> Task -> Verification Selector

Scenario references use story/acceptance-scenario numbers in [spec.md](spec.md).
File selectors below exist; specific contract and component test names are listed after the
matrix where they make the evidence easier to reproduce.

| Requirement | Acceptance scenario / invariant | Task IDs | Verification selector |
|-------------|---------------------------------|----------|-----------------------|
| FR-001 | US1.1, US1.2, US1.4 | T006-T018, T021-T022 | `backend/tests/contract/api/test_submission_outcomes.py`; `frontend/src/tests/submission-outcomes.test.tsx` |
| FR-002 | US1.1, US1.6 | T006-T007, T010, T013-T019 | `backend/tests/integration/persistence/test_submission_transactions.py`; `frontend/src/tests/submission-outcomes.test.tsx` |
| FR-003 | US1.3, US1.8 | T008, T019-T020 | `frontend/src/tests/submission-outcomes.test.tsx` |
| FR-004 | US1.3 | T007-T008, T020-T022 | `frontend/src/tests/submission-outcomes.test.tsx`; `backend/tests/integration/persistence/test_submission_transactions.py` |
| FR-005 | US1.5, US1.6 | T006-T008, T013-T018, T021-T022 | `backend/tests/integration/persistence/test_submission_transactions.py`; `frontend/src/tests/submission-outcomes.test.tsx` |
| FR-006 | US1.7 | T008, T020, T022 | `frontend/src/tests/submission-outcomes.test.tsx` |
| FR-007 | US2.1, US2.6 | T023-T034, T036 | `backend/tests/contract/api/test_safety_notices.py`; `frontend/src/tests/safety-notices.test.tsx` |
| FR-008 | US2.1, US2.3, US2.7 | T023-T029, T032-T033 | `backend/tests/unit/test_extraction.py`; `frontend/src/tests/safety-notices.test.tsx` |
| FR-009 | US2.1, privacy/no-disk invariants | T024-T026, T028-T031, T043 | `backend/tests/integration/test_no_facts_boundaries.py`; `backend/tests/integration/test_pii_log_exclusion.py` |
| FR-010 | US2.2 | T024, T026-T034 | `backend/tests/integration/test_no_facts_boundaries.py`; `frontend/src/tests/safety-notices.test.tsx` |
| FR-011 | US2.3, duplicate-delivery edge case | T025-T027, T032-T034 | `frontend/src/tests/safety-notices.test.tsx` |
| FR-012 | US2.4, US2.5, US2.8, US2.9 | T027, T033-T034, T036-T039 | `frontend/src/tests/safety-notices.test.tsx`; linked chat/upload, failure, fallback, concurrent and replay cases |
| FR-013 | US3.1-US3.6 | T037-T042 | `frontend/src/tests/outcome-dialog.test.tsx`; `frontend/src/tests/safety-notices.test.tsx`; live quickstart |
| FR-014 | US1.2, US1.5, US2.6 | T004-T006, T015, T018, T025-T027 | `backend/tests/contract/api/test_submission_outcomes.py`; `frontend/src/tests/safety-notices.test.tsx` |
| FR-015 | Canonical/human-only/one-question/RAM/PII invariants | T007, T012-T014, T023, T026, T030, T035, T043 | `backend/tests/contract/test_canonical_schema.py`; `backend/tests/contract/api/test_human_only_fields.py`; `backend/tests/contract/ingestion/test_ingress_no_disk.py`; golden runner |
| FR-016 | All three story independent tests | T021-T022, T035-T036, T042-T052 | `backend/scripts/run_golden_evaluation.py`; `scripts/verify.ps1 -Required` |
| FR-017 | US2.1, US2.2 | T005, T024-T025, T029-T032, T035 | `backend/tests/unit/test_extraction.py`; `backend/tests/contract/api/test_safety_notices.py` |
| FR-018 | US1.9; FR-018 boundary/IDNA2008 matrix | T009, T011-T012, T021 | `backend/tests/unit/test_email_validation.py`; `backend/tests/contract/api/test_submission_outcomes.py`; every A-label/profile fixtures |
| FR-019 | Safe failure/exhaustive state invariant | T005, T015, T018, T027, T032, T045, T050 | frontend lint/type/build; `frontend/src/tests/submission-outcomes.test.tsx`; `frontend/src/tests/safety-notices.test.tsx` |
| FR-020 | Reset/resource invariant | T020, T038-T041 | `frontend/src/tests/outcome-resources.test.tsx` |
| FR-021 | Required-gate/no-skip invariant | T003, T044, T046-T051 | `backend/tests/contract/test_verification_gates.py`; `scripts/verify.ps1 -Required`; GitHub required-check settings |
| FR-022 | This traceability matrix | T049, T052 | matrix/selector discovery review and recorded implementation evidence |
| SC-001 | US1.1-US1.6 | T006, T008, T021-T022 | submission contract and lifecycle suites |
| SC-002 | US1.3 | T007-T008, T020-T022 | transaction and lifecycle suites |
| SC-003 | US2.1 category/input matrix | T023-T026, T036 | safety unit/contract/boundary suites |
| SC-004 | US2.2, US2.4-US2.5 | T024, T026-T027, T034, T036 | extraction and safety-notice suites |
| SC-005 | US1.6; duplicate/late-result edges | T007-T008, T021-T022, T027, T036 | transaction/lifecycle/safety-notice suites |
| SC-006 | US3.1-US3.6 | T037-T042 | dialog/banner suites and live browser/assistive-technology checks |
| SC-007 | <=1,000 ms available-outcome display | T052 | live response/event-to-visible-modal/banner timing |
| SC-008 | FR-018 fixture matrix | T009, T011-T012, T021 | `backend/tests/unit/test_email_validation.py` |
| SC-009 | 100 feedback / 10 fresh cycles | T041 | `frontend/src/tests/outcome-resources.test.tsx` |
| SC-010 | Required-gate/sentinel matrix | T044, T046-T051 | `backend/tests/contract/test_verification_gates.py`; required local/Actions runs |

### Concrete Test Names

- Submission HTTP: `test_incomplete_submission_returns_only_safe_field_keys`, `test_successful_submission_retry_returns_the_same_committed_receipt`, `test_submitted_session_rejects_human_and_message_mutations`, `test_stored_invalid_email_blocks_submission_without_deleting_value`, `test_false_declaration_blocks_submission`, `test_submitted_session_rejects_http_source_and_open_websocket_source_commit`, `test_submission_persistence_unavailable_returns_safe_503`, and `test_submission_requires_owner_and_allowed_origin` in `backend/tests/contract/api/test_submission_outcomes.py`.
- Submission persistence: `test_readiness_reports_missing_fields_without_values`, `test_finalization_commits_one_immutable_receipt`, `test_concurrent_finalization_returns_one_receipt`, `test_human_write_racing_finalization_is_serialized`, and `test_submission_timestamp_migration_roundtrips_without_losing_drafts` in `backend/tests/integration/persistence/test_submission_transactions.py`.
- Frontend lifecycle: explicit Submit, unsaved declaration, active-operation, Escape/frozen-summary, fresh-intake, unknown-result, and reused-session setup cases in `frontend/src/tests/submission-outcomes.test.tsx`.
- Safety transport and correction: `test_http_and_websocket_return_the_same_category_only_notice`, `test_ordinary_validation_failure_does_not_create_a_safety_notice`, and the focused notice, fallback, malformed-payload, keyboard, and linked-correction cases in `frontend/src/tests/safety-notices.test.tsx`.
- Gate verification: `test_required_verifier_covers_tools_database_and_failure_propagation`, `test_required_postgresql_fixture_fails_when_database_url_is_missing`, `test_hook_installer_preserves_an_existing_pre_push_hook`, `test_hook_installer_sets_local_path_when_no_conflict_exists`, `test_required_verifier_rejects_disabled_workflow_files`, `test_ci_uses_the_required_verification_entry_point`, and `test_new_regression_suites_are_discoverable_and_disabled_workflows_are_absent` in `backend/tests/contract/test_verification_gates.py`.

## Audit Finding Remediation Map

| Finding | Planned remediation | Regression / proof tasks |
|---------|---------------------|--------------------------|
| I1: denial contract shape | Nested status denied/reason NoFacts separate from intake status: T005, T029-T032 | T024-T027, T035-T036 |
| I2: modal/banner/ARIA ambiguity (F-03) | Employee-selected confirmation modal and nonmodal alert banner: T019, T033-T034, T038-T040 | T027, T037, T042 |
| I3: success Escape conflict | Escape/Close leaves frozen summary, no reset: T019-T020, T038 | T008, T022, T037, T042 |
| C1: strict email/TLD coverage (F-04) | One backend authority and preserved invalid stored values: T011-T012 | T009, T006, T021 |
| C2: gates/pre-push/PostgreSQL (F-01/F-02) | Required database mode, shared verifier, hook installer, CI and merge-setting verification: T003, T046-T048 | T044, T050-T051 |
| C3: type/error enforcement (F-06) | Guarded unknown decoding, no assertion bypass, exhaustive/handled outcomes: T005, T015, T018, T032, T045 | T027, T045, T050 |
| C4: extraction metadata unit tests | Detailed extraction propagation: T029 | T024, T036 |
| C5: reset/storage/resource proof (F-05) | Scoped reset, owned-resource cleanup, no new storage/portal: T020, T038-T039 | T041-T042 |
| A1: correction correlation | Employee-selected Correct this input, client-only immutable dispatch link, cancel and isolated clearing: T033-T034, T039 | T027, T036-T037, T042; US2.5/US2.8/US2.9 and live quickstart |
| A2: IDNA profile ambiguity | Strict IDNA2008 for every A-label, no UTS #46/transitional mappings, direct runtime dependency/lockfile: T011 | T009, T021; profile-sensitive fixtures through extraction and stored readiness |

## Implementation Strategy

### MVP First

Complete setup/foundation and US1, then validate it independently. Email tightening and
Escape-without-reset are part of this approved MVP, not optional later behavior.
US1 alone is not full-feature acceptance and does not close the audit findings.

### Incremental Delivery

1. US1 establishes safe finalization, summary dismissal, and complete acknowledgment reset.
2. US2 adds deterministic nested metadata and inline nonmodal feedback without blocking editing.
3. US3 proves accessible semantics, focus, layout, and scoped resource cleanup.
4. Cross-cutting gates enforce the same checks locally and in CI, with actual evidence.

### Completion Rules

- Total: 52 tasks; US1: 17, US2: 14, US3: 6; setup/foundation/polish: 15.
- Checked tasks reflect implementation or local verification completed in this session. Unchecked tasks retain explicit external evidence requirements; format/mapping checks do not imply application correctness.
- Current implementation status: 34 of 52 tasks checked; 18 remain open for missing coverage or unavailable required environment evidence.
- T001 remains open because `.specify/feature.json` is absent; the prerequisite script succeeded only after setting `SPECIFY_FEATURE_DIRECTORY` to the active feature directory. The pre-change baseline was 109 backend tests and 5 frontend tests after restoring missing local tool dependencies.
- Missing PostgreSQL, browser, assistive-technology, or required-check access is an explicit
  verification blocker. Required gates cannot silently skip; no 9.5+ score is inferred.
- Keep operational results in the implementation session; avoid unrequested evidence files.
- Update implementation test selectors and traceability during T049; rerun `/speckit-analyze`
  after artifact refinement and before `/speckit-implement`.
