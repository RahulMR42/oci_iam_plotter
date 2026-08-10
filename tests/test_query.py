"""Tests for conversational retrieval over cached IAM evidence."""

from oci_iam_plotter.query import collection_query, deterministic_query_answer, run_iam_agent


def test_collection_query_retrieves_user_access(snapshot) -> None:
    evidence = collection_query(snapshot, "What access does alice have?")
    assert evidence["matched_entities"][0]["name"] == "alice"
    assert evidence["matched_user_access"][0]["implied_permissions"] == ["read all-resources (tenancy)"]
    assert "not a final authorization decision" in deterministic_query_answer(evidence)


def test_collection_query_can_request_duplicates(snapshot) -> None:
    evidence = collection_query(snapshot, "Are there duplicated policies or groups?")
    assert evidence["duplicate_candidates"] is not None


def test_collection_query_lists_only_groups_matching_quoted_name_fragment(snapshot) -> None:
    evidence = collection_query(snapshot, 'List all groups contain a name "audit"')
    assert evidence["structured_query"] == {"intent": "list_groups_name_contains", "name_fragment": "audit", "total": 1}
    assert [item["name"] for item in evidence["matched_entities"]] == ["Auditors"]
    assert deterministic_query_answer(evidence) == 'Groups with a name containing "audit" (1): Auditors (group).'


def test_collection_query_reports_no_matching_groups_for_quoted_name_fragment(snapshot) -> None:
    evidence = collection_query(snapshot, 'List all groups contain a name "cms"')
    assert evidence["matched_entities"] == []
    assert deterministic_query_answer(evidence) == 'No collected groups have a name containing "cms".'


def test_agent_resolves_group_follow_up_from_conversation(snapshot) -> None:
    evidence = run_iam_agent(snapshot, "show those groups", [{"role": "user", "text": 'List all groups contain a name "audit"'}])
    assert evidence["agent"]["resolved_question"] == 'List all groups contain a name "audit"'
    assert evidence["agent"]["tools"] == ["snapshot_inventory", "list_groups_by_name"]
