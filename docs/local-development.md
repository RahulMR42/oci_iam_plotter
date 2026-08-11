# Local development

## Prerequisites

- Python 3.10 or newer
- Node.js and npm for the React production build
- OCI CLI-style configuration, normally `~/.oci/config`
- OCI SDK read permissions for the IAM data you intend to collect

## Run the portal

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
./start.sh
```

`start.sh` launches the FastAPI/React portal on `http://127.0.0.1:8501` by default. It clears proxy variables unless `OCI_IAM_PLOTTER_USE_PROXY=1` is set.

The first local launch creates a strong password in the owner-only file configured by `OCI_IAM_PLOTTER_PASSWORD_FILE`; the default username is `oci`.

## Build and test

```bash
pytest -q
npm run build
```

The Vite build writes deployable assets to `oci_iam_plotter/static/`. Run it before creating a container image or validating UI changes through the FastAPI server.

The primary navigation highlights Access Map and Reports & Risks. Reports & Risks follows IAM Drift, includes a score-guide popup in Risk Posture, and uses the current snapshot’s active portal-session count beside the release badge. This count is not the collected OCI IAM user count.

## Containers

```bash
docker compose build
docker compose up -d
```

Compose mounts `~/.oci` read-only and stores the working cache and generated local password in the `iam-plotter-data` volume. It publishes only to localhost.

## CLI analysis

The CLI can collect or analyze snapshots without the web portal:

```bash
python -m oci_iam_plotter collect
python -m oci_iam_plotter analyze-user --user-id ocid1.user.oc1..example
python -m oci_iam_plotter find-duplicates
python -m oci_iam_plotter report --output artifacts/iam-report.xlsx
```

CLI commands after `collect` reuse the local snapshot and do not make new OCI Identity requests.
