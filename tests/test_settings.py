"""Tests for documented environment-backed settings."""

from pathlib import Path

from oci_iam_plotter.settings import Settings


def test_settings_resolve_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OCI_IAM_PLOTTER_CACHE_DIR", "alternate-cache")
    monkeypatch.setenv("OCI_GENAI_MODEL_ID", "openai.example-model")
    settings = Settings.from_env()
    assert settings.cache_dir == Path("alternate-cache")
    assert settings.genai_model_id == "openai.example-model"
