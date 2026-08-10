from pathlib import Path

import oci

from oci_iam_plotter.collector import OCICollector


def test_ephemeral_profile_rewrites_local_key_path_before_oci_load(monkeypatch):
    original_from_file = oci.config.from_file
    observed = {}

    def load_config(*, file_location, profile_name):
        config = original_from_file(file_location=file_location, profile_name=profile_name)
        observed["key_file"] = config["key_file"]
        return config

    monkeypatch.setattr(oci.config, "from_file", load_config)
    monkeypatch.setattr(oci.identity, "IdentityClient", lambda config, **_kwargs: object())
    monkeypatch.setattr(oci.signer, "load_private_key_from_file", lambda _path: object())
    monkeypatch.setattr(oci.auth.signers, "SecurityTokenSigner", lambda _token, _key: object())

    collector = OCICollector.from_ephemeral_profile(
        """[DEFAULT]
user=ocid1.user.oc1..example
fingerprint=00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff
tenancy=ocid1.tenancy.oc1..example
region=us-chicago-1
key_file=/home/local/.oci/private.pem
""",
        "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
    )

    key_path = Path(observed["key_file"])
    assert key_path.name == "oci_api_key.pem"
    assert key_path.exists()
    assert collector.config["key_file"] == str(key_path)
    collector.close()
    assert not key_path.exists()


def test_ephemeral_security_token_profile_rewrites_token_and_key_paths(monkeypatch):
    original_from_file = oci.config.from_file
    observed = {}

    def load_config(*, file_location, profile_name):
        config = original_from_file(file_location=file_location, profile_name=profile_name)
        observed.update(config)
        return config

    monkeypatch.setattr(oci.config, "from_file", load_config)
    monkeypatch.setattr(oci.identity, "IdentityClient", lambda config, **_kwargs: object())
    monkeypatch.setattr(oci.signer, "load_private_key_from_file", lambda _path: object())
    monkeypatch.setattr(oci.auth.signers, "SecurityTokenSigner", lambda _token, _key: object())
    collector = OCICollector.from_ephemeral_profile(
        """[DEFAULT]
tenancy=ocid1.tenancy.oc1..example
region=us-chicago-1
key_file=/home/local/.oci/private.pem
security_token_file=/home/local/.oci/token
""",
        "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
        security_token_text="security-token-content", use_security_token=True,
    )
    key_path, token_path = Path(observed["key_file"]), Path(observed["security_token_file"])
    assert key_path.name == "oci_api_key.pem"
    assert token_path.name == "security_token"
    assert token_path.read_text(encoding="utf-8") == "security-token-content"
    collector.close()
    assert not key_path.exists() and not token_path.exists()
