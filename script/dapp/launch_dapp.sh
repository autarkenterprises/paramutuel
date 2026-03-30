#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${PORT:-8080}"
AUTO_OPEN=1

usage() {
  cat <<'EOF'
Usage: ./script/dapp/launch_dapp.sh [--port <PORT>] [--no-open]

Builds Foundry artifacts, starts a local HTTP server, and opens the dApp URL.

Options:
  --port <PORT>  Serve on this port (default: 8080 or $PORT).
  --no-open      Do not auto-open browser.
  -h, --help     Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="${2:-}"
      if [[ -z "$PORT" ]]; then
        echo "error: --port requires a value" >&2
        exit 2
      fi
      shift 2
      ;;
    --no-open)
      AUTO_OPEN=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v forge >/dev/null 2>&1; then
  echo "error: forge is required (https://book.getfoundry.sh/getting-started/installation)" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required to serve the dApp" >&2
  exit 1
fi

cd "$ROOT_DIR"
echo "==> Building contracts (ABI artifacts)..."
forge build -q

URL="http://127.0.0.1:${PORT}/dapp/"
LOG_PATH="/tmp/paramutuel-dapp-${PORT}.log"

existing_pid=""
if command -v lsof >/dev/null 2>&1; then
  existing_pid="$(lsof -ti "tcp:${PORT}" 2>/dev/null | head -n 1 || true)"
fi

if [[ -n "$existing_pid" ]]; then
  echo "==> Reusing existing process on port ${PORT} (pid ${existing_pid})"
else
  echo "==> Starting local server on port ${PORT}..."
  python3 -m http.server "$PORT" >"$LOG_PATH" 2>&1 &
  server_pid=$!
  sleep 1
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "error: failed to start server on port ${PORT}. Check ${LOG_PATH}" >&2
    exit 1
  fi
  echo "==> Server started (pid ${server_pid}); logs: ${LOG_PATH}"
fi

if [[ "$AUTO_OPEN" -eq 1 ]]; then
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  elif command -v wslview >/dev/null 2>&1; then
    wslview "$URL" >/dev/null 2>&1 || true
  else
    echo "==> No browser opener found; open manually: ${URL}"
  fi
fi

echo "==> dApp URL: ${URL}"
