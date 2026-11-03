$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

Write-Host "Instalando dependencias..." -ForegroundColor Cyan
python -m pip install -r requirements.txt

Write-Host "Ejecutando pruebas..." -ForegroundColor Cyan
python -m pytest tests -q

Write-Host "Generando ejecutable..." -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name ControlStock `
    --collect-submodules app `
    run.py

Write-Host ""
Write-Host "Ejecutable generado: dist\ControlStock.exe" -ForegroundColor Green
