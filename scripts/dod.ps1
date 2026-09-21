$ErrorActionPreference = "Stop"

Write-Host "=== Running Definition of Done (Quackend) ===" -ForegroundColor Cyan

try {
    Write-Host "[1/5] Checking Layer Contracts (import-linter)..." -ForegroundColor Blue
    lint-imports
    if ($LASTEXITCODE -ne 0) { throw "import-linter failed" }

    Write-Host "[2/5] Linting Code (ruff)..." -ForegroundColor Blue
    ruff check .
    if ($LASTEXITCODE -ne 0) { throw "ruff check failed" }

    Write-Host "[3/5] Checking Code Format (ruff format)..." -ForegroundColor Blue
    ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw "ruff format failed" }

    Write-Host "[4/5] Verifying Static Types (mypy)..." -ForegroundColor Blue
    mypy src
    if ($LASTEXITCODE -ne 0) { throw "mypy failed" }

    Write-Host "[5/5] Running Tests & Coverage (pytest)..." -ForegroundColor Blue
    python -m coverage run -m pytest
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }

    python -m coverage report --fail-under=80
    if ($LASTEXITCODE -ne 0) { throw "coverage threshold not met" }

    Write-Host "" -NoNewline
    Write-Host "SUCCESS: All DoD checks passed! Ready to commit." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "" -NoNewline
    Write-Host "FAILED: $_" -ForegroundColor Red
    Write-Host "Fix the errors above before committing or creating a PR." -ForegroundColor Yellow
    exit 1
}