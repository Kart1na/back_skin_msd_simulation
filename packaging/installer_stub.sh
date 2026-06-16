#!/usr/bin/env bash
set -euo pipefail

APP_NAME="LSCURE AI Report Server"
APP_ID="lscure-ai-report-server"
INSTALL_DIR="${LSCURE_INSTALL_DIR:-$HOME/.local/share/${APP_ID}}"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
RUNNER="$BIN_DIR/${APP_ID}"
DESKTOP_FILE="$DESKTOP_DIR/${APP_ID}.desktop"

usage() {
  cat <<USAGE
${APP_NAME} installer

Usage:
  ./lscure-ai-report-server-ubuntu16.run
  ./lscure-ai-report-server-ubuntu16.run --uninstall

Optional:
  LSCURE_INSTALL_DIR=/custom/path ./lscure-ai-report-server-ubuntu16.run
USAGE
}

payload_line() {
  awk '/^__LSCURE_PAYLOAD_BELOW__$/ { print NR + 1; exit 0; }' "$0"
}

uninstall_app() {
  rm -f "$RUNNER" "$DESKTOP_FILE"
  rm -rf "$INSTALL_DIR"
  echo "${APP_NAME} has been uninstalled."
}

install_app() {
  local line
  line="$(payload_line)"
  if [ -z "$line" ]; then
    echo "Installer payload is missing." >&2
    exit 1
  fi

  mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"
  tail -n +"$line" "$0" | tar -xz -C "$INSTALL_DIR" --strip-components=1

  cat > "$RUNNER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$INSTALL_DIR"
exec ./start_server.sh "\$@"
EOF
  chmod +x "$RUNNER"

  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=LSCURE AI Report Server
Comment=Start local AI massage report service
Exec=$RUNNER
Terminal=true
Categories=Utility;
EOF

  echo
  echo "${APP_NAME} installed successfully."
  echo "Install directory: $INSTALL_DIR"
  echo
  echo "Start it with:"
  echo "  $RUNNER"
  echo
  echo "Then open:"
  echo "  http://127.0.0.1:9090/reports"
  echo
}

case "${1:-}" in
  --help|-h)
    usage
    ;;
  --uninstall)
    uninstall_app
    ;;
  "")
    install_app
    ;;
  *)
    echo "Unknown option: $1" >&2
    usage >&2
    exit 2
    ;;
esac

exit 0
__LSCURE_PAYLOAD_BELOW__
