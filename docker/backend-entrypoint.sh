#!/bin/sh
# Start the API, then (unless AUTO_INDEX=0) register every folder listed in
# PHOTO_DIRS (default: /photos) and start an incremental indexing job.
set -e
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
trap 'kill -TERM $API_PID 2>/dev/null; wait $API_PID' TERM INT

if [ "${AUTO_INDEX:-1}" != "0" ]; then
  python - <<'PY' || echo "[pixelindex] auto-index skipped (see above)"
import json, os, sys, time, urllib.request
base = "http://127.0.0.1:8000/api/v1"
def call(method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
for _ in range(120):
    try:
        call("GET", "/system/info"); break
    except Exception:
        time.sleep(1)
dirs = [d for d in os.environ.get("PHOTO_DIRS", "/photos").split(":") if d]
known = {f["path"] for f in call("GET", "/folders") if f["enabled"]}
added = []
for d in dirs:
    if not os.path.isdir(d):
        print(f"[pixelindex] {d} is not mounted — skipping", flush=True); continue
    if not any(e.name != ".gitignore" for e in os.scandir(d)):
        print(f"[pixelindex] {d} is empty — add pictures or set PHOTOS=/path/on/host", flush=True); continue
    if os.path.realpath(d) not in known:
        call("POST", "/folders", {"path": d}); added.append(d)
if added or known:
    call("POST", "/index/start", {"folder_ids": []})
    print(f"[pixelindex] indexing started (new folders: {added or 'none'}) — progress shows in the app", flush=True)
PY
fi
wait $API_PID
