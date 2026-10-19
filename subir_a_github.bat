@echo off
title Subir cambios a GitHub
cd /d "%~dp0"

echo ======================================================================
echo    Subiendo cambios a GitHub (Miskazuela/pnoa-autocad)
echo ======================================================================
echo.

echo 1. Preparando archivos...
git add .

echo 2. Creando commit con las ultimas mejoras...
set "MSG=%~1"
if "%MSG%"=="" set "MSG=Lanzador ejecutable nativo PNOA_AutoCAD.exe y soporte portable sin Python"
git commit -m "%MSG%"

echo 3. Subiendo cambios a GitHub...
git push origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo    LISTO! Cambios subidos exitosamente a GitHub.
    echo    Streamlit Cloud se actualizara en vivo en 1-2 minutos.
    echo ======================================================================
) else (
    echo.
    echo [ERROR] Ocurrio un problema al conectar con GitHub.
)
echo.
pause
