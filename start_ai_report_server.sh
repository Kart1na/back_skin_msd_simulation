#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

HOST="${AI_REPORT_HOST:-0.0.0.0}"
PORT="${AI_REPORT_PORT:-9090}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Starting LSCURE AI report server..."
echo "Host: ${HOST}"
echo "Port: ${PORT}"
echo
echo "Local report center: http://127.0.0.1:${PORT}/reports"
echo "Robot API: http://<linux-ip>:${PORT}/ai-report/force"
echo

"${PYTHON_BIN}" back_skin_msd_simulation/ai_report_server.py --host "${HOST}" --port "${PORT}"
