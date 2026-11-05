@echo off
REM Try the exercise on this computer only.
cd /d "%~dp0"
call _setup.bat || exit /b 1
echo.
echo   Participant view:  http://localhost:8501
echo   Facilitator view:  http://localhost:8501/?view=facilitator
echo   (close this window to stop the app)
echo.
.venv\Scripts\python.exe -m streamlit run app.py --server.address localhost --server.port 8501
pause
