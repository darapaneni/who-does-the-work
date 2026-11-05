@echo off
REM Seminar over the internet: a temporary public https link (works on any phone network, no firewall changes).
REM Uses Cloudflare's free quick tunnel (cloudflared) if installed, otherwise ngrok.
REM   cloudflared: winget install --id Cloudflare.cloudflared
REM   ngrok:       https://ngrok.com/download (then: ngrok config add-authtoken <token>)
cd /d "%~dp0"
call _setup.bat || exit /b 1
if exist cloudflared.log del cloudflared.log
where cloudflared >nul 2>nul
if %errorlevel%==0 (
  echo Starting a Cloudflare quick tunnel ...
  start "Public link (close to stop)" /min cmd /c "cloudflared tunnel --no-autoupdate --url http://localhost:8501 > cloudflared.log 2>&1"
  goto run
)
where ngrok >nul 2>nul
if %errorlevel%==0 (
  echo Starting an ngrok tunnel ...
  start "Public link (close to stop)" /min ngrok http 8501
  goto run
)
echo Neither cloudflared nor ngrok was found. Install one of them (see the top of this file),
echo or use run_seminar.bat on the same Wi-Fi.
pause
exit /b 1
:run
echo.
echo   Facilitator screen (project this): http://localhost:8501/?view=facilitator
echo   The public link and its QR code appear there after about 10 seconds (press R to refresh).
echo   Close the "Public link" window after the seminar to switch the link off.
echo.
start "" "http://localhost:8501/?view=facilitator"
.venv\Scripts\python.exe -m streamlit run app.py --server.address localhost --server.port 8501 --server.headless true
pause
