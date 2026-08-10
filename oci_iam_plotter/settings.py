"""Environment-backed runtime settings with safe, documented defaults."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

DEFAULT_PROJECT_OCID = "ocid1.generativeaiproject.oc1.us-chicago-1.amaaaaaafigrwqyaszdh7vv7uymklym7vjid2dac4niv6pxokjd54hve4l7a"
DEFAULT_MODEL_ID = "xai.grok-4"
DEFAULT_OPENAI_BASE_URL = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/openai/v1"


@dataclass(frozen=True)
class Settings:
    """Resolved application settings; credentials are never included in repr output."""

    cache_dir: Path
    genai_project_ocid: str
    genai_model_id: str
    genai_base_url: str
    genai_api_key_file: Path
    oci_config_file: Path
    oci_config_profile: str
    object_storage_bucket: str
    object_storage_namespace: str
    object_storage_enabled: bool
    object_storage_resource_principal: bool

    @classmethod
    def from_env(cls) -> "Settings":
        """Resolve supported environment variables once for an application process."""
        return cls(
            cache_dir=Path(os.getenv("OCI_IAM_PLOTTER_CACHE_DIR", ".iam-plotter-cache")),
            genai_project_ocid=os.getenv("OCI_GENAI_PROJECT_OCID", DEFAULT_PROJECT_OCID),
            genai_model_id=os.getenv("OCI_GENAI_MODEL_ID", DEFAULT_MODEL_ID),
            genai_base_url=os.getenv("OCI_GENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            genai_api_key_file=Path(os.getenv("OCI_GENAI_API_KEY_FILE", ".oci-genai-api-key")),
            oci_config_file=Path(os.getenv("OCI_CONFIG_FILE", "~/.oci/config")).expanduser(),
            oci_config_profile=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT").strip() or "DEFAULT",
            object_storage_bucket=os.getenv("OCI_IAM_PLOTTER_OBJECT_STORAGE_BUCKET", "bucket_iam_plotter").strip(),
            object_storage_namespace=os.getenv("OCI_IAM_PLOTTER_OBJECT_STORAGE_NAMESPACE", "").strip(),
            object_storage_enabled=os.getenv("OCI_IAM_PLOTTER_OBJECT_STORAGE_ENABLED", "true").lower() not in {"0", "false", "no"},
            object_storage_resource_principal=(os.getenv("OCI_IAM_PLOTTER_HOSTED", "").lower() in {"1", "true", "yes"}
                                               or bool(os.getenv("OCI_RESOURCE_PRINCIPAL_VERSION"))),
        )
