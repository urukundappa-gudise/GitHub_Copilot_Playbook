[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git is required to install hooks.'
    }
    $configuredPath = & git config --get core.hooksPath 2>$null
    $configExitCode = $LASTEXITCODE
    if ($configExitCode -eq 0 -and $configuredPath -ne '.githooks') {
        throw "Hook installation conflict: core.hooksPath is already configured as '$configuredPath'."
    }

    $hookDirectory = Join-Path $repoRoot '.githooks'
    $prePushHook = Join-Path $hookDirectory 'pre-push'
    if (-not (Test-Path -LiteralPath $prePushHook -PathType Leaf)) {
        throw 'The tracked .githooks/pre-push hook is missing.'
    }
    if ($configExitCode -ne 0) {
        $activeHooks = (& git rev-parse --git-path hooks).Trim()
        if (-not [System.IO.Path]::IsPathRooted($activeHooks)) {
            $activeHooks = Join-Path $repoRoot $activeHooks
        }
        $existingPrePush = Join-Path $activeHooks 'pre-push'
        if (Test-Path -LiteralPath $existingPrePush -PathType Leaf) {
            throw "Hook installation conflict: an existing pre-push hook is present at '$existingPrePush'. Resolve it without overwriting user hooks."
        }
        & git config --local core.hooksPath .githooks
        if ($LASTEXITCODE -ne 0) {
            throw 'Git could not configure .githooks as the local hooks path.'
        }
    }
    Write-Host 'Git pre-push verification hook is installed.'
}
finally {
    Pop-Location
}