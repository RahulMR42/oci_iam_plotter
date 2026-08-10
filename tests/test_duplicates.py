"""Tests for exact and near duplicate candidate detection."""

from dataclasses import replace

from oci_iam_plotter.analysis import find_duplicates
from oci_iam_plotter.models import Entity, PolicyStatement


def test_duplicate_detection_flags_but_does_not_merge(snapshot) -> None:
    snapshot.entities.append(Entity("group-2", "Auditors", "group"))
    snapshot.statements.append(PolicyStatement("policy-2#0", "policy-2", snapshot.statements[0].text.upper(), 0))
    result = find_duplicates(snapshot)
    assert len(result["exact_entity_name_candidates"]) == 1
    assert len(result["exact_policy_statement_candidates"]) == 1
    assert len(snapshot.entities) == 5


def test_near_duplicate_name(snapshot) -> None:
    snapshot.entities.append(Entity("group-2", "Auditor", "group"))
    assert find_duplicates(snapshot, 0.8)["near_entity_name_candidates"]

