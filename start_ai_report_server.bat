@echo off
setlocal
cd /d "%~dp0"

set "BUNDLED_PY=C:\Users\lscure\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" back_skin_msd_simulation\ai_report_server.py --host 127.0.0.1 --port 9090
) else (
  py back_skin_msd_simulation\ai_report_server.py --host 127.0.0.1 --port 9090 || python back_skin_msd_simulation\ai_report_server.py --host 127.0.0.1 --port 9090
)

endlocal
