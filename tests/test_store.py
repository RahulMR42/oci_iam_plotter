"""Tests for portable, stable snapshot persistence."""

from dataclasses import replace

from oci_iam_plotter.models import Relationship
from oci_iam_plotter.store import SnapshotStore


class _Archive:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def put(self, snapshot, payload):
        self.calls.append((snapshot, payload))
        if self.error:
            raise self.error
        return "tenancies/example/2026/snapshot.json"


def test_semantic_hash_ignores_collection_timestamp(snapshot, tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    store.save(snapshot)
    first_hash = store.load().source_hash
    store.save(replace(snapshot, collected_at="later"))
    assert store.load().source_hash == first_hash


def test_relationships_and_warnings_round_trip(snapshot, tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    snapshot.relationships = [Relationship("user-1", "group-1", "MEMBER_OF", "direct")]
    snapshot.warnings = ["one optional domain was unavailable"]
    store.save(snapshot)
    loaded = store.load()
    assert loaded.relationships == snapshot.relationships
    assert loaded.warnings == snapshot.warnings


def test_history_keeps_five_snapshots_per_tenancy(snapshot, tmp_path) -> None:
    store = SnapshotStore(tmp_path, max_history=5)
    for index in range(7):
        store.save(replace(snapshot, collected_at=f"2026-08-0{index + 1}T10:00:00+00:00",
                           warnings=[f"collection-{index}"]))
    history = store.list_history()
    assert len(history) == 5
    assert history[0].collected_at == "2026-08-07T10:00:00+00:00"
    assert history[-1].collected_at == "2026-08-03T10:00:00+00:00"
    assert store.load(history[0].path).warnings == ["collection-6"]


def test_object_archive_is_written_without_expanding_local_history(snapshot, tmp_path) -> None:
    archive = _Archive()
    store = SnapshotStore(tmp_path, object_archive=archive)
    store.save(snapshot)
    assert len(archive.calls) == 1
    assert store.last_object_name == "tenancies/example/2026/snapshot.json"
    assert store.last_archive_error is None


def test_object_archive_failure_keeps_the_local_snapshot(snapshot, tmp_path) -> None:
    store = SnapshotStore(tmp_path, object_archive=_Archive(RuntimeError("forbidden")))
    store.save(snapshot)
    assert store.load().tenancy_id == snapshot.tenancy_id
    assert store.last_archive_error == "forbidden"
