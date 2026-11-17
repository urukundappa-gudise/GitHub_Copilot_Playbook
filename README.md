# ADLC Aimplify Chatbot 

## Local InfoVision SSO

1. Fill in the Entra tenant ID, application client ID, and client secret in the
   existing local `.env`. `.env` is ignored by Git and Copilot; never commit it
   or paste the client secret into chat. `.env.example` is the reference template.
2. Register these exact URLs on the Entra application as Web redirect URLs:
   `http://localhost:5174/api/v1/auth/callback` and
   `http://localhost:5174/login` (post-logout redirect).
3. Run `./run.ps1` from PowerShell, then open `http://localhost:5174/login`.
   The sign-in action should redirect to `login.microsoftonline.com`.

The local configuration uses `AUTH_REQUIRED=true` and `AUTH_MOCK_MODE=false`.
It reserves ports 5174 and 8001 to avoid conflicts with services on the default
ports. If the Entra values are missing or invalid, sign-in fails closed; do not
enable mock mode to test real credentials. Use the same `localhost` hostname
and ports as the registered URLs so the secure session cookie is retained.

## Stage 6: Maintain

The Drift Detector runs every 15 minutes and on `repository_dispatch` events
of type `telemetry-anomaly`. Its source is
[.github/workflows/drift-detector.md](.github/workflows/drift-detector.md);
[.github/workflows/drift-detector.lock.yml](.github/workflows/drift-detector.lock.yml)
is generated with `gh aw` v1.0.1. Recompile with:

```powershell
gh aw compile drift-detector --no-check-update
```

The deterministic inspector reads `.copilot/usage.jsonl` without modifying it.
It compares the latest 10 valid samples with up to 500 preceding samples,
requiring at least 30 baseline samples for each model/feature/request-type group.
Latency, cost, explicit error rate, and observed request failure rate trigger
when their window mean exceeds the historical mean plus three population standard
deviations. This is a sample-window detector, not a time-window production SLO.
Groups without sufficient history do not establish drift or prove health.
An external telemetry collector must publish fresh, sanitized JSONL to the
default branch; repository dispatch alone does not supply or persist telemetry.

### Deployment Prerequisites

- Configure the `COPILOT_GITHUB_TOKEN` Actions secret for the Copilot engine as
	described in the gh-aw authentication documentation. Do not store tokens in git.
- Enable GitHub Actions to create pull requests. The compiler gives only isolated
	safe-output jobs repository write permissions; the agent uses read-only scopes.
	Strict mode rejects the playbook-style top-level issue/PR write declarations,
	so read-only frontmatter is used with isolated safe-output writes instead.
- Before enabling production automation, configure default-branch protection or
	rulesets to require PRs, passing checks, and human SRE code-owner approval,
	dismiss stale approvals, and prevent automation/admin bypass. Configure the
	actual SRE team as code owner of all remediation paths. These repository-side
	controls cannot be enforced by a local workflow file and are not provisioned
	by this change. Without them, mandatory SRE merge authorization is not enforced.
- Outputs are limited to one incident and one draft remediation PR per run.
	No merge, approve, deploy, or auto-merge tool is enabled. A human SRE must
	authorize and perform the merge. Raw telemetry must not be copied into outputs.

### Local Incident Simulation

```powershell
uv sync --project backend --all-extras
uv run --project backend python backend/scripts/simulate_telemetry_drift.py
uv run --project backend pytest backend/tests/regression/test_telemetry_drift.py -v
```

The simulation synthesizes the regression test, injects a three-sigma latency
breach in memory, and examines recent backend commit diffs for candidate causes.
It proves the regression fails against an isolated baseline-contamination
mutation, then passes with the corrected detector and healthy telemetry. It does
not alter production code or logs, publish GitHub objects, or claim a synthetic
incident establishes a production root cause. The retained regression test is
the flywheel artifact for future changes. Existing edited regression tests are
never overwritten.

For inspection without simulation or test generation:

```powershell
uv run --project backend python backend/scripts/simulate_telemetry_drift.py --inspect .copilot/usage.jsonl
```

The referenced GitHub-Native AI SDLC Playbook pages were not available in this
workspace; implementation follows the Stage 6 requirements supplied in the task.
