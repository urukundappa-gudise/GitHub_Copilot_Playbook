# Implementation Plan: Submission Confirmation and Safety Denial Popups

**Branch**: `feat/submission-popup-and-security-feedback` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-submission-safety-popups/spec.md`

## Summary

Add an explicit, server-validated final submission transition on the existing idea record,
an acknowledgment-driven fresh-intake reset, and category-only NoFacts denial feedback
across HTTP and WebSocket input paths. Preserve accepted values, declaration ownership,
existing safety decisions, and submitted records. Use the existing React/FastAPI/SQLAlchemy
stack, not a new workflow service or popup package. The approved refinement uses a
confirmation modal and a nonmodal denial banner with separate responsibilities.

Planning ends with these design artifacts; application changes and test execution belong
to implementation. The setup script reports `002-submission-safety-popups` as its BRANCH
value because of feature-directory resolution; `git branch --show-current` confirms the
actual branch recorded above. Do not create or switch branches.

## Technical Context

**Language/Version**: Python >=3.11; TypeScript ~5.7; React 19.

**Primary Dependencies**: FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, LangGraph;
React DOM, Vite 5. Keep existing dependencies except declare idna>=3,<4 as a direct backend
runtime dependency for strict IDNA2008 validation; update the backend uv lockfile during
implementation rather than relying on a transitive development dependency.

**Storage**: Existing PostgreSQL production persistence, SQLite local/test support.
Add nullable `submitted_at` to `idea_submissions` through Alembic; reuse its existing
`status` and primary key. Safety notices and popup state remain transient.

**Testing**: pytest, existing golden runner, Vitest/jsdom/Testing Library, TypeScript build
and ESLint. Real-browser keyboard, assistive-technology, viewport, zoom, and timing checks
supplement jsdom rather than treating it as proof of layout accessibility.

**Target Platform**: Existing browser application and Python web service; Windows-compatible
development commands and existing CI.

**Project Type**: Full-stack web application with HTTP and WebSocket interfaces.

**Performance Goals**: Show either outcome within one second after the associated outcome
becomes available; measure from response/event reception to visible modal/banner, excluding
extraction/submission latency. No new throughput targets.

**Constraints**: Exactly 27 fields, 6 sections, 18 mandatory fields; human-only declarations;
no rejected values in notices or persistence; RAM-only ingestion; no personal information
in logs; one clarification per turn; golden suite >=50 cases, 100% passing, no omissions.

**Scale/Scope**: One intake workspace, a confirmation modal and denial banner, one final-submit endpoint,
additive turn/state metadata, and one migration. Existing six source formats and both
interaction transports remain supported. No schema-field, authentication, retention,
new-format, review-workflow, or general transport redesign. Audit remediation additionally
covers strict email syntax, typed outcome decoding, resource regression checks, installable
pre-push verification, and CI integration; these are intentional scope refinements.

## Constitution Check

*GATE: Passed before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Pre-design assessment | Post-design enforcement |
|-----------|-----------------------|-------------------------|
| I. Deterministic NoFacts | Preserve every existing pass/drop decision. | Shared classifier uses existing patterns; proof-carrying safe candidates remain required. Only allowlisted categories leave the gate, never dropped values. |
| II. Ephemeral ingestion | No source-storage change needed. | Existing BytesIO paths remain; notices contain no bytes, filenames, transcripts, or excerpts. Existing no-disk tests remain mandatory. |
| III. Canonical and human-only boundaries | No field-count or origin-policy change. | Readiness reuses canonical validation with the approved email syntax tightening, validates 18 mandatory fields and all three declarations with human origin; no automated declaration fill. |
| IV. One question per turn | Existing graph pacing is retained. | Safety notice is explanatory text, not another clarification question; mixed results retain the single existing question. |
| V. PII and identity | No identity or logging changes required. | New route reuses cookie identity, origin, and ownership checks. Fixed reason/error messages and field keys only; no rejected content is logged or retained. |
| VI. Golden gate | Existing gate remains the release requirement. | Extend applicable safety/conversation expectations; run every manifest case and block merge on any failure/omission, plus feature-specific integration/UI checks. |

Category-only feedback does not violate silent dropping: candidate values are still
discarded without being returned as facts, and notices expose no value. No constitutional
amendment or exception is needed. This is a design pass, not a claim that implementation
tests have already passed.

## Project Structure

### Documentation (this feature)

```text
specs/002-submission-safety-popups/
  spec.md
  plan.md
  research.md
  data-model.md
  quickstart.md
  contracts/
    intake-outcomes.md
  checklists/
    requirements.md
```

`tasks.md` is maintained by `/speckit-tasks` with audit-remediation traceability.

### Source Code (repository root)

```text
backend/
  alembic/versions/
  src/aimplify_intake/
    api/app.py
    api/http.py
    graph/intake_graph.py
    persistence/models.py
    persistence/repositories.py
    safety/no_facts.py
    schema/validation.py
    services/extraction.py
  tests/
    unit/
    contract/api/
    integration/
    golden/
frontend/
  src/
    App.tsx
    index.css
    services/intake.ts
    components/
      IntakeChat.tsx
      HumanDeclarations.tsx
      SourcePicker.tsx
      OutcomeDialog.tsx
      SafetyDenialBanner.tsx
    tests/
.githooks/
  pre-push
scripts/
  verify.ps1
  install-hooks.ps1
.github/workflows/ci.yml
```

**Structure Decision**: Extend existing modules and test locations. `OutcomeDialog.tsx`
owns only modal confirmation; `SafetyDenialBanner.tsx` owns nonmodal alerts. App coordinates
state and the service validates transport data. Put finalization/readiness transaction
helpers in the existing repository module rather than adding a second persistence layer.

## Phase 0: Research Outcome

[research.md](research.md) resolves submission identity, transaction boundaries, stored
declaration validation, rejection classification, transport parity, reset ownership,
accessible dialogs, and verification tooling. No unresolved technical decisions remain.
Repository research is the primary evidence; a bounded research pass independently
verified CI, golden, migration, and startup commands.

## Phase 1: Design and Delivery Sequence

1. **Submission integrity**: Add `submitted_at`; implement shared stored-value readiness
   validation and an idempotent `in_progress -> submitted` transition. Serialize all writes
   and finalization on the same parent record; remove internal commit boundaries in those
   shared write paths so checks and changes commit together. Reject writes after finalization,
   including pending extraction results and open WebSocket sources.
2. **Safe explanations**: Add category classification using the existing NoFacts patterns.
   Keep legacy pass/drop and safe-candidate interfaces compatible; introduce a detailed
   extraction result used by the graph and API that carries safe updates and an optional
   category-only notice with `status: "denied"` and `reason: "NoFacts"`. Keep this rejection
   status separate from the intake lifecycle. Do not retain candidate text in new objects
   or diagnostic fields. Add extraction-layer metadata propagation unit tests.
3. **Contracts and transport**: Implement [intake-outcomes.md](contracts/intake-outcomes.md)
   across HTTP turn responses, WebSocket status events, field-state readiness, and final
   submission. Preserve typed domain errors instead of collapsing them into generic
   transport failures. Reuse an operation identifier across a WebSocket-to-HTTP retry
   so feedback deduplication follows the logical operation. Decode responses from unknown
   with runtime guards instead of bare assertions; enforce typed, exhaustive outcome
   state and handled asynchronous failures in lint/type checks.
   Keep correction correlation client-only: Correct this input selects one notice key,
   and the next dispatched chat/upload snapshots it across fallback. Only an authoritative
   result with accepted updates, no field-validation failure, and explicitly null
   safety_notice clears that target; errors, empty/legacy/mixed results preserve it.
   Preserve unrelated banners and cleared/dismissed deduplication keys until generation reset.
4. **Workspace lifecycle**: Add a final Submit action that waits for active messages,
   uploads, and declaration saves; block it for unsaved declaration edits. Freeze editing
   during submit, unknown outcome, and confirmed success. On uncertainty, read authoritative
   state before unlocking; retry finalization against the same session if still in progress.
5. **Feedback and reset**: Use a native confirmation dialog with role=dialog, aria-modal=true,
   accessible labels, and separate polite status announcement. Use an inline role=alert
   denial banner with no aria-modal, focus trap, or focus stealing; keep editing available.
   Escape/Close dismisses success into a frozen summary without resetting; only Start a
   new idea in the modal or summary acknowledges reset. Background clicks do not dismiss.
   Denial Escape is scoped to focus inside its banner. Success acknowledgment
   alone initiates fresh-session preparation, closes the old socket, invalidates late
   callbacks, and remounts all intake-local components. Retain the newly allocated session
   identifier if later setup fails so retry resumes setup instead of allocating repeatedly.
   Add no browser-storage writes; test 100 feedback and 10 fresh-intake cycles for zero
   retained owned nodes/listeners/timers/connections and any portal-container cleanup.
6. **Validation and documentation**: Extend existing safety, contract, persistence,
   frontend, and golden checks; add final-submit and lifecycle scenarios. Follow
   [quickstart.md](quickstart.md), including real PostgreSQL concurrency/migration checks,
   real-browser accessibility, and the one-second outcome target. Update directly related
   API/run documentation during implementation. Tighten the shared backend email validator
   to FR-018 and test approved ASCII/punycode and rejected domain/TLD cases in extraction
   and stored readiness, without deleting existing invalid values. Validate every xn--
   label with strict IDNA2008 and case-insensitive ASCII round-trip; no UTS #46/transitional
   mappings or Python IDNA2003 codec. Declare idna>=3,<4 in backend/pyproject.toml and
   regenerate backend/uv.lock using uv without unrelated upgrades.
7. **Verification gates**: Implement one fail-fast PowerShell verification entry point used
   by an installable tracked pre-push hook and active CI. Wire frontend lint/type/build,
   all feature suites, golden evaluation, PostgreSQL service-backed concurrency, and
   migration round-trips. Required mode must fail on missing TEST_POSTGRESQL_URL or skipped
   required checks. Keep default optional local tests distinct from required verification.
   Verify GitHub required checks via repository settings with authorized access; do not
   alter branch protections automatically or infer enforcement from workflow files.

See [data-model.md](data-model.md) for entities and state transitions. No new queue,
workflow framework, persistent rejection history, or independent submission table is required.

## Post-Design Gate

All six constitutional principles remain satisfied by the design. Contract coverage includes
FR-001 through FR-022 and validation scenarios cover SC-001 through SC-010. Implementation
must prove the database race behavior, privacy boundaries, complete reset, and real-browser
accessibility; a planning artifact alone is not release evidence.
