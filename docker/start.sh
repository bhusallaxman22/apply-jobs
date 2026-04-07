#!/usr/bin/env bash
set -euo pipefail

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}

trap cleanup EXIT INT TERM

start_browser_desktop() {
  export DISPLAY="${DISPLAY:-:99}"
  local screen_geometry="${BROWSER_DESKTOP_GEOMETRY:-1600x900x24}"
  local vnc_port="${BROWSER_DESKTOP_VNC_PORT:-5900}"
  local web_port="${BROWSER_DESKTOP_PORT:-7900}"
  local password_file="/tmp/job-agent-vnc.passwd"

  Xvfb "$DISPLAY" -screen 0 "$screen_geometry" -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
  PIDS+=("$!")
  sleep 1

  fluxbox >/tmp/fluxbox.log 2>&1 &
  PIDS+=("$!")

  local x11vnc_args=(-display "$DISPLAY" -shared -forever -rfbport "$vnc_port")
  if [[ -n "${BROWSER_DESKTOP_PASSWORD:-}" ]]; then
    x11vnc -storepasswd "$BROWSER_DESKTOP_PASSWORD" "$password_file" >/dev/null 2>&1
    x11vnc_args+=(-rfbauth "$password_file")
  else
    x11vnc_args+=(-nopw)
  fi

  x11vnc "${x11vnc_args[@]}" >/tmp/x11vnc.log 2>&1 &
  PIDS+=("$!")

  websockify --web=/usr/share/novnc/ "$web_port" "localhost:$vnc_port" >/tmp/websockify.log 2>&1 &
  PIDS+=("$!")
}

if [[ "${BROWSER_DESKTOP_ENABLED:-false}" == "true" ]]; then
  start_browser_desktop
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8095
