# =====================================================================
# PNOA to AutoCAD - Creador de Paquete Portable (.ZIP)
# Empaqueta la aplicacion completa con Python embebido y dependencias
# para distribuir a usuarios finales (sin necesidad de Python).
# =====================================================================

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$distDir = Join-Path $projectRoot "dist"
$portableDir = Join-Path $distDir "PNOA_to_AutoCAD_Portable"
$zipFile = Join-Path $distDir "PNOA_to_AutoCAD_Portable.zip"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   Creando Paquete Portable de PNOA to AutoCAD" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Limpiar versiones anteriores si existen
if (Test-Path $portableDir) {
    Write-Host "Limpiando compilacion anterior..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $portableDir
}
if (Test-Path $zipFile) {
    Remove-Item -Force $zipFile
}

New-Item -ItemType Directory -Path $portableDir -Force | Out-Null

# 2. Copiar archivos del proyecto
Write-Host "[1/5] Copiando archivos de la aplicacion..." -ForegroundColor Yellow
$filesToCopy = @(
    "app.py",
    "ejemplo_madrid.dxf",
    "requirements.txt"
)

foreach ($f in $filesToCopy) {
    $src = Join-Path $projectRoot $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $portableDir -Force
    }
}

# Copiar configuracion de Streamlit
$streamlitSrc = Join-Path $projectRoot ".streamlit"
if (Test-Path $streamlitSrc) {
    $streamlitDest = Join-Path $portableDir ".streamlit"
    Copy-Item -Path $streamlitSrc -Destination $streamlitDest -Recurse -Force
}

# 3. Compilar el lanzador nativo .exe dentro de la carpeta portable
Write-Host "[2/5] Compilando lanzador nativo PNOA_AutoCAD.exe..." -ForegroundColor Yellow
$cscPath = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$launcherCs = Join-Path $projectRoot "launcher.cs"
$launcherExe = Join-Path $portableDir "PNOA_AutoCAD.exe"

if (Test-Path $cscPath) {
    & $cscPath /nologo /target:winexe /out:$launcherExe $launcherCs
} else {
    Write-Host "[AVISO] No se encontro csc.exe. Copiando ejecutable preexistente si esta disponible..." -ForegroundColor Yellow
    $rootExe = Join-Path $projectRoot "PNOA_AutoCAD.exe"
    if (Test-Path $rootExe) {
        Copy-Item -Path $rootExe -Destination $launcherExe -Force
    }
}

# Crear tambien un lanzador BAT alternativo
$batContent = @"
@echo off
title PNOA to AutoCAD
cd /d "%~dp0"
"%~dp0runtime\python.exe" -m streamlit run app.py --server.port=8501 --browser.serverAddress="localhost" --server.headless=false
"@
Set-Content -Path (Join-Path $portableDir "Iniciar_PNOA.bat") -Value $batContent -Encoding Ascii

# 4. Crear archivo LEEME para el usuario final
Write-Host "[3/5] Generando instrucciones para el usuario..." -ForegroundColor Yellow
$readmeContent = @"
========================================================================
   PNOA to AutoCAD - Version Portable Oficial (Sin Instalacion)
========================================================================

Esta version incluye todo lo necesario para funcionar en cualquier equipo
con Windows 10 u 11, sin necesidad de tener Python instalado.

MODO DE USO:
1. Haz doble clic sobre:
   -> PNOA_AutoCAD.exe  (o sobre Iniciar_PNOA.bat)

2. Se abrira una ventana de control y tu navegador web se iniciara
   automaticamente con la aplicacion en:
   http://localhost:8501

3. Para cerrar la aplicacion, simplemente haz clic en "Detener y Salir"
   o cierra la ventanita de PNOA to AutoCAD.

DATOS DE PRUEBA:
- Puedes usar el archivo 'ejemplo_madrid.dxf' incluido en esta carpeta
  para probar la descarga de ortofotos PNOA y cartografia oficial de inmediato.
========================================================================
"@
Set-Content -Path (Join-Path $portableDir "LEEME_PRIMERO.txt") -Value $readmeContent -Encoding Default

# 5. Configurar Python portable embebido en runtime/
Write-Host "[4/5] Configurando Python embebido y descargando librerias..." -ForegroundColor Yellow
$runtimeDir = Join-Path $portableDir "runtime"
$setupScript = Join-Path $projectRoot "setup_runtime.ps1"

& $setupScript -TargetDir $runtimeDir

# 6. Comprimir en un unico archivo .zip listo para distribuir
Write-Host "[5/5] Comprimiendo en PNOA_to_AutoCAD_Portable.zip..." -ForegroundColor Yellow
Compress-Archive -Path "$portableDir\*" -DestinationPath $zipFile -CompressionLevel Optimal

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "   EXITO: Paquete portable creado correctamente!" -ForegroundColor Green
Write-Host "   Archivo listo para distribuir o subir a GitHub Releases:" -ForegroundColor Green
Write-Host "   $zipFile" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
