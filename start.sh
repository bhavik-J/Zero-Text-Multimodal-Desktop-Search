#!/usr/bin/env bash
# Start PixelIndex (backend + frontend) and open it in your browser.
#
#   ./start.sh                     # start the app
#   ./start.sh ~/Pictures          # …and add + index this folder automatically
#   ./start.sh data/testset        # …e.g. the test library from ./setup.sh --with-testset
#
# Press Ctrl+C to stop everything. Logs: data/logs/
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
VPY="$ROOT/backend/.venv/bin/python"
FOLDER="${1:-}"

[[ -x "$VPY" ]] || { echo "Run ./setup.sh first."; exit 1; }
[[ -d frontend/node_modules ]] || { echo "Run ./setup.sh first."; exit 1; }
mkdir -p data/logs

for port in "$API_PORT" "$UI_PORT"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is already in use (is PixelIndex already running?). Stop it, or run e.g. API_PORT=8001 UI_PORT=5174 ./start.sh"
    exit 1
  fi
done

PIDS=()
cleanup() {
  echo; echo "Stopping PixelIndex…"
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting backend on :$API_PORT  (log: data/logs/backend.log)"
(cd backend && exec "$VPY" -m uvicorn app.main:app --port "$API_PORT" >"$ROOT/data/logs/backend.log" 2>&1) &
PIDS+=($!)

echo "Starting frontend on :$UI_PORT (log: data/logs/frontend.log)"
(cd frontend && VITE_API_PORT="$API_PORT" exec ./node_modules/.bin/vite --port "$UI_PORT" --strictPort >"$ROOT/data/logs/frontend.log" 2>&1) &
PIDS+=($!)

api() { curl -fsS "http://127.0.0.1:$API_PORT/api/v1$1" "${@:2}"; }
for _ in $(seq 90); do
  api /system/info >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$UI_PORT" >/dev/null 2>&1 && break
  sleep 1
done
api /system/info >/dev/null 2>&1 || { echo "Backend did not start — see data/logs/backend.log"; tail -20 data/logs/backend.log; exit 1; }

if [[ -n "$FOLDER" ]]; then
  ABS="$(cd "$FOLDER" 2>/dev/null && pwd)" || { echo "Folder not found: $FOLDER"; exit 1; }
  "$VPY" - "$ABS" "$API_PORT" <<'EOF'
import json, sys, urllib.request, urllib.error
path, port = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:{port}/api/v1"
def call(method, url, body=None):
    req = urllib.request.Request(base + url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)
folders = {f["path"]: f for f in call("GET", "/folders") if f["enabled"]}
if path not in folders:
    call("POST", "/folders", {"path": path})
    print(f"Added folder {path}")
job = call("POST", "/index/start", {"folder_ids": []})
print("Indexing started — watch progress in the app's sidebar (new/changed images only).")
EOF
fi

URL="http://localhost:$UI_PORT"
echo
echo "  PixelIndex is running →  $URL"
echo "  Press Ctrl+C to stop."
if [[ "$(uname -s)" == "Darwin" ]]; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
fi
wait
