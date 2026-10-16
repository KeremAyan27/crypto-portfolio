#!/usr/bin/env sh
# Runs the FastAPI backend on an internal port and Streamlit on the public $PORT.
set -e
API_PORT="${API_PORT:-8001}"
UI_PORT="${PORT:-8501}"
export API_URL="${API_URL:-http://127.0.0.1:${API_PORT}}"

uvicorn app.api.main:app --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT INT TERM

exec streamlit run app/ui/main.py \
  --server.port "$UI_PORT" \
  --server.address 0.0.0.0 \
  --server.headless true \
  --browser.gatherUsageStats false
