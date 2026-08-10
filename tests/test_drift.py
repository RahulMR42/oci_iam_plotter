"""Tests for snapshot inventory drift comparison."""

from __future__ import annotations

import pytest

from oci_iam_plotter.drift import snapshot_drift
from oci_iam_plotter.models import Entity, Membership, PolicyStatement, Relationship, Snapshot


def test_snapshot_drift_reports_additions_removals_and_changes(snapshot: Snapshot) -> None:
    baseline = Snapshot(
        tenancy_id="tenancy", collected_at="2026-01-01T00:00:00Z",
        entities=[Entity("user-1", "Alice", "user"), Entity("group-1", "Readers", "group")],
        memberships=[Membership("user-1", "group-1")],
        statements=[PolicyStatement("policy-1#0", "policy-1", "Allow group Readers to read buckets in tenancy", 0)],
        relationships=[Relationship("user-1", "app-1", "ASSIGNED_TO_APP", "direct")],
        warnings=["Baseline warning"], source_hash="old",
    )
    current = Snapshot(
        tenancy_id="tenancy", collected_at="2026-01-02T00:00:00Z",
        entities=[Entity("user-1", "Alice A.", "user"), Entity("group-2", "Writers", "group")],
        memberships=[Membership("user-1", "group-2")],
        statements=[PolicyStatement("policy-1#0", "policy-1", "Allow group Writers to manage buckets in tenancy", 0)],
        relationships=[Relationship("user-1", "app-1", "ASSIGNED_TO_APP", "identity_domains_grant")],
        warnings=["Current warning"], source_hash="new",
    )

    drift = snapshot_drift(baseline, current)

    assert drift["counts"]["entities"] == {"added": 1, "removed": 1, "changed": 1}
    assert drift["entities"]["changed"][0]["changes"]["name"] == {"before": "Alice", "after": "Alice A."}
    assert drift["counts"]["memberships"] == {"added": 1, "removed": 1, "changed": 0}
    assert drift["counts"]["policy_statements"] == {"added": 0, "removed": 0, "changed": 1}
    assert drift["counts"]["relationships"] == {"added": 0, "removed": 0, "changed": 1}
    assert drift["collection_warnings"] == {"added": ["Current warning"], "resolved": ["Baseline warning"]}
    assert not drift["unchanged"]


def test_snapshot_drift_rejects_cross_tenancy_comparison() -> None:
    baseline = Snapshot.empty("one")
    current = Snapshot.empty("two")

    with pytest.raises(ValueError, match="different tenancies"):
        snapshot_drift(baseline, current)
