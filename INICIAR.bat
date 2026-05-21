@echo off
title GOLD AI SCANNER PRO
color 0A
echo.
echo  ======================================================
echo   GOLD AI SCANNER PRO - Iniciando...
echo  ======================================================
echo.
echo  Abriendo el scanner en tu navegador...
echo  Si no abre automatico, ve a: http://localhost:8501
echo.
echo  Para detener el scanner presiona Ctrl+C aqui.
echo.

cd /d "%~dp0"
streamlit run app.py --server.port 8501 --server.headless false

pause
