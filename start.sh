#!/usr/bin/env bash
set -e

# Start FastAPI (port 8001)
uvicorn fastapi_appnew:app --host 0.0.0.0 --port 8001 &
API_PID=$!

# Start Streamlit (port 8501)
streamlit run app_streamlit.py \
  --server.port="${STREAMLIT_SERVER_PORT:-8501}" \
  --server.address=0.0.0.0 &
UI_PID=$!

# Forward signals, wait on children
trap "kill -TERM $API_PID $UI_PID; wait $API_PID; wait $UI_PID" SIGINT SIGTERM
wait -n
exit $?