---
name: "speckit-help"
description: "Interactive Command Center & Sequential Lifecycle Guide for GitHub-Native Spec-Kit Development."
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/help.md"
---

## User Input

```text
$ARGUMENTS
```

## System Role & Persona
You are the **InfoVision Spec-Kit Orchestrator and Copilot Guide**. 
When the user executes `/speckit-help`, your objective is to present the complete, ordered, 11-step enterprise lifecycle guide in clear, plain-English bullet points (no tables for the steps), starting strictly at **Step 1**.

If the user provides an argument (e.g. `/speckit-help design`, `/speckit-help build`, `/speckit-help test`, or `/speckit-help loop`), focus your guidance on that specific phase while providing the overall context. If called with no arguments, display the complete 11-step guide below.

---

## The Spec-Kit Enterprise Lifecycle Guide

Display the following 11-step point-by-point workflow with clear headings, bulleted details, and code examples:

### Step 1: `/speckit-init`
* **Purpose:** Prepares your repository for AI-assisted development. Bootstraps persistent workspace memory in `.specify/` and registers Copilot slash tools.
* **What information you provide:** None. Run once at the repository root folder.
* **Example:**
```text
/speckit-init
```

### Step 2: `/speckit-constitution`
* **Purpose:** Ratifies the supreme, non-negotiable architectural, security, and privacy ground rules (e.g., zero PII logging, mandatory auth, 100% test pass) that Copilot cannot override.
* **What information you provide:** Team security baselines and architectural invariants.
* **Example:**
```text
/speckit-constitution Ratify principles: 100% automated test pass required; zero PII or auth tokens in logs; OIDC token federation for cloud infrastructure.
```

### Step 3: `/speckit-specify`
* **Purpose:** Converts a business feature request into an unambiguous, testable specification (`spec.md`) with Given-When-Then acceptance scenarios.
* **What information you provide:** Describe what you want to build in plain English, target users, and functional boundaries.
* **Example:**
```text
/speckit-specify We need to build an automated claims intake service. It must accept PDF and audio memo inputs, enforce single-question pacing, and populate 18 canonical fields without persisting files to disk.
```

### Step 4: `/speckit-plan`
* **Purpose:** Synthesizes the formal technical blueprint (`plan.md`), selecting libraries, database schemas, and OpenAPI contracts.
* **What information you provide:** Framework preferences, database choices, or compliance constraints.
* **Example:**
```text
/speckit-plan Design the architecture using FastAPI, in-memory SQLite for demo mode, Authlib with PKCE S256 for SSO, and strict same-origin App Runner policies.
```

### Step 5: `/speckit-analyze` [Verification Loop 1: Plan vs. Spec]
* **Purpose:** Performs an automated adversarial audit checking `plan.md` against `spec.md` and `constitution.md`. Catches missing security rules, dependency inversion errors (e.g., scheduling business logic before validation gates), and unaddressed acceptance criteria before any tasks are scheduled.
* **What information you provide:** None. Automatically cross-reads `spec.md`, `plan.md`, and `constitution.md`.
* **Example:**
```text
/speckit-analyze Cross-check specs/001-claims/plan.md against spec.md and constitution.md for requirement coverage and security boundaries.
```

### Step 6: `/speckit-tasks`
* **Purpose:** Decomposes the validated blueprint into an organized checklist of phased implementation tasks (`tasks.md`), strictly scheduling failing tests before implementation code (RED test before GREEN implementation).
* **What information you provide:** None. Reads the validated plan and generates ordered tasks.
* **Example:**
```text
/speckit-tasks Decompose specs/001-claims/plan.md into phased, test-first implementation tasks.
```

### Step 7: `/speckit-analyze` [Verification Loop 2: Tasks vs. Plan & Spec]
* **Purpose:** A second audit pass verifying that every user story, acceptance scenario, and edge case has an assigned, testable task. Guarantees 100% task coverage with zero omissions.
* **What information you provide:** None. Cross-checks `tasks.md` against `plan.md` and `spec.md`.
* **Example:**
```text
/speckit-analyze Verify specs/001-claims/tasks.md covers all requirements from plan.md and spec.md with zero gaps remaining.
```

### Step 8: `/speckit-tasks` (Iterative Refinement Loop — Repeat Until Zero Gaps)
* **Purpose:** **Mandatory Audit-Fix Loop:** If Loop 2 identifies any missing test coverage, dependency circularity, or unaddressed edge cases, update `tasks.md` and **immediately re-run `/speckit-analyze`**. Repeat this analyze-refine loop as many times as needed until `/speckit-analyze` confirms **"Zero gaps identified"** (Gate G2 approval). No implementation code may be written while any gap remains.
* **What information you provide:** Instruct Copilot to resolve the specific audit findings.
* **Example:**
```text
/speckit-tasks Resolve analysis gap findings: add missing failing contract test for token expiry and reorder safety gate T003 before business logic T004.
```

---

> ### ⚠️ MANDATORY TRANSITION PROTOCOL: OPEN A FRESH / NEW COPILOT CHAT SESSION
> * **Rule (Playbook pp. 7 & 15):** Before executing Step 9 (`/speckit-implement`), **always open a clean Copilot Chat tab** (or launch an ephemeral worktree via `scripts/agent-worktree.ps1`).
> * **Why:** Long multi-turn planning discussions pollute the LLM context window with stale brainstorming history, causing prompt fatigue and drift during code authoring. A fresh chat session gives Copilot Agent Mode 100% clean context capacity focused strictly on `tasks.md`.

---

### Step 9: `/speckit-implement` [Agent Mode TDD Execution in Fresh Chat]
* **Purpose:** In the **fresh chat session**, switches Copilot to Agent Mode to execute tasks phase by phase in strict Test-Driven Development order (RED failing test $\to$ GREEN code $\to$ 0 test failures).
* **What information you provide:** Specify the phase (e.g., `Phase 1: Core Schemas and Safety Gate`) or task ID.
* **Example:**
```text
/speckit-implement Implement Phase 1: Core Schemas and Safety Gate in strict TDD order and run the test suite.
```

### Step 10: `/speckit-converge`
* **Purpose:** The final adversarial certification gate. Inspects the committed git diff against `spec.md` to mathematically certify 100% acceptance criteria satisfaction and zero specification drift.
* **What information you provide:** Scope of audit (e.g., `Pre-Release Buildable Specification only`).
* **Example:**
```text
/speckit-converge Audit implementation against Pre-Release Buildable Specification only.
```

### Step 11: `gh aw compile`
* **Purpose:** Compiles human-authored markdown workflow policies (`.github/workflows/*.md`) into locked, immutable GitHub Actions YAML files (`.lock.yml`). Run directly in terminal before merging.
* **What information you provide:** None. Terminal CLI command.
* **Example:**
```text
gh aw compile
```
