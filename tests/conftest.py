"""Shared test fixtures for OCI IAM Plotter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oci_iam_plotter.models import Snapshot


@pytest.fixture
def snapshot() -> Snapshot:
    """Load the portable sample IAM snapshot."""
    path = Path(__file__).parents[1] / "examples" / "sample_snapshot.json"
    return Snapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))

