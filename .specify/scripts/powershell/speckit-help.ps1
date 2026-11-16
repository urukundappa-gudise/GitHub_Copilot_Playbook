param(
    [string]$Stage = "all"
)

$Host.UI.RawUI.ForegroundColor = "White"

function Write-Header {
    param([string]$Text)
    Write-Host "`n================================================================================" -ForegroundColor DarkCyan
    Write-Host " $Text" -ForegroundColor Cyan -NoNewline
    Write-Host " (GitHub-Native Spec-Kit Lifecycle)" -ForegroundColor DarkGray
    Write-Host "================================================================================" -ForegroundColor DarkCyan
}

function Write-Step {
    param(
        [int]$Num,
        [string]$Cmd,
        [string]$Purpose,
        [string]$Info,
        [string]$Example
    )
    Write-Host "`nStep ${Num}: " -ForegroundColor Yellow -NoNewline
    Write-Host "$Cmd" -ForegroundColor Green
    Write-Host "  * Purpose: " -ForegroundColor DarkGray -NoNewline
    Write-Host "$Purpose" -ForegroundColor White
    Write-Host "  * Input:   " -ForegroundColor DarkGray -NoNewline
    Write-Host "$Info" -ForegroundColor Gray
    Write-Host "  * Example: " -ForegroundColor DarkGray -NoNewline
    Write-Host "$Example" -ForegroundColor DarkCyan
}

function Write-Callout {
    param([string]$Title, [string[]]$Lines)
    Write-Host "`n+------------------------------------------------------------------------------+" -ForegroundColor DarkYellow
    Write-Host "|  $Title" -ForegroundColor Yellow
    Write-Host "+------------------------------------------------------------------------------+" -ForegroundColor DarkYellow
    foreach ($line in $Lines) {
        Write-Host "   $line" -ForegroundColor DarkYellow
    }
    Write-Host "+------------------------------------------------------------------------------+" -ForegroundColor DarkYellow
}

Write-Header "INFOVISION SPEC-KIT COMMAND CENTER & LIFECYCLE GUIDE"

$stageLower = $Stage.ToLower()

if ($stageLower -eq "all" -or $stageLower -eq "init" -or $stageLower -eq "governance") {
    Write-Step 1 "/speckit-init" "Prepares repository for AI development. Scaffolds memory in .specify/." "None. Run once at root." "/speckit-init"
    Write-Step 2 "/speckit-constitution" "Ratifies non-negotiable security/architectural ground rules that AI cannot bypass." "Team security baselines (zero PII, mandatory auth, 100% tests pass)." "/speckit-constitution Ratify principles: zero PII in logs; OIDC federation."
}

if ($stageLower -eq "all" -or $stageLower -eq "design" -or $stageLower -eq "specify") {
    Write-Step 3 "/speckit-specify" "Converts business requirements into testable Given-When-Then spec.md." "Feature description, user personas, boundaries." "/speckit-specify Build claims intake service with audio & PDF intake."
    Write-Step 4 "/speckit-plan" "Synthesizes technical blueprint (plan.md), contracts, schemas, and stack choices." "Stack preferences, database choice, OpenAPI specs." "/speckit-plan FastAPI + SQLite demo + Authlib PKCE S256 SSO."
    Write-Step 5 "/speckit-analyze [Loop 1: Plan vs. Spec]" "Adversarial audit checking plan against spec & constitution. Catches inversion errors." "None. Cross-reads spec.md, plan.md, constitution.md." "/speckit-analyze Cross-check plan.md against spec.md and constitution.md."
    Write-Step 6 "/speckit-tasks" "Decomposes validated plan into phased TDD tasks (RED failing tests before GREEN code)." "None. Generates tasks.md." "/speckit-tasks Decompose plan.md into test-first implementation tasks."
    Write-Step 7 "/speckit-analyze [Loop 2: Tasks vs. Plan & Spec]" "Verifies 100% testable task coverage for every user story and acceptance scenario." "None. Cross-checks tasks.md against plan.md & spec.md." "/speckit-analyze Verify tasks.md covers all requirements with zero gaps."
    Write-Step 8 "/speckit-tasks (Refinement Loop)" "MANDATORY AUDIT-FIX LOOP: Repeat /speckit-analyze ↻ /speckit-tasks until ZERO GAPS." "Instruct Copilot to resolve specific gap findings." "/speckit-tasks Resolve analysis findings: close gap T003 before code authoring."
}

if ($stageLower -eq "all" -or $stageLower -eq "build" -or $stageLower -eq "implement") {
    Write-Callout "MANDATORY TRANSITION PROTOCOL: OPEN A FRESH / NEW COPILOT CHAT SESSION" @(
        "Rule (Playbook pp. 7 & 15): ALWAYS open a clean Copilot Chat tab (or launch scripts/agent-worktree.ps1)",
        "before running /speckit-implement.",
        "Why: Clears brainstorming history and context pollution so Agent Mode focuses 100% on tasks.md."
    )

    Write-Step 9 "/speckit-implement [Agent Mode TDD in Fresh Chat]" "Switches Copilot to Agent Mode to execute tasks phase-by-phase in strict TDD order." "Specify phase (e.g. 'Phase 1: Core Schemas') or task ID." "/speckit-implement Implement Phase 1: Core Schemas in strict TDD order."
}

if ($stageLower -eq "all" -or $stageLower -eq "test" -or $stageLower -eq "converge" -or $stageLower -eq "release") {
    Write-Step 10 "/speckit-converge" "Adversarial pre-release audit verifying 100% acceptance satisfaction & zero drift." "Scope of audit (e.g. Pre-Release Buildable Specification only)." "/speckit-converge Audit implementation against Pre-Release Buildable Spec only."
    Write-Step 11 "gh aw compile" "Compiles human markdown workflow policies into immutable Actions lockfiles." "None. Terminal CLI command." "gh aw compile"
}

Write-Host "`nReady for execution in GitHub Copilot Chat or terminal." -ForegroundColor Green
Write-Host ""
