# ---------------------------------------------
# activate_venv.ps1
# Aktiviert sicher eine Python-venv in Windows
# ---------------------------------------------

# Name oder Pfad der venv (Standard: .venv)
$VenvPath = ".\.venv\Scripts\Activate.ps1"

# Prüfen, ob die venv existiert
if (!(Test-Path $VenvPath)) {
    Write-Host "⚠️  Keine virtuelle Umgebung gefunden: $VenvPath" -ForegroundColor Yellow
    Write-Host "Erstelle eine neue mit:" -ForegroundColor Yellow
    Write-Host "python -m venv .venv" -ForegroundColor Yellow
    exit
}

# Execution Policy nur für diese Sitzung lockern
Write-Host "🔧 Setze ExecutionPolicy = RemoteSigned (nur für diese Sitzung) ..."
Set-ExecutionPolicy RemoteSigned -Scope Process -Force

# venv aktivieren
Write-Host "🐍 Aktiviere virtuelle Umgebung ..."
. $VenvPath

Write-Host "✅ venv aktiv! ($env:VIRTUAL_ENV)" -ForegroundColor Green