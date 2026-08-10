"""Tests for conservative cross-entity correlation."""

from oci_iam_plotter.models import Entity, PolicyStatement, Relationship, Snapshot
from oci_iam_plotter.relationships import deduplicate_relationships, derive_relationships


def test_dynamic_group_rule_correlates_type_compartment_and_policy() -> None:
    compartment_id = "ocid1.compartment.oc1..example"
    dynamic_group = Entity(
        "dg-1", "build-runners", "dynamic_group",
        metadata={"matching_rule": f"ALL {{resource.type='instance', resource.compartment.id='{compartment_id}'}}"},
    )
    snapshot = Snapshot(
        "tenancy-1", "now",
        entities=[Entity("tenancy-1", "root", "tenancy"),
                  Entity(compartment_id, "build", "compartment"), dynamic_group,
                  Entity("policy-1", "runner-policy", "policy")],
        statements=[PolicyStatement("statement-1", "policy-1",
                                    "Allow dynamic-group build-runners to use instances in tenancy", 0)],
    )
    synthetic, relationships = derive_relationships(snapshot)
    assert synthetic[0].id == "resource-type:instance"
    kinds = {(item.target_id, item.kind, item.evidence) for item in relationships}
    assert ("policy-1", "GRANTED_BY_POLICY", "parsed_policy_text") in kinds
    assert (compartment_id, "RULE_REFERENCES", "dynamic_group_rule") in kinds
    assert ("resource-type:instance", "MAY_MATCH_RESOURCE_TYPE", "inferred_from_rule") in kinds


def test_relationship_deduplication_preserves_distinct_evidence() -> None:
    direct = Relationship("user-1", "app-1", "ASSIGNED_TO_APP", metadata={"grant_id": "one"})
    second = Relationship("user-1", "app-1", "ASSIGNED_TO_APP", metadata={"grant_id": "two"})
    assert deduplicate_relationships([direct, direct, second]) == [direct, second]
