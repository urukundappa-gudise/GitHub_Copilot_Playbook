# Validation Guide: Submission and Safety Popups

The submission and safety-notice endpoints are implemented. The checks below are still
required evidence for full feature acceptance; a green local subset does not substitute for
PostgreSQL, browser, assistive-technology, or merge-gate verification.
See [contracts](contracts/intake-outcomes.md) and [state model](data-model.md).

## Prerequisites

- Python >=3.11, uv, Node.js/npm, existing backend and frontend dependencies.
- A disposable PostgreSQL database for migration and cross-connection concurrency checks;
  SQLite remains the default isolated test path but cannot prove PostgreSQL locking.
- Persistence tests use a per-test SQLite file by default. Optional PostgreSQL tests read
  `TEST_POSTGRESQL_URL` and require a database name containing a standalone `test`, `tests`,
  or `disposable` marker; each test creates and drops its own isolated schema. Without that
  URL, PostgreSQL cases skip in developer mode. Required verification sets `VERIFY_REQUIRED=1`
  and fails if the URL is missing or does not identify a test database. Use only a database
  created for these tests; never point the variable at shared, staging, or production data.
- Existing application environment configured locally. Do not print or commit credentials.
- For interactive audio, the existing approved no-retention transcription provider must
  be configured; automated tests can use existing injected provider fixtures.

Run commands from the repository root in PowerShell unless a step changes location.
Restore dependencies only if absent or required by changed manifests:

```powershell
uv sync --locked --project backend --extra dev
npm ci --prefix frontend
```

## 1. Database preparation

Point DATABASE_URL at a disposable PostgreSQL database using the existing local configuration.
Never downgrade a shared or production database for validation.

```powershell
Push-Location backend
uv run alembic upgrade head
uv run alembic current
Pop-Location
```

After implementation, verify the next revision adds nullable `submitted_at`, keeps existing
drafts in progress, and preserves canonical counts and constraints. On a disposable copy
only, downgrade one revision and re-upgrade; verify draft/field rows survive. Also exercise
fresh SQLite metadata creation and the new repository behavior in tests.

## 2. Targeted automated verification

Extend the existing tests rather than introducing a new runner. The following directories
and files already exist; add submission/outcome cases alongside them:

```powershell
uv run --locked --project backend pytest -q backend/tests/contract/api/test_submission_outcomes.py backend/tests/contract/api/test_safety_notices.py backend/tests/integration/persistence/test_submission_transactions.py backend/tests/unit/test_email_validation.py backend/tests/unit/test_extraction.py backend/tests/unit/safety backend/tests/integration/graph backend/tests/integration/test_no_facts_boundaries.py
npm run test --prefix frontend -- src/tests/submission-outcomes.test.tsx src/tests/safety-notices.test.tsx src/tests/outcome-dialog.test.tsx src/tests/intake-flow.test.tsx src/tests/human_declarations.test.tsx
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

The tests must explicitly prove:

1. Incomplete/invalid declarations (including stored false acceptance) block finalization.
2. Success commits once; repeated POST, concurrent POST, and lost-response retry return
   the same session and submitted timestamp, with no second submitted record.
3. Finalization racing an AI update or human write in separate database connections
   produces a serial outcome: the write precedes validated submission or fails as closed.
   Parameterize the common transaction tests for SQLite and PostgreSQL; use the existing
   database fixture conventions and an explicit disposable PostgreSQL connection.
4. All post-submit writes fail, including an already-open WebSocket and pending source.
5. Unknown submission response preserves and freezes the draft; recovery reuses its ID.
6. Acknowledgment clears all child-local and parent state; late callbacks cannot refill it.
   Fresh-start failure retries preparation, never finalization.
7. Category coverage crosses chat, PDF, DOCX, PPTX, WAV, MP3, WebM and existing HTTP/WS
   processing paths. Pure rejection, mixed acceptance, retained previous value, multiple
   reasons, empty known-reason fallback, and correction are exercised.
8. Rejected claims remain absent from accepted values, persistence, notices, and logs;
   no source/derived bytes are written to disk.
9. Duplicate delivery and WebSocket-to-HTTP fallback share a logical operation ID and
   produce one denial; a later rejected operation still receives feedback.
10. Typed protocol/domain errors remain distinguishable; ordinary source errors do not
    become NoFacts denials, and safety notices do not trigger transport retry.

Email validation is server-owned and shared by extraction and stored readiness. It enforces
ASCII dot-atom syntax and strict IDNA2008 for every A-label, without UTS #46, transitional
mappings, DNS lookups, or a duplicate frontend regex. Invalid stored addresses remain
unchanged and block finalization.

## 3. Required constitutional evaluation

```powershell
uv run --project backend pytest -q backend/tests/unit/evaluation/test_golden_runner.py backend/tests/contract/test_schema_golden.py
uv run --project backend python backend/scripts/run_golden_evaluation.py
```

Expected: at least 50 cases, all six sections and all five NoFacts categories, chat/document/audio
coverage, human-only protection, and single-question pacing; 100% pass and zero omitted
cases. Extend applicable golden expectations for safe reason metadata, preserving existing
claims and their accepted/rejected outcomes. Do not simply tag cases without behavioral assertions.

Use the full existing backend and frontend suites as the final release check after the
targeted feature tests and required golden gate pass:

```powershell
uv run --project backend pytest -q
npm run test --prefix frontend
```

## 4. Local browser journeys

Start the backend and frontend in separate terminals using existing Vite proxy configuration:

```powershell
# Terminal 1
Push-Location backend
uv run uvicorn aimplify_intake.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2
npm run dev --prefix frontend
```

Check backend readiness at `http://127.0.0.1:8000/health/ready` and open the frontend URL
printed by Vite. Existing allowed-origin/cookie configuration must permit that frontend;
do not disable authentication or origin checks to make the journey pass.

### Confirmation and reset

Complete the canonical mandatory fields using valid qualitative content, personally enter
and save declarations, and select Submit. Completing the last field alone must not submit.
Verify one success popup, retained submitted record, frozen old controls, and no reset until
`Start a new idea`. Acknowledge and verify empty chat, composer, fields, declarations, notes,
source control, clarification/error/notice state, initial progress, and a distinct session.

Repeat with incomplete declarations, duplicate clicks, interrupted submission response,
and a failed fresh-start request. The latter must not offer to resubmit the old idea.
Press Escape/Close on success: only the modal closes, the submitted summary stays frozen,
and its Start a new idea action is focusable and is the only reset path.

### Safety denial

Use synthetic non-personal examples containing a percentage, cost, date, digit quantity,
and word-form quantity in fields the extractor recognizes. Verify actual safe categories
without copying rejected text into the nonmodal banner. Verify structured safety_notice
contains status denied and reason NoFacts while intake status remains in_progress.
Mix safe and unsafe candidates and verify
safe fields remain; dismiss and correct. Repeat through each supported source format with
test fixtures and through both existing transports. An unreadable source must instead
produce the existing source-processing error.

Create two concurrent rejected operations. Select Correct this input on the first banner;
verify a visible target, Cancel correction, and focus on the chat composer without copied
rejected content. Cancel/reselect or select the second banner to verify replacement.
Dispatch a safe correction through chat and repeat with an upload: accepted updates,
no field-validation failure, and explicitly null safety_notice clear only the linked banner.
Unlinked or already-running operations cannot clear either target. Repeat with failed,
empty, legacy-absent, validation-failed, and mixed/rejected corrections: the target remains;
a new rejection has its own banner. Canceling a file picker preserves the undispatched
selection; dismissing its target cancels it. Fallback retains the correction link,
duplicate results never resurrect cleared/dismissed banners, and a fresh generation
discards old links/results.

### Accessibility and measurable outcomes

- Use only Tab, Shift+Tab, Enter, and Escape. Confirmation has role=dialog and
  aria-modal=true; focus is contained while open. Its status announcement is polite.
  Escape/Close dismisses it without reset and focuses the frozen summary action;
  background click does not dismiss. Denial has role=alert, no aria-modal or trap,
  does not steal focus, and allows editing. Escape while focused inside its banner
  dismisses and restores the initiating control; Escape elsewhere is not intercepted.
- Check announced title, outcome, and reasons with an available screen reader; record
  the tested browser/assistive-technology combination.
- At viewport width 320 CSS pixels and separately at 200% browser zoom, confirm all text
  and actions remain reachable and there is no horizontal scrolling.
- Measure response/terminal-event receipt to visible popup using browser timing or a
  browser assertion. Require <=1,000 ms for both confirmation and denial under normal
  supported conditions; do not measure extraction time or substitute total request duration.

## 5. Audit-remediation regression and gate checks

The repository includes one required verification entry point and a conflict-aware hook
installer:

```powershell
pwsh -NoProfile -File scripts\install-hooks.ps1
pwsh -NoProfile -File scripts\verify.ps1 -Required
```

Set TEST_POSTGRESQL_URL securely to a disposable database before required verification.
The installer inspects `core.hooksPath` and any active `pre-push` hook before changing local
configuration. It stops on conflicts and never overwrites an existing hook. The tracked
`.githooks/pre-push` launcher invokes the same verifier and installs no dependencies.

Required verification must run backend suites (including extraction propagation), full
Vitest discovery, frontend lint/type/build, complete golden evaluation, and PostgreSQL
race/migration checks. The verifier sets VERIFY_REQUIRED=1 for its child test processes;
database fixtures must fail on missing TEST_POSTGRESQL_URL in that mode, not skip.
CI provisions a disposable PostgreSQL service and invokes the same entry point. Missing
prerequisites or failing child commands must return nonzero through both launchers; gate
regressions use isolated fixture repositories, never a deliberately broken shared branch.

Verify no executable .disabled workflows exist and all required jobs run on PRs. Inspect
GitHub required-check settings using authorized access; if unavailable or not configured,
record that as a release blocker, not proof of enforcement. Do not silently change settings.

Run the email fixture matrix through extraction and stored-readiness tests: ASCII and valid
punycode, malformed xn-- labels, numeric/one-letter TLDs, raw Unicode, single-label domains,
IP literals, dot/local/domain/label length boundaries. Use strict IDNA2008 with no UTS #46
or transitional mappings on every xn-- label, including non-final labels. Include
user@xn--fa-hia.de as valid and user@xn--e28h.de as invalid; test malformed labels,
case-insensitive ASCII round-trip, and invalid non-final A-labels. Verify the direct
runtime dependency and backend lockfile are updated without using Python's IDNA2003 codec.
Invalid stored values remain intact and block submission. See FR-018 for the single policy.

Component/resource checks must mount/dismiss feedback 100 times and prepare 10 fresh
intakes. Spy on browser-storage writes and serialization entry points; require zero new
writes. After teardown, owned node/container, listener, timer, and connection counts return
to baseline. Validate no positive tab indices, malformed denial assertions, unhandled
rejections, unreachable handlers, or explicit/implicit any in the affected outcome path.

Keep a requirement -> acceptance scenario -> task -> test-selector mapping in tasks.md.
Record actual run evidence in the implementation session; pending coverage does not close
an audit finding or substantiate a 9.5+ quality score.

These are SC-001 through SC-010 acceptance checks, not inferred passes from jsdom.
