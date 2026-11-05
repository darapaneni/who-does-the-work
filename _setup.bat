@echo off
REM Shared setup for the launchers: Python environment, packages and the local settings file.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating a Python environment in .venv ...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo Python 3.9+ was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
if not exist local_config.toml copy local_config.example.toml local_config.toml >nul
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  mkdir "%USERPROFILE%\.streamlit" 2>nul
  (echo [general]& echo email = "") > "%USERPROFILE%\.streamlit\credentials.toml"
)
exit /b 0
