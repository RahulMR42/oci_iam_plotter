"""Graph construction and optional portable HTML visualization."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from .analysis import parse_policy_statement
from .models import Snapshot


def build_graph(snapshot: Snapshot) -> nx.MultiDiGraph:
    """Build a directed graph from normalized IAM snapshot data."""
    graph = nx.MultiDiGraph()
    for entity in snapshot.entities:
        graph.add_node(entity.id, label=entity.name, kind=entity.kind, **entity.metadata)
    for entity in snapshot.entities:
        if entity.kind != "tenancy":
            parent_id = entity.compartment_id if entity.compartment_id in graph else snapshot.tenancy_id
            if parent_id in graph:
                graph.add_edge(parent_id, entity.id, relation="CONTAINS")
    for membership in snapshot.memberships:
        graph.add_edge(membership.user_id, membership.group_id, relation="MEMBER_OF")
    for relationship in snapshot.relationships:
        if relationship.source_id in graph and relationship.target_id in graph:
            graph.add_edge(relationship.source_id, relationship.target_id,
                           relation=relationship.kind, evidence=relationship.evidence)
    for statement in snapshot.statements:
        statement_node = statement.id
        graph.add_node(statement_node, label=statement.text, kind="policy_statement")
        graph.add_edge(statement.policy_id, statement_node, relation="HAS_STATEMENT")
        parsed = parse_policy_statement(statement)
        if parsed.principal_name:
            for node_id, attrs in graph.nodes(data=True):
                if attrs.get("kind", "").replace("_", "-") == parsed.principal_type and attrs.get("label", "").casefold() == parsed.principal_name.casefold():
                    graph.add_edge(statement_node, node_id, relation="APPLIES_TO")
    return graph


def build_compact_graph(snapshot: Snapshot, focus_id: str, depth: int = 2, max_nodes: int = 45,
                        relations: set[str] | None = None, max_edges: int | None = None) -> nx.MultiDiGraph:
    """Build a capped entity-level investigation graph around one entity.

    Policy statement nodes and generic tenancy containment are intentionally
    omitted. Their evidence remains available in the detail inspector.
    """
    entities = {entity.id: entity for entity in snapshot.entities}
    if focus_id not in entities:
        raise ValueError(f"Focus entity {focus_id!r} is not in the snapshot")
    graph = nx.MultiDiGraph()
    for entity in snapshot.entities:
        graph.add_node(entity.id, label=entity.name, kind=entity.kind)
    seen: set[tuple[str, str, str]] = set()

    def add_relation(source: str, target: str, relation: str, evidence: str = "direct") -> None:
        if source not in graph or target not in graph or (relations is not None and relation not in relations):
            return
        key = (source, target, relation)
        if key not in seen:
            graph.add_edge(source, target, relation=relation, evidence=evidence)
            seen.add(key)

    for membership in snapshot.memberships:
        add_relation(membership.user_id, membership.group_id, "MEMBER_OF")
    for relationship in snapshot.relationships:
        add_relation(relationship.source_id, relationship.target_id, relationship.kind, relationship.evidence)
    names: dict[tuple[str, str], str] = {}
    for entity in snapshot.entities:
        names[(entity.kind, entity.name.casefold())] = entity.id
        names[(entity.kind.replace("_", "-"), entity.name.casefold())] = entity.id
    for statement in snapshot.statements:
        parsed = parse_policy_statement(statement)
        principal_id = names.get((parsed.principal_type or "", (parsed.principal_name or "").casefold()))
        if principal_id:
            add_relation(principal_id, statement.policy_id, "GRANTED_BY_POLICY", "parsed_policy_text")
    for entity in snapshot.entities:
        if entity.kind == "policy" and entity.compartment_id in graph:
            add_relation(entity.id, entity.compartment_id, "SCOPED_IN")

    selected = {focus_id}
    frontier = [focus_id]
    for _ in range(max(1, min(depth, 3))):
        next_frontier: list[str] = []
        for node in frontier:
            neighbors = sorted({*graph.predecessors(node), *graph.successors(node)},
                               key=lambda item: (graph.nodes[item].get("kind", ""), graph.nodes[item].get("label", "")))
            for neighbor in neighbors:
                if neighbor not in selected and len(selected) < max_nodes:
                    selected.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier or len(selected) >= max_nodes:
            break
    focused = graph.subgraph(selected).copy()
    if max_edges is None or focused.number_of_edges() <= max_edges:
        return focused
    ranked = sorted(
        focused.edges(keys=True, data=True),
        key=lambda item: (0 if focus_id in item[:2] else 1, item[3].get("relation", ""),
                          focused.nodes[item[0]].get("label", ""), focused.nodes[item[1]].get("label", "")),
    )[:max_edges]
    limited = nx.MultiDiGraph()
    limited.add_node(focus_id, **focused.nodes[focus_id])
    for source, target, _, attrs in ranked:
        limited.add_node(source, **focused.nodes[source])
        limited.add_node(target, **focused.nodes[target])
        limited.add_edge(source, target, **attrs)
    return limited


def build_multi_focus_graph(
    snapshot: Snapshot,
    focus_ids: list[str],
    depth: int = 2,
    max_nodes: int = 45,
    relations: set[str] | None = None,
    max_edges: int | None = None,
) -> nx.MultiDiGraph:
    """Union capped neighborhoods for multiple investigation subjects."""
    unique_focus = list(dict.fromkeys(focus_ids))
    if not unique_focus:
        raise ValueError("At least one focus entity is required")
    candidates = [build_compact_graph(snapshot, focus_id, depth, max_nodes, relations, None)
                  for focus_id in unique_focus]
    combined = nx.compose_all(candidates)
    edge_cap = max_edges if max_edges is not None else combined.number_of_edges()
    if combined.number_of_nodes() <= max_nodes and combined.number_of_edges() <= edge_cap:
        return combined

    ranked = sorted(
        combined.edges(keys=True, data=True),
        key=lambda item: (0 if item[0] in unique_focus or item[1] in unique_focus else 1,
                          item[3].get("relation", ""), combined.nodes[item[0]].get("label", ""),
                          combined.nodes[item[1]].get("label", "")),
    )
    limited = nx.MultiDiGraph()
    for focus_id in unique_focus:
        limited.add_node(focus_id, **combined.nodes[focus_id])
    for source, target, _, attrs in ranked:
        new_nodes = {source, target} - set(limited.nodes)
        if limited.number_of_edges() >= edge_cap or limited.number_of_nodes() + len(new_nodes) > max_nodes:
            continue
        for node_id in (source, target):
            if node_id not in limited:
                limited.add_node(node_id, **combined.nodes[node_id])
        limited.add_edge(source, target, **attrs)
    return limited


def graph_data(graph: nx.MultiDiGraph, focus_id: str | None = None) -> dict:
    """Serialize graph data, optionally retaining a focus node's two-hop neighborhood."""
    selected = set(graph.nodes)
    if focus_id:
        if focus_id not in graph:
            raise ValueError(f"Focus node {focus_id!r} is not in graph")
        selected = {focus_id}
        frontier = {focus_id}
        for _ in range(3):
            neighbors: set[str] = set()
            for node in frontier:
                for source, target, attrs in graph.in_edges(node, data=True):
                    if attrs.get("relation") != "CONTAINS":
                        neighbors.add(source)
                for source, target, attrs in graph.out_edges(node, data=True):
                    if attrs.get("relation") != "CONTAINS":
                        neighbors.add(target)
            frontier = neighbors - selected
            selected.update(neighbors)
    return {"nodes": [{"id": node, **attrs} for node, attrs in graph.nodes(data=True) if node in selected],
            "edges": [{"source": source, "target": target, **attrs} for source, target, _, attrs in graph.edges(keys=True, data=True)
                      if source in selected and target in selected]}


def export_graph(graph: nx.MultiDiGraph, output: Path, focus_id: str | None = None) -> Path:
    """Export JSON or interactive HTML; HTML needs optional ``pyvis``."""
    data = graph_data(graph, focus_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return output
    if output.suffix.lower() != ".html":
        raise ValueError("Graph output must end in .json or .html")
    try:
        from pyvis.network import Network
    except ImportError as exc:
        raise RuntimeError("HTML visualization requires the pyvis dependency") from exc
    network = Network(height="850px", width="100%", directed=True, bgcolor="#ffffff",
                      font_color="#1f2937", cdn_resources="in_line")
    colors = {"user": "#2563eb", "group": "#16a34a", "dynamic_group": "#9333ea", "policy": "#ea580c", "policy_statement": "#facc15", "tenancy": "#0f172a", "compartment": "#0891b2"}
    for node in data["nodes"]:
        network.add_node(node["id"], label=node.get("label", node["id"]), title=node.get("kind", ""), color=colors.get(node.get("kind"), "#64748b"))
    for edge in data["edges"]:
        network.add_edge(edge["source"], edge["target"], label=edge.get("relation", ""), arrows="to")
    network.write_html(str(output), open_browser=False, notebook=False)
    return output


def graph_html(graph: nx.MultiDiGraph, focus_id: str | None = None) -> str:
    """Return a self-contained interactive HTML graph for web embedding."""
    data = graph_data(graph, focus_id)
    try:
        from pyvis.network import Network
    except ImportError as exc:
        raise RuntimeError("Web visualization requires the pyvis dependency") from exc
    network = Network(height="720px", width="100%", directed=True, bgcolor="#0b1220",
                      font_color="#e5eef7", cdn_resources="in_line")
    colors = {"user": "#38bdf8", "group": "#34d399", "dynamic_group": "#c084fc",
              "policy": "#fb923c", "policy_statement": "#facc15", "tenancy": "#e2e8f0",
              "compartment": "#22d3ee", "domain": "#f472b6"}
    for node in data["nodes"]:
        kind = node.get("kind", "unknown")
        label = node.get("label", node["id"])
        network.add_node(node["id"], label=label, title=f"{kind}: {label}",
                         color=colors.get(kind, "#94a3b8"))
    for edge in data["edges"]:
        network.add_edge(edge["source"], edge["target"], label=edge.get("relation", ""), arrows="to")
    network.set_options('{"physics":{"stabilization":{"iterations":120},"barnesHut":{"gravitationalConstant":-4500}},"interaction":{"hover":true,"navigationButtons":true,"keyboard":true}}')
    return network.generate_html(notebook=False)


def focused_graph_html(graph: nx.MultiDiGraph, focus_id: str | list[str]) -> str:
    """Return a fullscreen-only interactive map launched from a compact button."""
    try:
        from pyvis.network import Network
    except ImportError as exc:
        raise RuntimeError("Interactive map requires the pyvis dependency") from exc
    network = Network(height="500px", width="100%", directed=True, bgcolor="transparent",
                      font_color="#e2e8f0", cdn_resources="in_line")
    colors = {"user": "#0369a1", "domain_user": "#0369a1", "group": "#047857",
              "domain_group": "#047857", "dynamic_group": "#7e22ce", "policy": "#c2410c",
              "confidential_app": "#be123c", "oauth_app": "#be123c", "compartment": "#0e7490",
              "resource_type": "#475569", "domain": "#9d174d"}
    focus_ids = {focus_id} if isinstance(focus_id, str) else set(focus_id)
    for node_id, attrs in graph.nodes(data=True):
        kind = attrs.get("kind", "entity")
        label = attrs.get("label", node_id)
        network.add_node(
            node_id, label=label, title=f"{kind.replace('_', ' ')}: {label}",
            color="#0f172a" if node_id in focus_ids else colors.get(kind, "#475569"),
            borderWidth=4 if node_id in focus_ids else 1, borderWidthSelected=5,
            shape="box", font={"color": "#ffffff", "size": 15}, margin=12,
        )
    for source, target, attrs in graph.edges(data=True):
        inferred = attrs.get("evidence") in {"inferred_from_rule", "dynamic_group_rule"}
        network.add_edge(source, target, label=attrs.get("relation", "RELATED_TO").replace("_", " "),
                         title=f"Evidence: {attrs.get('evidence', 'direct')}", arrows="to",
                         dashes=inferred, color="#64748b", font={"color": "#94a3b8", "size": 11})
    network.set_options("""
    {
      "layout": {"hierarchical": {"enabled": true, "direction": "LR", "sortMethod": "directed", "nodeSpacing": 150, "levelSeparation": 230}},
      "physics": {"enabled": false},
      "interaction": {"hover": true, "keyboard": {"enabled": true}, "zoomView": true, "dragView": true, "tooltipDelay": 120},
      "edges": {"smooth": {"enabled": true, "type": "cubicBezier", "forceDirection": "horizontal", "roundness": 0.35}}
    }
    """)
    html = network.generate_html(notebook=False)
    controls = """
    <style>
      html, body { margin:0; min-height:0; background:transparent; overflow:hidden; }
      #mynetwork { display:none; }
      #iam-map-launch { height:38px; padding:0 14px; border:1px solid #64748b; border-radius:8px; background:#0f172a; color:#fff; cursor:pointer; font:600 14px Arial,sans-serif; }
      #iam-map-launch:hover, #iam-map-controls button:hover { background:#1e293b; }
      #iam-map-launch:focus, #iam-map-controls button:focus { outline:3px solid #f59e0b; outline-offset:1px; }
      #iam-map-controls { position:fixed; right:18px; top:18px; z-index:20; display:none; gap:6px; }
      #iam-map-controls button { min-width:40px; height:38px; padding:0 11px; border:1px solid #64748b; border-radius:8px; background:#0f172a; color:#fff; cursor:pointer; font:600 14px Arial,sans-serif; }
      :fullscreen { background:#07101d; }
      :fullscreen #mynetwork { display:block; width:100vw !important; height:100vh !important; background:#07101d; }
      :fullscreen #iam-map-launch { display:none; }
      :fullscreen #iam-map-controls { display:flex; }
    </style>
    <button id="iam-map-launch" type="button" aria-label="Maximize connection map" title="Open the map in a full window" onclick="openIamMap()">⛶ Maximize map</button>
    <div id="iam-map-controls" aria-label="Map view controls">
      <button type="button" aria-label="Zoom out" title="Zoom out" onclick="network.moveTo({scale:Math.max(0.1,network.getScale()/1.25),animation:{duration:180}})">−</button>
      <button type="button" aria-label="Fit map to home view" title="Home: fit all visible connections" onclick="network.fit({animation:{duration:240}})">Home</button>
      <button type="button" aria-label="Zoom in" title="Zoom in" onclick="network.moveTo({scale:Math.min(4,network.getScale()*1.25),animation:{duration:180}})">+</button>
      <button type="button" aria-label="Exit full screen" title="Return to the investigation" onclick="document.exitFullscreen()">Exit</button>
    </div>
    <script>
      function openIamMap() {
        document.documentElement.requestFullscreen().then(function() {
          setTimeout(function() { network.redraw(); network.fit({animation:false}); }, 120);
        });
      }
      document.addEventListener("fullscreenchange", function() {
        if (document.fullscreenElement) {
          setTimeout(function() { network.redraw(); network.fit({animation:false}); }, 120);
        }
      });
    </script>
    """
    return html.replace("</body>", controls + "</body>")
