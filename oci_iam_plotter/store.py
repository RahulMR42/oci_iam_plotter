"""Atomic JSON snapshot persistence and content-hash support."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from dataclasses import dataclass

from .models import Snapshot
from .object_store import ObjectSnapshotArchive


@dataclass(frozen=True)
class SnapshotRecord:
    """Metadata for one selectable timestamped snapshot."""

    path: Path
    tenancy_id: str
    collected_at: str
    source_hash: str | None


class SnapshotStore:
    """Stores one portable IAM snapshot under a local cache directory."""

    def __init__(self, cache_dir: Path, max_history: int = 5,
                 object_archive: ObjectSnapshotArchive | None = None) -> None:
        self.cache_dir = cache_dir
        self.path = cache_dir / "snapshot.json"
        self.history_dir = cache_dir / "snapshots"
        self.max_history = max_history
        self.object_archive = object_archive
        self.last_archive_error: str | None = None
        self.last_object_name: str | None = None

    def save(self, snapshot: Snapshot, upload_to_object_storage: bool = True) -> Path:
        """Write a snapshot atomically and return its stable path."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = snapshot.to_dict()
        # Collection time changes on every pull, so hash only IAM content. This
        # allows callers to identify no-op refreshes without querying again.
        semantic = {key: value for key, value in payload.items() if key not in {"collected_at", "source_hash"}}
        payload["source_hash"] = self.content_hash(semantic)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
        self._archive(payload)
        self.last_archive_error = None
        self.last_object_name = None
        if upload_to_object_storage and self.object_archive:
            try:
                self.last_object_name = self.object_archive.put(Snapshot.from_dict(payload), payload)
            except Exception as exc:
                # A local snapshot remains valuable even if an operator has not
                # granted Object Storage permissions yet.
                self.last_archive_error = str(exc)
        return self.path

    def load(self, path: Path | None = None) -> Snapshot:
        """Load the latest snapshot, raising FileNotFoundError if absent."""
        selected = path or self.path
        return Snapshot.from_dict(json.loads(selected.read_text(encoding="utf-8")))

    def list_history(self) -> list[SnapshotRecord]:
        """List retained snapshots newest first, including a legacy latest file."""
        records: list[SnapshotRecord] = []
        for path in self.history_dir.glob("*/*.json") if self.history_dir.exists() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                records.append(SnapshotRecord(path, data["tenancy_id"], data["collected_at"], data.get("source_hash")))
            except (OSError, KeyError, json.JSONDecodeError):
                continue
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                key = (data["tenancy_id"], data["collected_at"], data.get("source_hash"))
                if not any((item.tenancy_id, item.collected_at, item.source_hash) == key for item in records):
                    records.append(SnapshotRecord(self.path, *key))
            except (OSError, KeyError, json.JSONDecodeError):
                pass
        return sorted(records, key=lambda item: item.collected_at, reverse=True)

    def _archive(self, payload: dict) -> None:
        """Store and prune timestamped snapshots independently for each tenancy."""
        safe_tenancy = re.sub(r"[^A-Za-z0-9._-]", "_", payload["tenancy_id"])
        tenancy_dir = self.history_dir / safe_tenancy
        tenancy_dir.mkdir(parents=True, exist_ok=True)
        timestamp = re.sub(r"[^0-9]", "", payload["collected_at"])[:20]
        archive = tenancy_dir / f"{timestamp}-{payload['source_hash'][:12]}.json"
        tmp = archive.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(archive)
        retained = sorted(tenancy_dir.glob("*.json"), reverse=True)
        for old in retained[self.max_history:]:
            old.unlink()

    @staticmethod
    def content_hash(payload: object) -> str:
        """Return a stable SHA-256 hash for serializable content."""
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()
