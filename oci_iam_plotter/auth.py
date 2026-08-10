"""Minimal local-only authentication for the Streamlit analysis UI."""

from __future__ import annotations

import hmac
import base64
import os
from pathlib import Path
import secrets
from typing import NamedTuple
from functools import lru_cache


class LocalCredentials(NamedTuple):
    """Resolved local username, password, and whether the password was generated."""

    username: str
    password: str
    generated: bool
    password_file: Path | None


@lru_cache(maxsize=1)
def _vault_password(secret_id: str) -> str:
    """Read the current password directly from OCI Vault as a resource principal."""
    import oci

    signer = oci.auth.signers.get_resource_principals_signer()
    parts = secret_id.split(".")
    if len(parts) < 4 or not parts[3]:
        raise RuntimeError("The OCI Vault secret OCID does not contain a region")
    client = oci.secrets.SecretsClient(config={"region": parts[3]}, signer=signer)
    bundle = client.get_secret_bundle(secret_id=secret_id, stage="CURRENT").data
    encoded = bundle.secret_bundle_content.content
    return base64.b64decode(encoded).decode("utf-8").strip()


def local_credentials() -> LocalCredentials:
    """Resolve configured credentials or create a strong owner-readable password."""
    username = os.getenv("OCI_IAM_PLOTTER_USERNAME", "oci").strip() or "oci"
    secret_id = os.getenv("OCI_IAM_PLOTTER_PASSWORD_SECRET_ID", "").strip()
    if secret_id:
        try:
            password = _vault_password(secret_id)
        except Exception:
            # Some managed runtimes inject Vault values but don't expose a
            # resource-principal signer to the application container.
            password = ""
        if password:
            if len(password) < 16:
                raise RuntimeError("The OCI Vault app password must contain at least 16 characters")
            return LocalCredentials(username, password, False, None)
    configured = (
        os.getenv("OCI_IAM_PLOTTER_PASSWORD_V2", "")
        or os.getenv("OCI_IAM_PLOTTER_PASSWORD", "")
    ).strip()
    if configured:
        if configured.startswith("ocid1.vaultsecret."):
            raise RuntimeError("The OCI Vault password reference could not be resolved")
        if secret_id:
            try:
                decoded = base64.b64decode(configured, validate=True).decode("utf-8").strip()
            except (ValueError, UnicodeDecodeError):
                decoded = ""
            if len(decoded) >= 16:
                configured = decoded
        return LocalCredentials(username, configured, False, None)
    path = Path(os.getenv("OCI_IAM_PLOTTER_PASSWORD_FILE", ".iam-plotter-password")).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = False
    if not path.exists():
        password = secrets.token_urlsafe(24)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(password + "\n")
            generated = True
        except FileExistsError:
            pass
    path.chmod(0o600)
    password = path.read_text(encoding="utf-8").strip()
    if len(password) < 16:
        raise RuntimeError(f"Local password in {path} must contain at least 16 characters")
    return LocalCredentials(username, password, generated, path)


def credentials_match(username: str, password: str) -> bool:
    """Compare submitted local credentials using constant-time comparisons."""
    expected = local_credentials()
    return hmac.compare_digest(username, expected.username) and hmac.compare_digest(password, expected.password)


def main() -> None:
    """Print first-run local login guidance for the startup script."""
    credentials = local_credentials()
    print(f"Local login username: {credentials.username}")
    if credentials.generated:
        print("Generated a strong local login password.")
        print(f"Password stored with owner-only permissions at: {credentials.password_file}")
    elif credentials.password_file:
        print(f"Local login password file: {credentials.password_file}")
    else:
        print("Local login password: supplied through OCI_IAM_PLOTTER_PASSWORD")


if __name__ == "__main__":
    main()
