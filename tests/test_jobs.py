"""Tests for web UI background collection orchestration."""

from __future__ import annotations

from time import monotonic, sleep

from oci_iam_plotter.jobs import collection_status, start_collection_job


class _FakeCollector:
    def __init__(self, snapshot) -> None:
        self.snapshot = snapshot

    def collect(self):
        return self.snapshot


def test_background_collection_saves_snapshot(snapshot, tmp_path) -> None:
    assert start_collection_job(tmp_path, lambda: _FakeCollector(snapshot))
    deadline = monotonic() + 2
    while collection_status()["status"] in {"queued", "running"} and monotonic() < deadline:
        sleep(0.01)
    status = collection_status()
    assert status["status"] == "completed"
    assert status["entities"] == len(snapshot.entities)
    assert (tmp_path / "snapshot.json").exists()

