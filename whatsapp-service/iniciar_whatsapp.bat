@echo off
title Servicio WhatsApp - ccgestion
cd /d "%~dp0"
echo ============================================================
echo  Servicio de WhatsApp de ccgestion
echo  NO CIERRES esta ventana mientras envias o esperas respuestas.
echo  Si el servicio se cae o se reinicia desde la app, se levanta solo.
echo  Para detenerlo del todo, cierra esta ventana.
echo ============================================================

:inicio
echo.
echo [%date% %time%] Iniciando el servicio de WhatsApp...
rem Cierra Chrome huerfanos de una ejecucion anterior (si no, bloquean la sesion guardada)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -like '*wwebjs_auth*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
rem Muestra la salida en pantalla y la guarda en ..\tmp\wa_service.log
if not exist "..\tmp" mkdir "..\tmp"
powershell -NoProfile -Command "npm start 2>&1 | Tee-Object -FilePath '..\tmp\wa_service.log' -Append"
echo.
echo [%date% %time%] El servicio se detuvo. Se reinicia en 5 segundos...
timeout /t 5 /nobreak >nul
goto inicio
