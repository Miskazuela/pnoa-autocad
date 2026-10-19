@echo off
setlocal EnableDelayedExpansion
title PNOA to AutoCAD - Extractor de Cartografia Oficial
cd /d "%~dp0"

echo ======================================================================
echo    Extractor de Cartografia PNOA para AutoCAD (IGN Espana)
echo ======================================================================
echo.

set "PY_CMD="

:: 1. Verificar si existe entorno portable en runtime o .runtime
if exist "%~dp0runtime\python.exe" (
    set "PY_CMD=%~dp0runtime\python.exe"
) else if exist "%~dp0.runtime\python.exe" (
    set "PY_CMD=%~dp0.runtime\python.exe"
) else (
    :: 2. Verificar si Python esta en el sistema
    where python >nul 2>nul
    if !ERRORLEVEL! EQU 0 (
        set "PY_CMD=python"
    )
)

:: 3. Si no existe ningun Python, configurar automaticamente el portable
if "%PY_CMD%"=="" (
    echo [AVISO] No se detecto Python instalado en tu equipo.
    echo No te preocupes: configuraremos un entorno portable y ligero automaticamente.
    echo Solo toma un momento la primera vez...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_runtime.ps1" -TargetDir "%~dp0.runtime"
    if exist "%~dp0.runtime\python.exe" (
        set "PY_CMD=%~dp0.runtime\python.exe"
    ) else (
        echo [ERROR] No se pudo configurar el entorno automatico.
        pause
        exit /b 1
    )
)

:: 4. Comprobar si las librerias estan instaladas
"%PY_CMD%" -c "import streamlit" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CONFIGURACION] Instalando librerias requeridas desde requirements.txt...
    "%PY_CMD%" -m pip install -r "%~dp0requirements.txt"
)

echo.
echo Iniciando aplicacion web en tu navegador predeterminado...
echo Direccion local: http://localhost:8501
echo.

"%PY_CMD%" -m streamlit run app.py --server.port=8501 --browser.serverAddress="localhost" --server.headless=false

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Ocurrio un problema al ejecutar la aplicacion.
    pause
)
