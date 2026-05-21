@echo off
title GOLD AI SCANNER PRO - Crear Ejecutable
color 0E
echo.
echo  ======================================================
echo   GOLD AI SCANNER PRO - Creando archivo .EXE
echo  ======================================================
echo.

cd /d "%~dp0"

echo  Paso 1: Instalando PyInstaller...
pip install pyinstaller --quiet
echo  PyInstaller instalado OK.
echo.

echo  Paso 2: Construyendo el ejecutable...
echo  (Esto puede tardar 1-2 minutos, por favor espera)
echo.

pyinstaller ^
  --onefile ^
  --noconsole ^
  --name "GOLD AI SCANNER PRO" ^
  --add-data "app.py;." ^
  --add-data "config.py;." ^
  --add-data "database.py;." ^
  --add-data "models.py;." ^
  --add-data "requirements.txt;." ^
  --add-data "market_data;market_data" ^
  --add-data "strategy;strategy" ^
  --add-data "ai;ai" ^
  --add-data "alerts;alerts" ^
  --add-data "web;web" ^
  launcher.py

echo.
if exist "dist\GOLD AI SCANNER PRO.exe" (
    echo  ======================================================
    echo   EXE CREADO EXITOSAMENTE
    echo.
    echo   Archivo: dist\GOLD AI SCANNER PRO.exe
    echo.
    echo   Copiando a la carpeta principal...
    copy "dist\GOLD AI SCANNER PRO.exe" "GOLD AI SCANNER PRO.exe"
    echo.
    echo   Listo! Haz doble clic en:
    echo   "GOLD AI SCANNER PRO.exe"
    echo  ======================================================
) else (
    echo  ERROR: No se pudo crear el ejecutable.
    echo  Revisa que Python este instalado correctamente.
)

echo.
pause
