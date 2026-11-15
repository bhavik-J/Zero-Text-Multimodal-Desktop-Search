#!/usr/bin/env bash
# One-time setup for PixelIndex on macOS or Linux.
#
#   ./setup.sh                 # install everything + download the CLIP model
#   ./setup.sh --with-testset  # …and also build the 3,300-picture test library (~600 MB download)
#
# Safe to run again: every step skips work that is already done.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
WITH_TESTSET=0
[[ "${1:-}" == "--with-testset" ]] && WITH_TESTSET=1

say()  { printf "\n\033[1;35m==>\033[0m \033[1m%s\033[0m\n" "$*"; }
fail() { printf "\n\033[1;31mERROR:\033[0m %s\n" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
OS="$(uname -s)"

brew_install() {  # brew_install <formula> — only on macOS with Homebrew
  if [[ "$OS" == "Darwin" ]] && have brew; then
    say "Installing $1 with Homebrew"
    brew install "$1"
  else
    return 1
  fi
}

# ── 1. Python ≥ 3.10 ─────────────────────────────────────────────────
pick_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$c"; return 0
    fi
  done
  return 1
}
say "Checking Python (3.10 or newer)"
PY="$(pick_python || true)"
if [[ -z "$PY" ]]; then
  brew_install python@3.12 || fail "Python 3.10+ not found. Install it from https://www.python.org/downloads/ (or 'brew install python@3.12') and run ./setup.sh again."
  PY="$(pick_python)" || fail "Python 3.10+ still not found on PATH after installing — open a new Terminal and run ./setup.sh again."
fi
echo "using $($PY --version) at $(command -v "$PY")"

# ── 2. Node.js ≥ 18 ──────────────────────────────────────────────────
say "Checking Node.js (18 or newer)"
if ! have node || ! node -e 'process.exit(+process.versions.node.split(".")[0] >= 18 ? 0 : 1)'; then
  brew_install node || fail "Node.js 18+ not found. Install it from https://nodejs.org/ (or 'brew install node') and run ./setup.sh again."
fi
echo "using node $(node --version)"

# ── 3. Tesseract (text inside images) ────────────────────────────────
say "Checking Tesseract OCR"
if ! have tesseract; then
  if ! brew_install tesseract; then
    if [[ "$OS" == "Linux" ]] && have apt-get; then
      echo "Run:  sudo apt-get install -y tesseract-ocr   (text-in-image search is off until then)"
    else
      echo "Tesseract not found — text-in-image search will be off. Install it later with 'brew install tesseract'."
    fi
  fi
fi
have tesseract && echo "using $(tesseract --version 2>&1 | head -1)"

# ── 4. Backend virtualenv + packages ─────────────────────────────────
say "Installing backend packages (first run takes a few minutes)"
if [[ ! -x backend/.venv/bin/python ]]; then
  "$PY" -m venv backend/.venv
fi
VPY="$ROOT/backend/.venv/bin/python"
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -r backend/requirements.txt

# ── 5. CLIP model weights ────────────────────────────────────────────
say "Downloading the CLIP model (~600 MB, once)"
(cd backend && "$VPY" -m app.embeddings.download --precision fp32 >/dev/null)
echo "model ready in data/models"

# ── 6. Frontend packages ─────────────────────────────────────────────
say "Installing frontend packages"
(cd frontend && npm install --no-audit --no-fund --loglevel=error)

# ── 7. Optional test library ─────────────────────────────────────────
if [[ $WITH_TESTSET == 1 ]]; then
  if [[ -f data/testset/ground_truth.json ]]; then
    say "Test library already in data/testset"
  else
    say "Building the test library (downloads ~540 MB of photos, once)"
    "$VPY" scripts/make_test_dataset.py --out data/testset
  fi
fi

say "Setup complete 🎉"
echo "Start the app with:   ./start.sh"
[[ $WITH_TESTSET == 1 ]] && echo "                 or:   ./start.sh data/testset   (opens with the test pictures loaded)"
