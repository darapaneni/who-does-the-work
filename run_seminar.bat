@echo off
REM Seminar on the same Wi-Fi: participants join from their phones on the venue network.
REM If the venue Wi-Fi blocks phones from reaching this laptop, use run_seminar_public.bat instead.
cd /d "%~dp0"
call _setup.bat || exit /b 1
if exist cloudflared.log del cloudflared.log
echo.
echo   Facilitator screen (project this): http://localhost:8501/?view=facilitator
echo   It shows a QR code and the join link for this network.
echo   If Windows Firewall asks, allow Python on PRIVATE networks.
echo.
start "" "http://localhost:8501/?view=facilitator"
.venv\Scripts\python.exe -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
pause
