[CmdletBinding()]
param(
    [switch]$Required
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$previousVerifyRequired = $env:VERIFY_REQUIRED
$exitCode = 0
$locationPushed = $false

function Invoke-VerificationStep {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    Write-Host "Running: $Command $($Arguments -join ' ')"
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Verification step failed with exit code $LASTEXITCODE."
    }
}

try {
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        throw 'PowerShell 7 or newer is required.'
    }
    foreach ($tool in @('uv', 'node', 'npm', 'pwsh')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "Required command is unavailable: $tool."
        }
    }
    if ($Required -and -not $env:TEST_POSTGRESQL_URL) {
        throw 'Required verification needs TEST_POSTGRESQL_URL for a disposable PostgreSQL database.'
    }
    $workflowDirectory = Join-Path $repoRoot '.github/workflows'
    $disabledWorkflows = @(
        Get-ChildItem -LiteralPath $workflowDirectory -File -Recurse |
            Where-Object { $_.Name -match '\.disabled(?:\.|$)' }
    )
    if ($disabledWorkflows.Count -gt 0) {
        throw 'Disabled workflow files are not allowed under .github/workflows.'
    }

    if ($Required) {
        $env:VERIFY_REQUIRED = '1'
    }

    Push-Location $repoRoot
    $locationPushed = $true
    Invoke-VerificationStep 'uv' @('run', '--locked', '--project', 'backend', 'pytest', '-q')
    Write-Host 'Running Vitest discovery.'
    Invoke-VerificationStep 'npm' @('run', 'test', '--prefix', 'frontend')
    Invoke-VerificationStep 'npm' @('run', 'lint', '--prefix', 'frontend')
    Invoke-VerificationStep 'npm' @('run', 'typecheck', '--prefix', 'frontend')
    Invoke-VerificationStep 'npm' @('run', 'build', '--prefix', 'frontend')
    Invoke-VerificationStep 'uv' @('run', '--locked', '--project', 'backend', 'python', 'backend/scripts/run_golden_evaluation.py')
}
catch {
    Write-Error $_
    $exitCode = 1
}
finally {
    if ($locationPushed) {
        Pop-Location
    }
    if ($null -eq $previousVerifyRequired) {
        Remove-Item Env:VERIFY_REQUIRED -ErrorAction SilentlyContinue
    }
    else {
        $env:VERIFY_REQUIRED = $previousVerifyRequired
    }
}

exit $exitCode