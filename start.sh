#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
INSTALL_STAMP="$VENV_DIR/.oci-iam-plotter-pyproject.sha256"

# OCI endpoints in this environment are reached directly by default. Set
# OCI_IAM_PLOTTER_USE_PROXY=1 to preserve caller-provided proxy variables.
if [[ "${OCI_IAM_PLOTTER_USE_PROXY:-0}" != "1" ]]; then
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Creating virtual environment in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m oci_iam_plotter.auth

project_hash() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 pyproject.toml | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum pyproject.toml | awk '{print $1}'
  else
    python -c "from hashlib import sha256; from pathlib import Path; print(sha256(Path('pyproject.toml').read_bytes()).hexdigest())"
  fi
}

current_hash="$(project_hash)"
installed_hash=""
if [[ -f "$INSTALL_STAMP" ]]; then
  installed_hash="$(<"$INSTALL_STAMP")"
fi

if [[ "$current_hash" != "$installed_hash" ]] || ! python -c "import fastapi, uvicorn, networkx, oci, openai, openpyxl, PIL, pyvis, reportlab" >/dev/null 2>&1; then
  echo "Installing OCI IAM Plotter and web dependencies"
  python -m pip install -e .
  printf '%s\n' "$current_hash" > "$INSTALL_STAMP"
fi

HOST="${OCI_IAM_PLOTTER_HOST:-127.0.0.1}"
PORT="${OCI_IAM_PLOTTER_PORT:-8501}"

echo "Starting OCI IAM Plotter at http://$HOST:$PORT"
exec uvicorn oci_iam_plotter.api:app \
  --host "$HOST" \
  --port "$PORT" \
  "$@"
