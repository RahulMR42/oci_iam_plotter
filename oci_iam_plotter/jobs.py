"""Single-worker background collection orchestration for the local web UI."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from .collector import OCICollector
from .store import SnapshotStore

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="oci-iam-collector")
_LOCK = Lock()
_STATE: dict[str, Any] = {
    "status": "idle", "started_at": None, "finished_at": None,
    "message": "Ready to collect", "error": None, "snapshot_path": None,
    "entities": 0, "memberships": 0, "relationships": 0, "statements": 0,
    "logs": [],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collection_status() -> dict[str, Any]:
    """Return a copy of the current background collection state."""
    with _LOCK:
        return dict(_STATE)


def _log(message: str, level: str = "info") -> None:
    """Append a credential-safe collection event, retaining only recent runs."""
    with _LOCK:
        events = _STATE.setdefault("logs", [])
        events.append({"time": _now(), "level": level, "message": message})
        del events[:-240]


def collection_logs() -> list[dict[str, str]]:
    """Return the current in-memory collection event stream."""
    with _LOCK:
        return list(_STATE.get("logs", []))


def _collect(cache_dir: Path, collector_factory: Callable[[], OCICollector], store: SnapshotStore | None = None) -> None:
    with _LOCK:
        _STATE.update(status="running", started_at=_now(), finished_at=None,
                      message="Querying OCI IAM through the selected config profile", error=None)
    _log("Collection worker started; no OCI credentials or signer details are logged.")
    try:
        collector = collector_factory()
        collector.event_logger = _log
        _log("OCI client configured for direct connections (proxy disabled unless explicitly enabled).")
        try:
            snapshot = collector.collect()
        finally:
            # Ephemeral browser credentials are deleted even when an OCI call
            # fails. Regular profile collectors intentionally have a no-op close.
            close = getattr(collector, "close", None)
            if close:
                close()
        store = store or SnapshotStore(cache_dir)
        path = store.save(snapshot)
    except Exception as exc:  # Web UI must expose errors without killing Streamlit.
        _log(f"Collection failed: {exc}", "error")
        with _LOCK:
            _STATE.update(status="failed", finished_at=_now(), message="Collection failed", error=str(exc))
        return
    if store.last_object_name:
        _log("Snapshot archived to OCI Object Storage.")
    elif store.object_archive and store.last_archive_error:
        _log(f"Object Storage archive was unavailable; retained local snapshot only: {store.last_archive_error}", "warning")
    with _LOCK:
        _STATE.update(
            status="completed", finished_at=_now(), message=("Snapshot collected, cached, and archived" if store.last_object_name else "Snapshot collected and cached"),
            snapshot_path=str(path), entities=len(snapshot.entities), memberships=len(snapshot.memberships),
            relationships=len(snapshot.relationships), statements=len(snapshot.statements), error=None,
        )
    _log(f"Collection completed: {len(snapshot.entities)} entities, {len(snapshot.memberships)} memberships, "
         f"{len(snapshot.relationships)} correlations, and {len(snapshot.statements)} policy statements.")


def start_collection_job(
    cache_dir: Path,
    collector_factory: Callable[[], OCICollector] = OCICollector.from_default_profile,
    store: SnapshotStore | None = None,
) -> bool:
    """Start a collection if one is not already queued or running."""
    with _LOCK:
        if _STATE["status"] in {"queued", "running"}:
            return False
        _STATE.update(status="queued", message="Collection queued", error=None, logs=[])
    _log("Collection queued.")
    _EXECUTOR.submit(_collect, cache_dir, collector_factory, store)
    return True
