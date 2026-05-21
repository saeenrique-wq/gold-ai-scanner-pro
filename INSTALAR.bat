@echo off
title GOLD AI SCANNER PRO - Instalacion
color 0E
echo.
echo  ======================================================
echo   GOLD AI SCANNER PRO - Instalacion automatica
echo  ======================================================
echo.
echo  Instalando dependencias necesarias...
echo.

cd /d "%~dp0"
pip install -r requirements.txt

echo.
echo  ======================================================
echo   Instalacion completada!
echo.
echo   Ahora ejecuta INICIAR.bat para abrir el scanner.
echo  ======================================================
echo.
pause
