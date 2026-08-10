# syntax=docker/dockerfile:1.7

FROM ghcr.io/jumpserver/python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/plotter \
    OCI_IAM_PLOTTER_CACHE_DIR=/app/data/cache \
    OCI_IAM_PLOTTER_HOST=0.0.0.0 \
    OCI_IAM_PLOTTER_PORT=8501 \
    OCI_CONFIG_FILE=/home/plotter/.oci/config \
    OCI_CONFIG_PROFILE=DEFAULT

WORKDIR /app

# Install application dependencies before copying frequently changed sources.
COPY pyproject.toml README.md ./
COPY oci_iam_plotter ./oci_iam_plotter
RUN python -m pip install --no-cache-dir .

COPY .streamlit ./.streamlit
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN groupadd --gid 10001 plotter \
    && useradd --uid 10001 --gid plotter --no-create-home --home-dir /home/plotter plotter \
    && mkdir -p /app/data/cache /home/plotter/.oci \
    && chown -R plotter:plotter /app/data /home/plotter \
    && chmod 0755 /app/docker-entrypoint.sh

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.getenv('PORT', os.getenv('OCI_IAM_PLOTTER_PORT','8501')); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3).read()"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
