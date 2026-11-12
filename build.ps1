
$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

function Stop-Build {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

try {
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "       CONTROLSTOCK - BUILD" -ForegroundColor Cyan
    Write-Host "======================================" -ForegroundColor Cyan

    # 1. Detectar Python
    Write-Host "`n[1/5] Comprobando Python..." -ForegroundColor Cyan

    $PythonExe = $null
    $PyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue

    if ($PyLauncher) {
        $PythonExe = (& $PyLauncher.Source -c "import sys; print(sys.executable)").Trim()
    }

    # 2. Instalar Python si no existe
    if (-not $PythonExe -or -not (Test-Path $PythonExe)) {

        Write-Host "Python no encontrado. Instalando..." -ForegroundColor Yellow

        $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue

        if (-not $Winget) {
            Stop-Build "No se encontro winget. Instala Python desde https://www.python.org/downloads/windows/ y vuelve a ejecutar."
        }

        & $Winget.Source install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements

        if ($LASTEXITCODE -ne 0) {
            Stop-Build "No se pudo instalar Python mediante winget."
        }

        $PythonExe = "$env:LocalAppData\Programs\Python\Python313\python.exe"

        if (-not (Test-Path $PythonExe)) {
            Stop-Build "Python fue instalado, pero no se encontro el ejecutable. Reinicia PowerShell y vuelve a ejecutar el script."
        }
    }

    Write-Host "Python encontrado: $PythonExe" -ForegroundColor Green
    & $PythonExe --version

    # 3. Instalar dependencias
    Write-Host "`n[2/5] Instalando dependencias..." -ForegroundColor Cyan

    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Stop-Build "Error actualizando pip." }

    & $PythonExe -m pip install -r requirements.txt pytest pyinstaller
    if ($LASTEXITCODE -ne 0) { Stop-Build "Error instalando dependencias." }

    # 4. Ejecutar pruebas
    Write-Host "`n[3/5] Ejecutando pruebas..." -ForegroundColor Cyan

    & $PythonExe -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { Stop-Build "Las pruebas fallaron. No se generara el ejecutable." }

    # 5. Generar ejecutable
    Write-Host "`n[4/5] Generando ejecutable..." -ForegroundColor Cyan

    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onefile `
        --name ControlStock `
        --collect-submodules app `
        run.py

    if ($LASTEXITCODE -ne 0) {
        Stop-Build "PyInstaller no pudo generar el ejecutable."
    }

    # Verificar resultado
    Write-Host "`n[5/5] Verificando resultado..." -ForegroundColor Cyan

    $ExePath = Join-Path $PSScriptRoot "dist\ControlStock.exe"

    if (-not (Test-Path $ExePath)) {
        Stop-Build "No se encontro ControlStock.exe."
    }

    $File = Get-Item $ExePath

    if ($File.Length -le 0) {
        Stop-Build "El ejecutable generado esta vacio."
    }

    Write-Host "`n======================================" -ForegroundColor Green
    Write-Host " COMPILACION COMPLETADA CORRECTAMENTE" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Green
    Write-Host "Archivo: $ExePath"
    Write-Host "Tamano: $([math]::Round($File.Length / 1MB, 2)) MB"

}
catch {
    Stop-Build $_.Exception.Message
}

