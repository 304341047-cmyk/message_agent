@echo off
setlocal EnableExtensions

chcp 65001 >nul
cd /d "%~dp0"
title message_agent - Market News Assistant

echo ============================================================
echo   message_agent - Market News Assistant
echo ============================================================
echo Project: %CD%
echo.

rem Prefer a project-local virtual environment, then the Python launcher,
rem and finally the python.exe available on PATH.
set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "%CD%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
    goto :python_found
)

if exist "%CD%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"
    goto :python_found
)

rem Double-clicked terminals may not inherit Conda's PATH. Check the usual
rem per-user and machine-wide locations before relying on PATH discovery.
if exist "%USERPROFILE%\anaconda3\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
    goto :python_found
)

if exist "%USERPROFILE%\miniconda3\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
    goto :python_found
)

if exist "%ProgramData%\anaconda3\python.exe" (
    set "PYTHON_EXE=%ProgramData%\anaconda3\python.exe"
    goto :python_found
)

if exist "%ProgramData%\miniconda3\python.exe" (
    set "PYTHON_EXE=%ProgramData%\miniconda3\python.exe"
    goto :python_found
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%~fD\python.exe" (
        set "PYTHON_EXE=%%~fD\python.exe"
        goto :python_found
    )
)

where py.exe >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py.exe"
    set "PYTHON_ARGS=-3"
    goto :python_found
)

where python.exe >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python.exe"
    goto :python_found
)

echo [ERROR] Python 3 was not found.
echo Install Python 3 and select "Add Python to PATH", then try again.
goto :failed

:python_found
echo [1/4] Python environment
"%PYTHON_EXE%" %PYTHON_ARGS% --version
if errorlevel 1 (
    echo [ERROR] The detected Python installation cannot be started.
    goto :failed
)

echo.
echo [2/4] Configuration files
if not exist "config.yaml" (
    if exist "config.example.yaml" copy /Y "config.example.yaml" "config.yaml" >nul
    echo [ERROR] config.yaml was missing. A template has been created.
    echo Fill in the Feishu webhook and model settings, then run this file again.
    goto :failed
)

if not exist "keywords.yaml" (
    if exist "keywords.example.yaml" (
        copy /Y "keywords.example.yaml" "keywords.yaml" >nul
        echo Created keywords.yaml from the example file.
    ) else (
        echo [ERROR] keywords.yaml and keywords.example.yaml are both missing.
        goto :failed
    )
)
echo Configuration files found.

echo.
echo [3/4] Python dependencies
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import requests, yaml" >nul 2>&1
if errorlevel 1 (
    echo Missing dependencies. Installing from requirements.txt...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        goto :failed
    )
) else (
    echo Dependencies are ready.
)

if /I "%~1"=="--check" (
    echo.
    echo [4/4] Environment check passed. No collection or push was performed.
    exit /b 0
)

echo.
echo [4/4] Starting message_agent
echo Press Ctrl+C to stop the service.
echo ============================================================
echo.

"%PYTHON_EXE%" %PYTHON_ARGS% "run.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo [ERROR] message_agent exited with code %EXIT_CODE%.
) else (
    echo message_agent has stopped.
)
pause
exit /b %EXIT_CODE%

:failed
echo.
pause
exit /b 1
