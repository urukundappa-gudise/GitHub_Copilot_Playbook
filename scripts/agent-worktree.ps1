param(
    [Parameter(Mandatory=$true)]
    [string]$TaskName,
    [string]$BaseBranch = "feat/submission-popup-and-security-feedback"
)

$ErrorActionPreference = "Stop"

Write-Host "==> Pruning stale worktrees..." -ForegroundColor Yellow
git worktree prune

$RepoRoot = (git rev-parse --show-toplevel).Trim()
$WorktreesParent = Join-Path (Split-Path $RepoRoot -Parent) "worktrees"

if (-not (Test-Path $WorktreesParent)) {
    New-Item -ItemType Directory -Path $WorktreesParent -Force | Out-Null
}

$WorktreeDir = Join-Path $WorktreesParent $TaskName
$SubBranch = "feat/$TaskName"

if (Test-Path $WorktreeDir) {
    Write-Host "Worktree directory already exists at $WorktreeDir. Re-using..." -ForegroundColor Yellow
} else {
    Write-Host "==> Adding isolated git worktree: $WorktreeDir ($SubBranch) from $BaseBranch" -ForegroundColor Cyan
    git worktree add -b $SubBranch $WorktreeDir $BaseBranch
}

# Propagate Spec Kit memory and specs so Copilot retains project context
if (Test-Path "$RepoRoot\.specify") {
    $specifyDestination = Join-Path $WorktreeDir ".specify"
    if (-not (Test-Path $specifyDestination)) {
        New-Item -ItemType Directory -Path $specifyDestination -Force | Out-Null
    }
    Get-ChildItem -LiteralPath "$RepoRoot\.specify" -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $specifyDestination -Recurse -Force
    }
}
if (Test-Path "$RepoRoot\specs") {
    $specsDestination = Join-Path $WorktreeDir "specs"
    if (-not (Test-Path $specsDestination)) {
        New-Item -ItemType Directory -Path $specsDestination -Force | Out-Null
    }
    Get-ChildItem -LiteralPath "$RepoRoot\specs" -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $specsDestination -Recurse -Force
    }
}

Write-Host "==> Worktree ready at: $WorktreeDir" -ForegroundColor Green
Write-Host "==> Launching isolated VS Code Copilot agent session..." -ForegroundColor Green

code $WorktreeDir
