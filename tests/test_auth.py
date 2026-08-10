"""Tests for generated local authentication credentials."""

import stat

from oci_iam_plotter.auth import credentials_match, local_credentials


def test_generated_password_is_strong_persistent_and_owner_only(monkeypatch, tmp_path) -> None:
    password_file = tmp_path / "local-password"
    monkeypatch.delenv("OCI_IAM_PLOTTER_PASSWORD", raising=False)
    monkeypatch.setenv("OCI_IAM_PLOTTER_PASSWORD_FILE", str(password_file))
    monkeypatch.delenv("OCI_IAM_PLOTTER_USERNAME", raising=False)
    first = local_credentials()
    second = local_credentials()
    assert first.username == "oci"
    assert first.generated is True
    assert second.password == first.password
    assert len(first.password) >= 24
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600
    assert credentials_match("oci", first.password)
    assert not credentials_match("oci", "incorrect-password")


def test_configured_credentials_override_defaults(monkeypatch) -> None:
    monkeypatch.setenv("OCI_IAM_PLOTTER_USERNAME", "auditor")
    monkeypatch.setenv("OCI_IAM_PLOTTER_PASSWORD", "configured-strong-password")
    credentials = local_credentials()
    assert credentials.username == "auditor"
    assert credentials.password == "configured-strong-password"
    assert credentials.password_file is None
