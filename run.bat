@echo off
setlocal
rem Windows: double-click to start the chatbot; the browser opens by itself. Close this window (or Ctrl+C) to stop.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
rem llama-server.exe (used for the optional Qwen helper) needs the Visual C++ runtime. If it is missing, try to install it (the chatbot still works without it).
if exist "bin\windows-x64\llama-server.exe" if not exist "bin\windows-x64\vcruntime140.dll" if not exist "%SystemRoot%\System32\vcruntime140.dll" call :vcredist
set "PY="
if exist "runtime\python\python.exe" "runtime\python\python.exe" -c "import sys" >nul 2>nul && set "PY=runtime\python\python.exe"
if not defined PY py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto :nopython
%PY% run_chat.py %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo. & echo The chatbot stopped with an error (code %RC%). Please read the messages above.
pause
exit /b %RC%
:nopython
echo Python 3.9 or newer is required.
echo 1) Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", or
echo 2) unpack the Windows "embeddable package" (64-bit zip) into the folder runtime\python in this folder.
echo Then double-click run.bat again.
pause
exit /b 1
:vcredist
echo The Microsoft Visual C++ runtime is missing (needed by the optional Qwen helper).
where winget >nul 2>nul
if errorlevel 1 goto :vcmanual
echo Installing it with winget (an administrator prompt may appear)...
winget install --id Microsoft.VCRedist.2015+.x64 -e --silent --accept-package-agreements --accept-source-agreements
exit /b 0
:vcmanual
echo Please install it from https://aka.ms/vs/17/release/vc_redist.x64.exe and run this file again. The chatbot will start now without the Qwen helper.
exit /b 0
