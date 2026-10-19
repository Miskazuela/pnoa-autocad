@echo off
title PNOA to AutoCAD - Extractor de Cartografia y Ortofotos
cd /d "%~dp0"

echo ======================================================================
echo    Extractor de Cartografia PNOA para AutoCAD (IGN Espana)
echo ======================================================================
echo.
echo Iniciando aplicacion web en tu navegador predeterminado...
echo Direccion local: http://localhost:8501
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se encontro Python en el sistema.
    echo Por favor instala Python o anadelo a las variables de entorno.
    pause
    exit /b 1
)

python -m streamlit run app.py --server.port=8501 --browser.serverAddress="localhost" --server.headless=false

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Ocurrio un problema al ejecutar la aplicacion.
    echo Asegurate de haber instalado las dependencias requeridas con:
    echo pip install -r requirements.txt
    echo.
    pause
)
