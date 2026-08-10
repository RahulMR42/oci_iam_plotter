#!/usr/bin/env sh
set -eu

# OCI endpoints are contacted directly unless proxy use is explicitly enabled.
if [ "${OCI_IAM_PLOTTER_USE_PROXY:-0}" != "1" ]; then
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true
fi

mkdir -p "${OCI_IAM_PLOTTER_CACHE_DIR:-/app/data/cache}"

app_port="${PORT:-${OCI_IAM_PLOTTER_PORT:-8501}}"

exec uvicorn oci_iam_plotter.api:app \
  --host "${OCI_IAM_PLOTTER_HOST:-0.0.0.0}" \
  --port "${app_port}" \
  "$@"
