#!/usr/bin/env bash
# macOS/Linux launcher.   ./run_local.sh            this computer only
#                         ./run_local.sh --seminar  same Wi-Fi (participants scan the QR on the facilitator screen)
#                         ./run_local.sh --public   public https link through cloudflared or ngrok
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
[ -f local_config.toml ] || cp local_config.example.toml local_config.toml
[ -f "$HOME/.streamlit/credentials.toml" ] || { mkdir -p "$HOME/.streamlit"; printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"; }
rm -f cloudflared.log
ADDR=localhost
case "$1" in
  --seminar|--classroom) ADDR=0.0.0.0 ;;
  --public)
    if command -v cloudflared >/dev/null; then cloudflared tunnel --no-autoupdate --url http://localhost:8501 > cloudflared.log 2>&1 &
    elif command -v ngrok >/dev/null; then ngrok http 8501 > /dev/null 2>&1 &
    else echo "Install cloudflared or ngrok first."; exit 1; fi ;;
esac
echo "Facilitator screen: http://localhost:8501/?view=facilitator"
exec .venv/bin/python -m streamlit run app.py --server.address "$ADDR" --server.port 8501 --server.headless true
