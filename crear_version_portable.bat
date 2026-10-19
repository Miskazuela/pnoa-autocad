@echo off
title PNOA to AutoCAD - Creador de Paquete Portable
cd /d "%~dp0"

echo ======================================================================
echo    Creador de Paquete Portable para PNOA to AutoCAD
echo ======================================================================
echo.
echo Este script creara la version comprimida (.ZIP) con Python embebido
echo lista para distribuir o subir a GitHub Releases.
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0crear_version_portable.ps1"

echo.
pause
