# =====================================================================
# PNOA to AutoCAD - Instalador de Entorno Python Portable
# Descarga y configura un entorno Python 100% independiente y aislado.
# =====================================================================

param(
    [string]$TargetDir = "$PSScriptRoot\.runtime"
)

$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   Configurando Entorno Portable para PNOA to AutoCAD" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path "$TargetDir\python.exe") {
    Write-Host "[OK] El entorno portable ya existe en: $TargetDir" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

$pythonZip = "$TargetDir\python-embed.zip"
$pythonUrl = "https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip"

Write-Host "[1/4] Descargando Python 3.12 portable (~10 MB)..." -ForegroundColor Yellow
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip -UseBasicParsing

Write-Host "[2/4] Descomprimiendo archivos en $TargetDir..." -ForegroundColor Yellow
Expand-Archive -Path $pythonZip -DestinationPath $TargetDir -Force
Remove-Item -Force $pythonZip

# Configurar el archivo ._pth para habilitar site-packages (pip)
Write-Host "[3/4] Habilitando soporte para librerias (site-packages)..." -ForegroundColor Yellow
$pthFile = Get-ChildItem -Path $TargetDir -Filter "*._pth" | Select-Object -First 1
if ($pthFile) {
    $content = Get-Content $pthFile.FullName
    $newContent = @()
    foreach ($line in $content) {
        if ($line -match "^#\s*import\s+site") {
            $newContent += "Lib"
            $newContent += "Lib\site-packages"
            $newContent += "import site"
        } else {
            $newContent += $line
        }
    }
    # Si no contenia el comentario, anadirlos explictamente
    if (-not ($newContent -contains "import site")) {
        $newContent += "Lib"
        $newContent += "Lib\site-packages"
        $newContent += "import site"
    }
    Set-Content -Path $pthFile.FullName -Value $newContent -Encoding Ascii
}

# Descargar e instalar pip
Write-Host "[4/4] Instalando gestor de librerias pip..." -ForegroundColor Yellow
$getPip = "$TargetDir\get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing

$pyExe = "$TargetDir\python.exe"
& $pyExe $getPip --no-warn-script-location --quiet
if (Test-Path $getPip) { Remove-Item -Force $getPip }

# Instalar dependencias si existe requirements.txt
$reqFile = "$PSScriptRoot\requirements.txt"
if (Test-Path $reqFile) {
    Write-Host ""
    Write-Host "Instalando librerias necesarias (Streamlit, ezdxf, shapely, etc.)..." -ForegroundColor Yellow
    Write-Host "Esto puede demorar 1-2 minutos la primera vez..." -ForegroundColor Gray
    & $pyExe -m pip install -r $reqFile --no-warn-script-location
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "   Entorno portable configurado con exito!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
