# OCI Generative AI hosted deployment

The application is deployed only as an OCI Generative AI Hosted Application. It does not use OCI Citizen.

## Runtime behavior

- The hosted runtime listens on `PORT` supplied by OCI.
- The current configuration uses public inbound networking with `NO_AUTH_CONFIG`; deploy only where that access model is appropriate.
- User-supplied API-signing or security-token credentials are used only for the read-only collection run and are deleted afterwards.
- The hosted application resource principal archives and reads snapshots in `bucket_iam_plotter`.
- OCI GenAI API credentials are supplied from Vault as `OCI_GENAI_API_KEY`.

## Required IAM access

The local developer principal needs permission to push to the selected OCIR repository and manage the hosted application/deployment. The hosted application resource-principal dynamic group needs read access to `bucket_iam_plotter` and read/write object permissions in the bucket compartment. The deployed `oci-iam-plotter-hosted-runtime` policy grants:

```text
Allow dynamic-group oci-iam-plotter-hosted-runtime to read buckets in compartment id <bucket-compartment> where all {target.bucket.name='bucket_iam_plotter'}
Allow dynamic-group oci-iam-plotter-hosted-runtime to manage objects in compartment id <bucket-compartment> where all {target.bucket.name='bucket_iam_plotter'}
```

It also needs access to the configured Vault secret and OCI Generative AI model/project according to your tenancy policy. Resource-principal token updates can take time to propagate after an IAM policy or dynamic-group change.

## Publish a release

```bash
export OCIR_USERNAME='<tenancy-namespace>/<oci-username>'
export OCIR_AUTH_TOKEN='<OCIR auth token>'
CONTAINER_CLI=podman ./deploy/deploy-hosted-application.sh
```

The script builds a Linux AMD64 image, pushes it to OCIR, updates the hosted application environment, adds a deployment artifact, and activates it. OCI limits a deployment to 20 artifacts; the script removes only the oldest inactive artifact when the limit is reached. Use the patch version in `pyproject.toml` as the release tag, and update the in-app release notes in `frontend/src/main.jsx` at the same time.

Runtime settings are defined in [deploy/hosted-runtime-config.json](../deploy/hosted-runtime-config.json). It enables `OCI_IAM_PLOTTER_HOSTED=true`, which selects resource-principal Object Storage authentication. The archive bucket, namespace, and Object Storage region are explicit so the SDK can construct the regional endpoint without relying on runtime metadata discovery.

## Verify a release

```bash
oci generative-ai hosted-deployment get \
  --hosted-deployment-id '<deployment-ocid>' \
  --query 'data.{state:"lifecycle-state",active:"active-artifact".tag}' \
  --output json
```

The deployment is ready when its state is `ACTIVE` and the active tag is the release tag you published.

If an image is already available in OCIR, use `SKIP_IMAGE_BUILD=1 IMAGE_TAG=<release-tag> CONTAINER_CLI=podman ./deploy/deploy-hosted-application.sh`. OCI may briefly return a `Conflict` while an artifact update is completing; wait for the deployment to return to `ACTIVE` before activating the new artifact.
