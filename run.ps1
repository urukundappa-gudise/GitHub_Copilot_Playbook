param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$Test,
    [string]$TestRoot,
    [switch]$UseSqlite
)

$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$envFile = Join-Path $repoRoot '.env'
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            elseif ($value -match '\s+#') {
                $value = ($value -split '\s+#', 2)[0].TrimEnd()
            }
            if (-not (Test-Path "env:$name")) {
                Set-Item "env:$name" $value
            }
        }
    }
}

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. Install it and try again."
    }
}

if ($Test) {
    $testRootPath = $repoRoot
    if ($TestRoot) {
        if (-not (Test-Path -LiteralPath $TestRoot -PathType Container)) {
            throw "Test root '$TestRoot' was not found."
        }
        $testRootPath = (Resolve-Path -LiteralPath $TestRoot).Path
    }
    Set-Location $testRootPath
    Require-Command 'npm'
    Require-Command 'node'
    if (-not (Test-Path (Join-Path $testRootPath 'frontend/node_modules'))) {
        throw "Frontend dependencies are missing. Run 'npm ci --prefix frontend' first."
    }

    $uvCommand = Get-Command 'uv' -ErrorAction SilentlyContinue
    $backendPath = Join-Path $testRootPath 'backend'
    $venvPython = Join-Path $backendPath '.venv\Scripts\python.exe'
    $backendTestPaths = @(
        'tests/unit/safety',
        'tests/unit/test_extraction.py',
        'tests/integration/graph',
        'tests/integration/persistence',
        'tests/integration/test_no_facts_boundaries.py',
        'tests/contract/api',
        'tests/contract/test_schema_golden.py',
        'tests/unit/evaluation'
    )
    $optionalBackendTestPaths = @(
        'tests/contract/test_verification_gates.py',
        'tests/unit/test_email_validation.py'
    )
    $availableBackendFeatureTests = @($optionalBackendTestPaths | Where-Object { Test-Path (Join-Path $backendPath $_) })
    $backendTestPaths += $availableBackendFeatureTests

    $frontendTestPaths = @(
        'src/App.test.tsx',
        'src/tests/intake-flow.test.tsx',
        'src/tests/human_declarations.test.tsx',
        'src/tests/clarification.test.tsx'
    )
    $optionalFrontendTestPaths = @(
        'src/tests/submission-outcomes.test.tsx',
        'src/tests/safety-notices.test.tsx',
        'src/tests/outcome-dialog.test.tsx'
    )
    $availableFrontendFeatureTests = @($optionalFrontendTestPaths | Where-Object { Test-Path (Join-Path $testRootPath "frontend\$_") })
    $frontendTestPaths += $availableFrontendFeatureTests

    if ($availableBackendFeatureTests.Count -gt 0 -and $availableFrontendFeatureTests.Count -gt 0) {
        Write-Host 'Submission confirmation and safety notice test suites are present.'
    }
    else {
        Write-Warning 'This checkout lacks one or more submission/safety-specific test modules. Running the available related intake suites; switch to the implementation branch for full feature coverage.'
    }

    $env:AUTH_REQUIRED = 'false'
    $env:ALLOWED_ORIGINS = 'http://testserver,http://localhost:5173,http://127.0.0.1:5173'
    $env:DATABASE_URL = 'sqlite+pysqlite:///:memory:'

    if ($uvCommand) {
        Push-Location $backendPath
        try {
            uv run --no-sync pytest -q @backendTestPaths
        }
        finally {
            Pop-Location
        }
    }
    elseif (Test-Path $venvPython) {
        Push-Location $backendPath
        try {
            & $venvPython -m pytest -q @backendTestPaths
        }
        finally {
            Pop-Location
        }
    }
    else {
        throw "Backend test dependencies are missing. Install uv or create backend\.venv with the backend dev dependencies."
    }
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed with exit code $LASTEXITCODE." }

    $frontendPath = Join-Path $testRootPath 'frontend'
    npm run test --prefix $frontendPath -- @frontendTestPaths
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed with exit code $LASTEXITCODE." }
    npm run lint --prefix $frontendPath
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed with exit code $LASTEXITCODE." }
    npm run typecheck --prefix $frontendPath
    if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck failed with exit code $LASTEXITCODE." }
    npm run build --prefix $frontendPath
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed with exit code $LASTEXITCODE." }

    $goldenRunner = Join-Path $backendPath 'scripts\run_golden_evaluation.py'
    if ($uvCommand) {
        Push-Location $backendPath
        try {
            uv run --no-sync python scripts/run_golden_evaluation.py
        }
        finally {
            Pop-Location
        }
    }
    else {
        & $venvPython $goldenRunner
    }
    if ($LASTEXITCODE -ne 0) { throw "Golden evaluation failed with exit code $LASTEXITCODE." }
    return
}

if ($Backend) {
    Set-Location $repoRoot
    $uvCommand = Get-Command 'uv' -ErrorAction SilentlyContinue
    $backendPath = Join-Path $repoRoot 'backend'
    $venvPython = Join-Path $backendPath '.venv\Scripts\python.exe'
    if ($uvCommand) {
        uv sync --project backend --all-extras
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    else {
        $pythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
        $pythonArguments = @()
        if (-not $pythonCommand) {
            $pythonCommand = Get-Command 'py' -ErrorAction SilentlyContinue
            $pythonArguments = @('-3')
        }
        if (-not $pythonCommand) {
            throw "Python 3.11 or newer is required when 'uv' is not installed."
        }

        & $pythonCommand.Source @pythonArguments -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
        if (-not (Test-Path $venvPython)) {
            & $pythonCommand.Source @pythonArguments -m venv (Join-Path $backendPath '.venv')
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }

        Push-Location $backendPath
        try {
            & $venvPython -m pip install -e '.[dev]'
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        finally {
            Pop-Location
        }
    }

    if ($UseSqlite) {
        if ($env:DATABASE_URL -notmatch '^sqlite') {
            $env:DATABASE_URL = 'sqlite+pysqlite:///:memory:'
        }
    }
    elseif (-not $env:DATABASE_URL) {
        $env:DATABASE_URL = 'postgresql+psycopg://aimplify:change-me@localhost:5432/aimplify'
    }
    $env:MAX_UPLOAD_BYTES = '20971520'
    Push-Location (Join-Path $repoRoot 'backend')
    try {
        if ($env:DATABASE_URL -notmatch '^sqlite') {
            if ($uvCommand) {
                uv run alembic upgrade head
            }
            else {
                & $venvPython -m alembic upgrade head
            }
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        if ($uvCommand) {
            uv run uvicorn aimplify_intake.main:app --reload
        }
        else {
            & $venvPython -m uvicorn aimplify_intake.main:app --reload
        }
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

if ($Frontend) {
    Set-Location $repoRoot
    if (-not (Test-Path (Join-Path $repoRoot 'frontend/node_modules'))) {
        npm ci --prefix frontend
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    npm run dev --prefix frontend
    exit $LASTEXITCODE
}

Require-Command 'node'
Require-Command 'npm'
if (-not (Get-Command 'uv' -ErrorAction SilentlyContinue) -and
    -not (Get-Command 'python' -ErrorAction SilentlyContinue) -and
    -not (Get-Command 'py' -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or newer (or 'uv') is required to run the backend."
}

Set-Location $repoRoot
$dockerCommand = Get-Command 'docker' -ErrorAction SilentlyContinue
$useSqlite = $UseSqlite -or $env:DATABASE_URL -match '^sqlite' -or -not $dockerCommand
if ($useSqlite) {
    if ($env:DATABASE_URL -notmatch '^sqlite') {
        $env:DATABASE_URL = 'sqlite+pysqlite:///:memory:'
    }
    if ($env:DATABASE_URL -match ':memory:') {
        Write-Warning 'Starting with in-memory SQLite; local data will not persist.'
    }
    else {
        Write-Host 'Starting with the SQLite database configured in .env.'
    }
}
else {
    docker compose up -d --wait postgres
    if ($LASTEXITCODE -ne 0) { throw 'Could not start PostgreSQL with Docker Compose.' }
}

$scriptPath = Join-Path $repoRoot 'run.ps1'
if ($useSqlite) {
    Start-Process powershell.exe -ArgumentList @(
        '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $scriptPath, '-Backend', '-UseSqlite'
    )
}
else {
    Start-Process powershell.exe -ArgumentList @(
        '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $scriptPath, '-Backend'
    )
}
Start-Process powershell.exe -ArgumentList @(
    '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $scriptPath, '-Frontend'
)

Write-Host 'Application startup launched.'
Write-Host 'Frontend: http://localhost:5173'
Write-Host 'Backend:  http://localhost:8000/health/live'