param(
    [string]$Device = "",
    [int]$Champions = 144,
    [int]$Top = 30,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$pythonCandidates = @(
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
    (Join-Path $root ".venv\Scripts\python.exe")
)
$python = $null
foreach ($candidate in $pythonCandidates) {
    if (-not (Test-Path -LiteralPath $candidate)) { continue }
    & $candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    throw "No working Python runtime found. Install Python 3.11+ or restore the project .venv."
}

$adbCommand = Get-Command adb -ErrorAction SilentlyContinue
if ($adbCommand) {
    $adb = $adbCommand.Source
} else {
    $scrcpyRoot = Join-Path $env:USERPROFILE "Downloads\scrcpy-win64-v3.3.4"
    $adb = Get-ChildItem -LiteralPath $scrcpyRoot -Filter adb.exe -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $adb) {
    throw "adb.exe was not found. Install Android platform-tools or keep the scrcpy folder in Downloads."
}
$env:PATH = "$(Split-Path -Parent $adb);$env:PATH"

$authorized = @(
    & $adb devices |
        Select-Object -Skip 1 |
        ForEach-Object {
            if ($_ -match '^([^\s]+)\s+device(?:\s|$)') { $Matches[1] }
        }
)
if (-not $Device) {
    if ($authorized.Count -ne 1) {
        throw "Expected exactly one authorized ADB device, found $($authorized.Count). Connect the NA phone and accept USB debugging, or pass -Device SERIAL."
    }
    $Device = $authorized[0]
} elseif ($Device -notin $authorized) {
    throw "ADB device '$Device' is not connected and authorized."
}

$dependencyPaths = @(
    (Join-Path $root ".scrape-paddle"),
    (Join-Path $root ".scrape-lite"),
    (Join-Path $root ".venv\Lib\site-packages"),
    (Join-Path $root ".wheel-extract"),
    (Join-Path $root ".local-python2")
) | Where-Object { Test-Path -LiteralPath $_ }
$env:PYTHONPATH = ($dependencyPaths -join ';')
$env:OCR_ENGINE = "auto"
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"

if (-not (Test-Path -LiteralPath $env:TESSERACT_CMD)) {
    throw "Tesseract is missing at $($env:TESSERACT_CMD)."
}

$freeBytes = [System.IO.DriveInfo]::new("C").AvailableFreeSpace
if ($freeBytes -lt 1GB) {
    throw "Less than 1 GB is free on C:. Clear space before starting the overnight collection."
}

& $python -c "import cv2, pytesseract; from src import ocr; import paddle, paddleocr; print('OCR preflight OK:', cv2.__version__, paddle.__version__, ocr.PADDLE_RECOGNITION_MODEL)"
if ($LASTEXITCODE -ne 0) {
    throw "OCR preflight failed. The collection was not started."
}

Write-Host "NA collection ready: $Champions champions, top $Top, win rate + builds, no stats."
Write-Host "Device: $Device"
Write-Host "The game will restart every 2 hours, only between completed champions."

if ($PreflightOnly) {
    Write-Host "Preflight complete; collection was not started."
    exit 0
}

& $python -m src.scrape_timed `
    --device $Device `
    --no-connect `
    --capture-only `
    --auto-scroll `
    --unattended `
    --auto-extract `
    --region NA `
    --capture-dir data/captures_na `
    --champions $Champions `
    --n $Top `
    --builds `
    --skip-existing `
    --refresh-after-hours 2 `
    --app-start-timeout 75

exit $LASTEXITCODE
