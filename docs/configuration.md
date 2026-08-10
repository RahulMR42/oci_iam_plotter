# Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `OCI_IAM_PLOTTER_CACHE_DIR` | `.iam-plotter-cache` | Local normalized snapshot cache |
| `OCI_IAM_PLOTTER_HOST` | `127.0.0.1` | Local bind address |
| `OCI_IAM_PLOTTER_PORT` | `8501` | Local portal port |
| `OCI_IAM_PLOTTER_USE_PROXY` | `0` | Preserve proxy variables only when set to `1` |
| `OCI_IAM_PLOTTER_USERNAME` | `oci` | Local sign-in username |
| `OCI_IAM_PLOTTER_PASSWORD_FILE` | `.iam-plotter-password` | Owner-only generated local password file |
| `OCI_CONFIG_FILE` | `~/.oci/config` | OCI SDK config for local Object Storage access |
| `OCI_CONFIG_PROFILE` | `DEFAULT` | OCI SDK profile |
| `OCI_IAM_PLOTTER_OBJECT_STORAGE_BUCKET` | `bucket_iam_plotter` | Durable snapshot archive bucket |
| `OCI_IAM_PLOTTER_OBJECT_STORAGE_NAMESPACE` | auto-detected | Object Storage namespace override |
| `OCI_IAM_PLOTTER_OBJECT_STORAGE_ENABLED` | `true` | Disable only for local-only snapshots |
| `OCI_IAM_PLOTTER_HOSTED` | unset | Select OCI resource-principal Object Storage auth |
| `OCI_GENAI_PROJECT_OCID` | configured project | OCI Generative AI project |
| `OCI_GENAI_MODEL_ID` | `xai.grok-4` | OCI OpenAI-compatible model |
| `OCI_GENAI_BASE_URL` | Chicago endpoint | OCI Responses API base URL |
| `OCI_GENAI_API_KEY` | unset | Preferred in-memory GenAI API key |
| `OPENAI_API_KEY` | unset | SDK-compatible fallback API key |
| `OCI_GENAI_API_KEY_FILE` | `.oci-genai-api-key` | Permission-restricted local key file |

Copy [.env.example](../.env.example) as a configuration reference. The local launcher does not automatically load `.env`.
