param([Parameter(ValueFromRemainingArguments = $true)][string[]]$AppArguments)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runtimeFile = Join-Path $projectRoot 'requirements.txt'
$devFile = Join-Path $projectRoot 'requirements-dev.txt'
$needsDev = $AppArguments.Count -gt 0 -and $AppArguments[0] -eq 'test'

if (-not (Test-Path -LiteralPath $projectPython)) {
    $basePython = Get-Command py -ErrorAction SilentlyContinue
    if ($basePython) {
        & $basePython.Source -3 -m venv (Join-Path $projectRoot '.venv')
    } elseif (Test-Path -LiteralPath 'F:\Data\.python\python.exe') {
        & 'F:\Data\.python\python.exe' -m venv (Join-Path $projectRoot '.venv')
    } else {
        $basePython = Get-Command python -ErrorAction SilentlyContinue
        if (-not $basePython) { throw 'Install Python 3.12+ before running this project.' }
        & $basePython.Source -m venv (Join-Path $projectRoot '.venv')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python environment.' }
}

$runtimeHash = (Get-FileHash -LiteralPath $runtimeFile -Algorithm SHA256).Hash
$stampFile = Join-Path $projectRoot '.venv\runtime-requirements.sha256'
$previousHash = if (Test-Path -LiteralPath $stampFile) { (Get-Content -LiteralPath $stampFile -Raw).Trim() } else { '' }
if ($previousHash -ne $runtimeHash) {
    & $projectPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare pip in the project environment.' }
    & $projectPython -m pip install -r $runtimeFile
    if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed; check the internet connection.' }
    Set-Content -LiteralPath $stampFile -Value $runtimeHash -Encoding ascii
}
if ($needsDev) {
    $devHash = $runtimeHash + (Get-FileHash -LiteralPath $devFile -Algorithm SHA256).Hash
    $devStamp = Join-Path $projectRoot '.venv\dev-requirements.sha256'
    $previousDevHash = if (Test-Path -LiteralPath $devStamp) { (Get-Content -LiteralPath $devStamp -Raw).Trim() } else { '' }
    if ($previousDevHash -ne $devHash) {
        & $projectPython -m pip install -r $devFile
        if ($LASTEXITCODE -ne 0) { throw 'Test dependency setup failed.' }
        Set-Content -LiteralPath $devStamp -Value $devHash -Encoding ascii
    }
}
if ($AppArguments.Count -gt 0 -and $AppArguments[0] -eq 'setup') {
    Write-Output 'Project environment is ready.'
    exit 0
}
& $projectPython (Join-Path $projectRoot 'run.py') @AppArguments
exit $LASTEXITCODE
