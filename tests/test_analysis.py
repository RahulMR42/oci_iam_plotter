"""Tests for policy parsing and conservative user access inference."""

from oci_iam_plotter.analysis import parse_policy_statement, policy_analysis
from oci_iam_plotter.models import PolicyStatement


def test_policy_parser_extracts_standard_statement() -> None:
    parsed = parse_policy_statement(PolicyStatement("p#0", "p", "Allow group Auditors to read all-resources in tenancy", 0))
    assert parsed.principal_name == "Auditors"
    assert parsed.verb == "read"
    assert parsed.resource_type == "all-resources"
    assert parsed.scope == "tenancy"
    assert parsed.confidence == "parsed"


def test_policy_parser_preserves_ambiguous_text() -> None:
    text = "endorse group Builders to manage repos in any-tenancy"
    parsed = parse_policy_statement(PolicyStatement("p#1", "p", text, 1))
    assert parsed.confidence == "ambiguous"
    assert parsed.original_text == text


def test_user_analysis_matches_membership(snapshot) -> None:
    result = policy_analysis(snapshot, "user-1")
    assert result["groups"][0]["name"] == "Auditors"
    assert result["implied_permissions"] == ["read all-resources (tenancy)"]
    assert result["confidence"] == "inferred"

