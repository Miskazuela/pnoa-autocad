@echo off
title PNOA to AutoCAD - Instalador de Dependencias
cd /d "%~dp0"

echo ======================================================================
echo    Instalando librerias para PNOA to AutoCAD
echo ======================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se detecto Python instalado en este equipo.
    echo Por favor instala Python marcando la casilla "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo Actualizando pip...
python -m pip install --upgrade pip

echo.
echo Instalando dependencias desde requirements.txt...
pip install -r requirements.txt

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo    Instalacion completada con exito!
    echo    Ya puedes ejecutar "iniciar_app.bat".
    echo ======================================================================
) else (
    echo.
    echo [ERROR] Hubo un problema al instalar las dependencias.
)
echo.
pause
