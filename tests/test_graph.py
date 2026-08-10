"""Tests for IAM graph nodes, relationships, and focused exports."""

from oci_iam_plotter.graph import build_compact_graph, build_graph, build_multi_focus_graph, focused_graph_html, graph_data


def test_graph_contains_membership_and_policy_edges(snapshot) -> None:
    graph = build_graph(snapshot)
    relations = {(left, right, attrs["relation"]) for left, right, attrs in graph.edges(data=True)}
    assert ("user-1", "group-1", "MEMBER_OF") in relations
    assert ("policy-1", "policy-1#0", "HAS_STATEMENT") in relations
    assert ("policy-1#0", "group-1", "APPLIES_TO") in relations


def test_user_focus_reaches_policy_statement(snapshot) -> None:
    data = graph_data(build_graph(snapshot), "user-1")
    assert "policy-1#0" in {node["id"] for node in data["nodes"]}


def test_compact_graph_hides_statement_nodes(snapshot) -> None:
    graph = build_compact_graph(snapshot, "user-1", depth=2, max_nodes=10)
    assert "policy-1#0" not in graph
    assert {attrs["kind"] for _, attrs in graph.nodes(data=True)} == {"user", "group", "policy"}
    assert graph.number_of_nodes() <= 10


def test_compact_graph_filters_and_caps_connections(snapshot) -> None:
    graph = build_compact_graph(snapshot, "user-1", depth=2, max_nodes=10,
                                relations={"MEMBER_OF"}, max_edges=1)
    assert graph.number_of_edges() == 1
    assert {attrs["relation"] for _, _, attrs in graph.edges(data=True)} == {"MEMBER_OF"}

    empty = build_compact_graph(snapshot, "user-1", relations=set(), max_edges=10)
    assert list(empty.nodes) == ["user-1"]
    assert empty.number_of_edges() == 0


def test_focused_graph_html_has_zoom_and_home_controls(snapshot) -> None:
    html = focused_graph_html(build_compact_graph(snapshot, "user-1", depth=2), "user-1")
    assert 'aria-label="Maximize connection map"' in html
    assert 'aria-label="Zoom out"' in html
    assert 'aria-label="Zoom in"' in html
    assert 'aria-label="Fit map to home view"' in html
    assert ':fullscreen #iam-map-controls { display:flex; }' in html
    assert '#iam-map-controls { position:fixed' in html
    assert "network.fit" in html


def test_multi_focus_graph_keeps_each_selected_subject(snapshot) -> None:
    graph = build_multi_focus_graph(snapshot, ["user-1", "group-1"], depth=1, max_nodes=8, max_edges=6)
    assert {"user-1", "group-1"}.issubset(graph.nodes)
    assert graph.number_of_nodes() <= 8
    assert graph.number_of_edges() <= 6

    html = focused_graph_html(graph, ["user-1", "group-1"])
    assert 'aria-label="Maximize connection map"' in html
