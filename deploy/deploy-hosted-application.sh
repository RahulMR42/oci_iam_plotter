#!/usr/bin/env bash
# Build locally, push to OCIR, then create or update an OCI GenAI hosted app.
# No DevOps pipeline or application ingress authentication is used.
set -euo pipefail

COMPARTMENT_ID="ocid1.compartment.oc1..aaaaaaaacjttophgihjlb2ujt5pj4nfikhqcplbtrgi4zcqjmjillrfs4mya"
VAULT_ID="ocid1.vault.oc1.us-chicago-1.ijuylwhcaad5c.abxxeljrp25riyj5ypfu4kuhdl3gbmlfgejtny57kjpzau4xivl6gkhl4zvq"
REGION="${OCI_REGION:-us-chicago-1}"
OCIR_HOST="${OCIR_HOST:-ord.ocir.io}"
REPOSITORY="${OCIR_REPOSITORY:-iamplotter}"
APP_NAME="${HOSTED_APP_NAME:-oci-iam-plotter}"
DEPLOYMENT_NAME="${HOSTED_DEPLOYMENT_NAME:-oci-iam-plotter}"
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
CONTAINER_CLI="${CONTAINER_CLI:-docker}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

command -v oci >/dev/null || { echo 'OCI CLI is required.' >&2; exit 1; }
command -v "$CONTAINER_CLI" >/dev/null || { echo "Container CLI is required: $CONTAINER_CLI" >&2; exit 1; }

NAMESPACE="${OCI_NAMESPACE:-$(oci os ns get --query data --raw-output)}"
IMAGE="${OCIR_HOST}/${NAMESPACE}/${REPOSITORY}:${TAG}"

# Set OCIR_USERNAME and OCIR_AUTH_TOKEN if Docker is not already logged in.
if [[ -n "${OCIR_USERNAME:-}" || -n "${OCIR_AUTH_TOKEN:-}" ]]; then
  [[ -n "${OCIR_USERNAME:-}" && -n "${OCIR_AUTH_TOKEN:-}" ]] || { echo 'Set both OCIR_USERNAME and OCIR_AUTH_TOKEN.' >&2; exit 1; }
  printf '%s' "$OCIR_AUTH_TOKEN" | "$CONTAINER_CLI" login "$OCIR_HOST" --username "$OCIR_USERNAME" --password-stdin
fi

if [[ "${SKIP_IMAGE_BUILD:-0}" != "1" ]]; then
  "$CONTAINER_CLI" build --platform linux/amd64 --tag "$IMAGE" "$ROOT"
  "$CONTAINER_CLI" push "$IMAGE"
fi

python3 - "$ROOT/deploy/hosted-runtime-config.json" "$TMP/env.json" <<'PY'
import json, sys
config, output = sys.argv[1:]
payload = json.load(open(config, encoding='utf-8'))
env = [{"name": key, "type": "PLAINTEXT", "value": str(value)}
       for key, value in sorted(payload["environment"].items())]
env.extend({"name": key, "type": "VAULT", "value": value}
           for key, value in sorted(payload["secretEnvironment"].items()))
json.dump(env, open(output, 'w', encoding='utf-8'))
PY
printf '%s' '{"inboundAuthConfigType":"NO_AUTH_CONFIG"}' > "$TMP/inbound-auth.json"

APP_ID="$(oci generative-ai hosted-application-collection list-hosted-applications \
  --compartment-id "$COMPARTMENT_ID" --display-name "$APP_NAME" --all \
  --query 'data.items[?"lifecycle-state"!=`DELETED`].id | [0]' --raw-output)"
if [[ -z "$APP_ID" || "$APP_ID" == "null" ]]; then
  oci generative-ai hosted-application create --compartment-id "$COMPARTMENT_ID" \
    --display-name "$APP_NAME" --description 'Read-only OCI IAM collection and analysis' \
    --scaling-config '{"scalingType":"CPU","minReplica":1,"maxReplica":1,"targetCpuThreshold":70}' --inbound-auth-config "file://$TMP/inbound-auth.json" \
    --environment-variables "file://$TMP/env.json" --wait-for-state SUCCEEDED --wait-for-state FAILED --max-wait-seconds 1200 >/dev/null
  APP_ID="$(oci generative-ai hosted-application-collection list-hosted-applications --compartment-id "$COMPARTMENT_ID" --display-name "$APP_NAME" --all --query 'data.items[?"lifecycle-state"!=`DELETED`].id | [0]' --raw-output)"
else
  oci generative-ai hosted-application update --hosted-application-id "$APP_ID" --display-name "$APP_NAME" \
    --description 'Read-only OCI IAM collection and analysis' --scaling-config '{"scalingType":"CPU","minReplica":1,"maxReplica":1,"targetCpuThreshold":70}' \
    --inbound-auth-config "file://$TMP/inbound-auth.json" --environment-variables "file://$TMP/env.json" --force \
    --wait-for-state SUCCEEDED --wait-for-state FAILED --max-wait-seconds 1200 >/dev/null
fi

# OCI can replace the requested display name with a generated one, so use the
# sole non-deleted deployment associated with this hosted application.
DEPLOYMENT_ID="$(oci generative-ai hosted-deployment-collection list-hosted-deployments --compartment-id "$COMPARTMENT_ID" --application-id "$APP_ID" --all --query 'data.items[?"lifecycle-state"!=`DELETED`].id | [0]' --raw-output)"
URI="${OCIR_HOST}/${NAMESPACE}/${REPOSITORY}"
if [[ -z "$DEPLOYMENT_ID" || "$DEPLOYMENT_ID" == "null" ]]; then
  oci generative-ai hosted-deployment create-hosted-deployment-single-docker-artifact --compartment-id "$COMPARTMENT_ID" \
    --hosted-application-id "$APP_ID" --display-name "$DEPLOYMENT_NAME" --active-artifact-container-uri "$URI" \
    --active-artifact-tag "$TAG" --active-artifact-status ACTIVE --wait-for-state SUCCEEDED --wait-for-state FAILED --max-wait-seconds 1200
else
  # OCI hosted deployments retain at most 20 artifacts. Keep the active one
  # and remove only the oldest inactive artifact before adding a release.
  oci generative-ai hosted-deployment get --hosted-deployment-id "$DEPLOYMENT_ID" --output json > "$TMP/deployment.json"
  read -r ARTIFACT_COUNT OLDEST_INACTIVE_ID < <(python3 - "$TMP/deployment.json" <<'PY'
import json, sys
items = json.load(open(sys.argv[1], encoding="utf-8"))["data"].get("artifacts", [])
inactive = [item for item in items if item.get("status") == "INACTIVE"]
inactive.sort(key=lambda item: item.get("time-created", ""))
print(len(items), inactive[0]["id"] if inactive else "")
PY
)
  if [[ "$ARTIFACT_COUNT" -ge 20 && -n "$OLDEST_INACTIVE_ID" ]]; then
    oci generative-ai hosted-deployment delete-hosted-deployment-artifact \
      --hosted-deployment-id "$DEPLOYMENT_ID" --artifact-id "$OLDEST_INACTIVE_ID" --force \
      --wait-for-state SUCCEEDED --wait-for-state FAILED --max-wait-seconds 1200 || true
  fi
  oci generative-ai hosted-deployment add-artifact-create-single-docker-artifact-details --hosted-deployment-id "$DEPLOYMENT_ID" \
    --artifact-container-uri "$URI" --artifact-tag "$TAG" --wait-for-state SUCCEEDED --wait-for-state FAILED --max-wait-seconds 1200 || true
  # Adding an artifact does not make it live. Convert OCI's response shape
  # (kebab keys) to the update API's camel-case activeArtifact payload.
  oci generative-ai hosted-deployment get --hosted-deployment-id "$DEPLOYMENT_ID" --output json > "$TMP/deployment.json"
  python3 - "$TMP/deployment.json" "$TMP/active-artifact.json" "$TAG" <<'PY'
import json, sys
deployment, output, tag = sys.argv[1:]
items = json.load(open(deployment, encoding="utf-8"))["data"].get("artifacts", [])
artifact = next((item for item in items if item.get("tag") == tag), None)
if not artifact:
    raise SystemExit(f"New artifact {tag} was not returned by OCI")
mapping = {"artifact-type": "artifactType", "container-uri": "containerUri",
           "hosted-deployment-id": "hostedDeploymentId", "id": "id",
           "is-vulnerability-scan-required": "isVulnerabilityScanRequired",
           "status": "status", "tag": "tag", "time-created": "timeCreated"}
json.dump({target: artifact[source] for source, target in mapping.items() if source in artifact},
          open(output, "w", encoding="utf-8"))
PY
  oci generative-ai hosted-deployment update --hosted-deployment-id "$DEPLOYMENT_ID" \
    --active-artifact "file://$TMP/active-artifact.json" --force \
    --wait-for-state SUCCEEDED --wait-for-state FAILED --max-wait-seconds 1200
fi

echo "Hosted application: $APP_ID"
echo "Image: $IMAGE"
echo "Vault configured: $VAULT_ID"
