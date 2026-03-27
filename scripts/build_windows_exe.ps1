param(
  [string]$PythonExe = "python",
  [string]$Name = "HH Monitor",
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$Entry = Join-Path $ScriptDir "windows_entry.py"

if (-not (Test-Path $Entry)) {
  throw "Entry file not found: $Entry"
}

Push-Location $ProjectRoot
try {
  Write-Host "[build] Python version"
  & $PythonExe --version | Out-Host

  Write-Host "[build] Upgrade pip"
  & $PythonExe -m pip install --upgrade pip | Out-Host

  Write-Host "[build] Install dependencies"
  & $PythonExe -m pip install -r requirements.txt pyinstaller | Out-Host

  Write-Host "[build] Install Playwright Chromium into package-local path"
  $env:PLAYWRIGHT_BROWSERS_PATH = "0"
  & $PythonExe -m playwright install chromium | Out-Host

  $cleanArgs = @()
  if ($Clean) {
    $cleanArgs = @("--clean")
  }

  & $PythonExe -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name "$Name" `
    --paths "src" `
    --collect-all "playwright" `
    --collect-all "pydantic" `
    --collect-all "pydantic_core" `
    --collect-all "bs4" `
    --collect-all "lxml" `
    @cleanArgs `
    "$Entry" | Out-Host

  $Output = Join-Path $ProjectRoot "dist\$Name.exe"
  if (-not (Test-Path $Output)) {
    throw "Build failed: $Output not found"
  }

  Write-Host "Build complete. EXE: $Output"
}
finally {
  Pop-Location
}
