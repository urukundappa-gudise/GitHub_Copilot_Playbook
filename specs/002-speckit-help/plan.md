# Feature Plan: Spec-Kit Interactive Command Center & Help System (`/speckit-help`)

## 1. Executive Summary & Problem Statement
While Spec-Kit provides powerful discrete slash commands (`/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`), new developers and team members lack an integrated, in-editor and CLI discovery mechanism that guides them through the mandatory sequential stages. Specifically, the critical verification loops (`/speckit-analyze` Loop 1 and Loop 2) and context reset rules (mandatory fresh chat session before implementation) are frequently omitted when developers guess commands.

This feature introduces `/speckit-help` natively into Spec-Kit as both a GitHub Copilot Chat skill (`.github/skills/speckit-help/SKILL.md`) and a standalone terminal utility (`.specify/scripts/powershell/speckit-help.ps1`).

---

## 2. Technical Architecture & Artifact Boundaries

### 2.1 Repository Extension Points
1. **Copilot Skill Definition:**
   - Path: `.github/skills/speckit-help/SKILL.md`
   - Invocation: `/speckit-help [stage]` (supports optional filtering: `design`, `build`, `test`, `governance`)
   - Output: Formatted, point-by-point enterprise guide starting from Step 1 to Step 11, with layman explanations, input requirements, examples, and mandatory transition callouts.

2. **Terminal CLI Utility:**
   - Path: `.specify/scripts/powershell/speckit-help.ps1`
   - Invocation: `.\.specify\scripts\powershell\speckit-help.ps1 [-Stage <stage>]`
   - Output: Rich colored console formatting matching the Copilot Chat output.

3. **Integration Manifest Registration:**
   - Path: `.specify/integrations/copilot.manifest.json`
   - Entry: Registering `.github/skills/speckit-help/SKILL.md` with SHA-256 hash.

---

## 3. Ordered Lifecycle Workflow (11 Steps)

- **Step 1: `/speckit-init`** — Scaffolds project memory in `.specify/`.
- **Step 2: `/speckit-constitution`** — Ratifies non-negotiable security, privacy, and architectural ground rules.
- **Step 3: `/speckit-specify`** — Generates testable `spec.md` with Given-When-Then scenarios.
- **Step 4: `/speckit-plan`** — Synthesizes technical architecture blueprint into `plan.md`.
- **Step 5: `/speckit-analyze` [Verification Loop 1: Plan vs. Spec]** — Catches missing security rules, dependency inversion errors, or unaddressed acceptance criteria.
- **Step 6: `/speckit-tasks`** — Decomposes validated plan into dependency-ordered TDD tasks (`tasks.md`) in strict RED before GREEN order.
- **Step 7: `/speckit-analyze` [Verification Loop 2: Tasks vs. Plan & Spec]** — Verifies 100% user story coverage with zero missing requirements.
- **Step 8: `/speckit-tasks` (Iterative Refinement Loop)** — Mandatory audit-fix loop. Repeat `/speckit-analyze ↻ /speckit-tasks` until **Zero Gaps Identified** (Gate G2 approval).
- **MANDATORY TRANSITION PROTOCOL:** Always open a **brand-new Copilot Chat tab** (or launch `scripts/agent-worktree.ps1`) before running `/speckit-implement` to eliminate context window pollution.
- **Step 9: `/speckit-implement` [Agent Mode TDD Execution in Fresh Chat]** — Executes tasks phase by phase in strict TDD order.
- **Step 10: `/speckit-converge`** — Adversarial pre-release audit verifying 100% acceptance criteria and zero specification drift.
- **Step 11: `gh aw compile`** — Compiles markdown workflow policies into immutable GitHub Actions lockfiles.

---

## 4. Verification & Testing Strategy
1. **Terminal Test:** Execute `.\.specify\scripts\powershell\speckit-help.ps1` in PowerShell and verify exit code 0 and proper colorized formatting.
2. **Filtered Terminal Test:** Execute `.\.specify\scripts\powershell\speckit-help.ps1 -Stage build` and verify targeted phase output.
3. **Copilot Skill Format Test:** Validate YAML frontmatter and markdown schema against `.github/skills/speckit-specify/SKILL.md`.
4. **Git Isolation:** Ensure all commits exist exclusively on `help-feature` branch branched from `main`.
