"""Evidence-preserving comparison of two normalized IAM snapshots."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Iterable

from .models import Entity, Membership, PolicyStatement, Relationship, Snapshot


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return only fields whose normalized values differ."""
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _portable_key(value: Any) -> Any:
    """Keep compound internal keys safe for JSON evidence downloads."""
    return list(value) if isinstance(value, tuple) else value


def _compare(
    before: Iterable[Any],
    after: Iterable[Any],
    key: Callable[[Any], Any],
) -> dict[str, list[dict[str, Any]]]:
    """Compare serializable records without inferring identity from their names."""
    previous = {key(item): asdict(item) for item in before}
    current = {key(item): asdict(item) for item in after}
    added = [current[item_key] for item_key in sorted(current.keys() - previous.keys(), key=str)]
    removed = [previous[item_key] for item_key in sorted(previous.keys() - current.keys(), key=str)]
    changed = [
        {"id": _portable_key(item_key), "before": previous[item_key], "after": current[item_key],
         "changes": _changed_fields(previous[item_key], current[item_key])}
        for item_key in sorted(current.keys() & previous.keys(), key=str)
        if previous[item_key] != current[item_key]
    ]
    return {"added": added, "removed": removed, "changed": changed}


def snapshot_drift(baseline: Snapshot, current: Snapshot) -> dict[str, Any]:
    """Return factual IAM inventory changes between two collections.

    OCI IDs remain the identity key.  This intentionally does not decide
    whether an observed change is risky or whether OCI will authorize it at
    runtime; it is a review queue backed by the two original snapshots.
    """
    if baseline.tenancy_id != current.tenancy_id:
        raise ValueError("Snapshots belong to different tenancies and cannot be compared.")

    entities = _compare(baseline.entities, current.entities, lambda item: item.id)
    memberships = _compare(
        baseline.memberships, current.memberships,
        lambda item: (item.user_id, item.group_id),
    )
    statements = _compare(baseline.statements, current.statements, lambda item: item.id)
    relationships = _compare(
        baseline.relationships, current.relationships,
        lambda item: (item.source_id, item.target_id, item.kind),
    )
    sections = {
        "entities": entities,
        "memberships": memberships,
        "policy_statements": statements,
        "relationships": relationships,
    }
    counts = {
        section: {change: len(records) for change, records in values.items()}
        for section, values in sections.items()
    }
    return {
        "baseline": {"collected_at": baseline.collected_at, "source_hash": baseline.source_hash},
        "current": {"collected_at": current.collected_at, "source_hash": current.source_hash},
        "tenancy_id": current.tenancy_id,
        "unchanged": all(not any(values.values()) for values in counts.values())
        and baseline.warnings == current.warnings,
        "counts": counts,
        **sections,
        "collection_warnings": {
            "added": sorted(set(current.warnings) - set(baseline.warnings)),
            "resolved": sorted(set(baseline.warnings) - set(current.warnings)),
        },
        "limitations": [
            "Changes are compared by OCI or normalized record IDs; similarly named entities are not treated as identical.",
            "This report shows collected inventory drift, not final OCI runtime authorization or a risk decision.",
        ],
    }
