"""Streamlit web application for IAM collection, relationship exploration, and reports."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import html
from io import BytesIO
import json
from pathlib import Path
import textwrap
from typing import Any

import streamlit as st

from oci_iam_plotter import __version__
from oci_iam_plotter.analysis import find_duplicates, parse_policy_statement, policy_analysis
from oci_iam_plotter.auth import credentials_match, local_credentials
from oci_iam_plotter.collector import OCICollector
from oci_iam_plotter.drift import snapshot_drift
from oci_iam_plotter.graph import build_multi_focus_graph, focused_graph_html
from oci_iam_plotter.jobs import collection_status, start_collection_job
from oci_iam_plotter.models import Snapshot
from oci_iam_plotter.reporting import csv_report, markdown_report, pdf_report, report_payload, xlsx_report
from oci_iam_plotter.query import collection_query, deterministic_query_answer
from oci_iam_plotter.store import SnapshotStore
from oci_iam_plotter.summarizer import OCIReasoner, deterministic_summary
from oci_iam_plotter.settings import Settings

SETTINGS = Settings.from_env()
CACHE_DIR = SETTINGS.cache_dir
STORE = SnapshotStore(CACHE_DIR)

TERM_HELP = {
    "tenancy": "The root OCI account and top-level IAM boundary represented by this snapshot.",
    "compartment": "A hierarchical OCI container used to organize resources and scope policies.",
    "domain": "An OCI Identity Domain containing domain-local users, groups, and applications.",
    "user": "A collected human or service identity that can belong to IAM groups.",
    "group": "A named set of users used as a principal in OCI policy statements.",
    "dynamic_group": "A rule-based set of OCI resources. It does not contain human users.",
    "policy": "An OCI IAM policy containing one or more authorization statements.",
    "policy_statement": "One original policy sentence preserved as collection evidence.",
    "confidential_app": "An Identity Domains OAuth client able to protect credentials; secret values are never collected.",
    "oauth_app": "An Identity Domains OAuth client that is not classified as confidential.",
    "domain_user": "A user found only through an Identity Domains SCIM endpoint.",
    "domain_group": "A group found only through an Identity Domains SCIM endpoint.",
    "resource_type": "A resource category referenced by a dynamic-group rule; it is not an inventoried resource instance.",
    "Parsed": "The statement matched the supported OCI Allow syntax and its principal, verb, resource type, scope, and condition were extracted.",
    "Ambiguous": "The statement was preserved but did not match the supported grammar confidently. It requires manual review and is not treated as proven access.",
    "Inferred": "A conclusion derived from collected evidence. It is not OCI's final runtime authorization decision.",
    "Direct evidence": "A relationship explicitly returned by an OCI API, such as user membership or an application grant.",
    "Correlation": "A local connection between collected entities. Its evidence field states whether it is direct, parsed, or inferred.",
    "Incoming": "Visible relationships whose arrow points to the selected entity.",
    "Outgoing": "Visible relationships whose arrow starts at the selected entity.",
    "Depth": "One hop shows direct neighbors; two hops also shows the next connected layer.",
    "MEMBER_OF": "A directly collected user-to-group membership.",
    "ASSIGNED_TO_APP": "An Identity Domains grant connecting a user or group to an OAuth application.",
    "GRANTED_BY_POLICY": "A parsed policy statement targets this group or dynamic group.",
    "SCOPED_IN": "The policy was created in the connected tenancy or compartment.",
    "RULE_REFERENCES": "A dynamic-group rule explicitly names the connected collected OCID; this does not prove runtime membership.",
    "MAY_MATCH_RESOURCE_TYPE": "A dynamic-group rule names this resource type; actual matching depends on resource attributes.",
}

st.set_page_config(page_title="OCI IAM Plotter", page_icon="◈", layout="wide",
                   initial_sidebar_state="expanded")


def _styles(theme: str) -> None:
    themes = {
        "System": "--ink:var(--text-color);--muted:color-mix(in srgb,var(--text-color) 62%,transparent);--line:color-mix(in srgb,var(--text-color) 16%,transparent);--accent:var(--primary-color);--surface:var(--secondary-background-color);--app-bg:var(--background-color);",
        "Light": "--ink:#172033;--muted:#5b6474;--line:#d7dde7;--accent:#0066cc;--surface:#ffffff;--app-bg:#f4f7fb;",
        "Simple light": "--ink:#1f2937;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;--surface:#ffffff;--app-bg:#ffffff;",
        "Dark": "--ink:#e7eef8;--muted:#9aa8bb;--line:#26364b;--accent:#22d3ee;--surface:#111d2f;--app-bg:#08111f;",
        "Ocean": "--ink:#e8fbff;--muted:#a4ced6;--line:#23566a;--accent:#35d5c8;--surface:#103848;--app-bg:#062631;",
        "High contrast": "--ink:#ffffff;--muted:#ffffff;--line:#ffffff;--accent:#ffff00;--surface:#000000;--app-bg:#000000;",
    }
    css = """
        <style>
        :root { __THEME_TOKENS__ }
        .stApp { background:var(--app-bg); color:var(--ink); }
        [data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--line); }
        [data-testid="stHeader"] { background:transparent; }
        .hero { padding:1.25rem 1.5rem; border:1px solid var(--line); border-radius:18px; background:linear-gradient(125deg,var(--surface),color-mix(in srgb,var(--accent) 17%,var(--surface))); box-shadow:0 16px 42px color-mix(in srgb,var(--text-color) 12%,transparent); margin-bottom:.85rem; }
        .hero h1 { color:var(--ink); font-size:2rem; letter-spacing:-.035em; margin:0; }
        .hero p { color:var(--muted); max-width:900px; font-size:1.02rem; margin:.55rem 0 0; }
        .eyebrow { color:var(--accent); text-transform:uppercase; letter-spacing:.14em; font-size:.73rem; font-weight:700; }
        .safety { border:1px solid color-mix(in srgb,var(--accent) 35%,transparent); background:color-mix(in srgb,var(--accent) 10%,var(--surface)); border-radius:14px; padding:.8rem 1rem; color:var(--ink); }
        div[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:1rem; }
        div[data-testid="stMetric"] label { color:var(--muted) !important; }
        div[data-testid="stMetricValue"] { color:var(--ink); }
        .entity-pill { display:inline-block; padding:.25rem .55rem; border-radius:999px; background:color-mix(in srgb,var(--accent) 10%,var(--surface)); border:1px solid var(--line); margin:.12rem; }
        .footer { color:var(--muted); border-top:1px solid var(--line); padding:1.3rem 0 .5rem; margin-top:2rem; font-size:.82rem; }
        .stTabs [data-baseweb="tab-list"] { gap:.35rem; }
        .stTabs [data-baseweb="tab"] { background:var(--surface); border-radius:10px; padding:.45rem .8rem; }
        .flow-rail { display:grid; grid-template-columns:repeat(3,1fr); gap:.6rem; margin:.25rem 0 1rem; }
        .flow-step { padding:.65rem .8rem; border-left:3px solid var(--accent); background:var(--surface); border-radius:8px; color:var(--muted); }
        .flow-step b { color:var(--ink); display:block; }
        .focus-card { padding:1rem; border:1px solid var(--line); border-radius:14px; background:var(--surface); }
        .help-term { color:inherit; text-decoration:underline dotted var(--muted); text-underline-offset:.2em; cursor:help; }
        .st-key-chat_launcher { position:fixed; right:1.35rem; bottom:1.25rem; width:auto; z-index:999990; }
        .st-key-chat_launcher button { border-radius:999px; min-height:3rem; padding:0 1.2rem; box-shadow:0 14px 38px rgba(0,0,0,.4); }
        div[data-testid="stPopoverBody"] { max-height:min(76vh,760px); overflow-y:auto; }
        div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] { position:sticky; bottom:0; z-index:5; background:var(--surface); padding-top:.45rem; }
        @media (max-width:700px) { .st-key-chat_launcher { right:.8rem; bottom:.8rem; } .flow-rail { grid-template-columns:1fr; } }
        </style>
        """.replace("__THEME_TOKENS__", themes.get(theme, themes["System"]))
    st.markdown(
        css,
        unsafe_allow_html=True,
    )


def _help_heading(label: str, explanation: str, level: int = 4) -> None:
    """Render a heading with a native mouse-over explanation."""
    st.markdown(
        f'<h{level}><abbr class="help-term" title="{html.escape(explanation, quote=True)}">{html.escape(label)}</abbr></h{level}>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _load_snapshot(path: str, modified_ns: int) -> Snapshot:
    """Load a snapshot with cache invalidation based on file modification time."""
    del modified_ns
    return Snapshot.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _snapshot() -> Snapshot | None:
    selected = Path(st.session_state.get("active_snapshot_path", STORE.path))
    if not selected.exists():
        selected = STORE.path
    if not selected.exists():
        return None
    return _load_snapshot(str(selected), selected.stat().st_mtime_ns)


def _login_gate() -> bool:
    """Require a local password before rendering collection or IAM data."""
    if st.session_state.get("authenticated"):
        return True
    st.markdown('<section class="hero"><div class="eyebrow">Protected local analysis</div>'
                '<h1>Sign in to OCI IAM Plotter</h1><p>Use the configured local credentials.</p></section>',
                unsafe_allow_html=True)
    attempts = int(st.session_state.get("login_attempts", 0))
    with st.form("local_login"):
        username = st.text_input("Username", value=local_credentials().username, autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", type="primary", width="stretch", disabled=attempts >= 5)
    if submitted:
        if credentials_match(username, password):
            st.session_state.update(authenticated=True, login_attempts=0)
            st.rerun()
        else:
            st.session_state["login_attempts"] = attempts + 1
            st.error("Invalid local username or password.")
    return False


def _entity_counts(snapshot: Snapshot) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in snapshot.entities:
        counts[entity.kind] = counts.get(entity.kind, 0) + 1
    return counts


def _entity_label(entity: Any) -> str:
    return f"{entity.name} · {entity.kind.replace('_', ' ')} · {entity.id[-12:]}"


def _table(items: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    if not items:
        st.caption("No matching records.")
        return
    if columns:
        items = [{key: item.get(key) for key in columns} for item in items]
    st.dataframe(items, width="stretch", hide_index=True)


@st.fragment(run_every=2)
def _collection_monitor() -> None:
    status = collection_status()
    if status["status"] in {"queued", "running"}:
        st.info(f"{status['message']} — this view refreshes automatically.")
        st.progress(0.5, text="Collection is running")
    elif status["status"] == "failed":
        st.error(status.get("error") or "Collection failed")
    elif status["status"] == "completed":
        st.success(
            f"Collected {status['entities']} entities, {status['memberships']} memberships, "
            f"{status['relationships']} correlations, and {status['statements']} statements."
        )
        if st.session_state.get("loaded_collection") != status["finished_at"]:
            st.session_state["loaded_collection"] = status["finished_at"]
            st.session_state.pop("active_snapshot_path", None)
            st.cache_data.clear()
            st.rerun(scope="app")


def _sidebar(snapshot: Snapshot | None) -> None:
    with st.sidebar:
        st.markdown("### ◈ OCI IAM Plotter")
        st.caption(f"Version {__version__} · local analysis")
        st.selectbox("Theme", ["System", "Light", "Simple light", "Dark", "Ocean", "High contrast"],
                     key="theme_choice", help="Changes the application palette. System follows the active Streamlit/browser theme.")
        with st.popover("IAM terminology", icon=":material/help:", width="stretch"):
            st.caption("Hover-enabled help appears throughout the app. Use this glossary for table keywords.")
            for term in ("Parsed", "Ambiguous", "Inferred", "Direct evidence", "Correlation",
                         "MEMBER_OF", "ASSIGNED_TO_APP", "GRANTED_BY_POLICY", "SCOPED_IN",
                         "RULE_REFERENCES", "MAY_MATCH_RESOURCE_TYPE"):
                st.markdown(f"**{term.replace('_', ' ')}** — {TERM_HELP[term]}")
        _help_heading("Data collection", "Runs read-only OCI SDK list/get operations and saves a normalized local snapshot.")
        st.warning("Recommended: collect with a tenancy administrator or an equivalently authorized read-only identity so the snapshot is complete.")
        source = st.radio("Credential source", ["Local config (local runs only)", "Upload or paste for this collection"],
                          help="Hosted deployments must use upload or paste. Credential inputs are deleted after this collection.")
        config_path = ""
        config_text = ""
        pem_text = ""
        if source == "Local config (local runs only)":
            config_path = st.text_input("OCI config path", value=str(SETTINGS.oci_config_file),
                                        help="Available only when this app can access a local config file.")
        else:
            config_upload = st.file_uploader("OCI config file", type=["config", "txt", "ini"])
            config_paste = st.text_area("Or paste OCI config", height=140)
            pem_upload = st.file_uploader("OCI API-signing PEM file", type=["pem", "key"])
            pem_paste = st.text_area("Or paste PEM private key", height=140, type="password")
            config_text = config_upload.getvalue().decode("utf-8") if config_upload else config_paste
            pem_text = pem_upload.getvalue().decode("utf-8") if pem_upload else pem_paste
            st.caption("The config and PEM are written with owner-only permissions to a temporary directory, used for this read-only run, then removed whether collection succeeds or fails. They are never cached, logged, or included in snapshots.")
        profile_name = st.text_input("OCI profile", value=SETTINGS.oci_config_profile, help="Defaults to DEFAULT")
        st.caption("Collection uses only OCI SDK GET/list operations.")
        acknowledged = st.checkbox("I understand this performs read-only OCI queries", value=True)
        busy = collection_status()["status"] in {"queued", "running"}
        if st.button("Collect IAM snapshot", type="primary", width="stretch", disabled=busy or not acknowledged):
            if source != "Local config (local runs only)" and (not config_text.strip() or not pem_text.strip()):
                st.error("Provide both an OCI config and its API-signing PEM file.")
            else:
                factory = (
                    (lambda config=config_text, pem=pem_text, profile=profile_name:
                     OCICollector.from_ephemeral_profile(config, pem, profile))
                    if source != "Local config (local runs only)"
                    else (lambda path=config_path, profile=profile_name: OCICollector.from_profile(path, profile))
                )
                start_collection_job(CACHE_DIR, factory)
                st.rerun()
        _collection_monitor()
        st.markdown("---")
        if snapshot:
            _help_heading("Collection history", "Previously cached snapshots, retained by tenancy and collection timestamp. The newest five per tenancy are kept.")
            records = STORE.list_history()
            paths = [str(item.path) for item in records]
            active = st.session_state.get("active_snapshot_path")
            index = paths.index(active) if active in paths else 0
            selected_path = st.selectbox(
                "Loaded collection", paths, index=index,
                format_func=lambda path: next(
                    f"{item.collected_at} · tenancy {item.tenancy_id[-12:]}" for item in records if str(item.path) == path
                ),
            )
            if selected_path != active:
                st.session_state["active_snapshot_path"] = selected_path
                st.rerun()
            st.code(snapshot.source_hash or "unhashed", language=None)
            st.caption("Retains up to five timestamped collections per tenancy.")
        else:
            st.warning("No local snapshot loaded yet.")
        st.markdown("---")
        st.caption("Secrets are never displayed. GenAI runs only when requested.")


def _overview(snapshot: Snapshot) -> None:
    counts = _entity_counts(snapshot)
    keys = ["user", "group", "domain_user", "domain_group", "confidential_app", "oauth_app",
            "dynamic_group", "policy", "policy_statement", "compartment", "domain"]
    values = {**counts, "policy_statement": len(snapshot.statements)}
    cols = st.columns(4)
    for index, kind in enumerate(keys):
        cols[index % 4].metric(kind.replace("_", " ").title(), values.get(kind, 0),
                               help=TERM_HELP.get(kind))
    _help_heading("Relationship inventory", "Counts direct memberships, locally correlated records, and policy parser outcomes.")
    relation_cols = st.columns(4)
    relation_cols[0].metric("User memberships", len(snapshot.memberships), help=TERM_HELP["MEMBER_OF"])
    relation_cols[1].metric("Correlated records", len(snapshot.relationships), help=TERM_HELP["Correlation"])
    relation_cols[2].metric("Parsed statements", sum(parse_policy_statement(item).confidence == "parsed" for item in snapshot.statements),
                            help=TERM_HELP["Parsed"])
    relation_cols[3].metric("Ambiguous statements", sum(parse_policy_statement(item).confidence == "ambiguous" for item in snapshot.statements),
                            help=TERM_HELP["Ambiguous"])
    if snapshot.warnings:
        with st.expander(f"Collection warnings ({len(snapshot.warnings)})"):
            for warning in snapshot.warnings:
                st.warning(warning)
    _help_heading("What this snapshot can prove", "Separates direct API evidence from conservative policy and rule inference.")
    st.markdown(
        """
        <div class="safety">Group membership and original policy text are direct evidence. Permission summaries are conservative
        inferences; OCI runtime authorization, conditions, compartment inheritance, and service-specific verb expansion remain authoritative.</div>
        """,
        unsafe_allow_html=True,
    )


def _relationship_rows(snapshot: Snapshot, entity_id: str) -> list[dict[str, Any]]:
    """Create a readable adjacency list from memberships and normalized evidence."""
    entities = {entity.id: entity for entity in snapshot.entities}
    rows: list[dict[str, Any]] = []
    for membership in snapshot.memberships:
        if membership.user_id == entity_id:
            target = entities.get(membership.group_id)
            rows.append({"direction": "out", "relationship": "MEMBER_OF", "evidence": "direct",
                         "related_name": target.name if target else membership.group_id,
                         "related_kind": target.kind if target else "group", "related_id": membership.group_id})
        elif membership.group_id == entity_id:
            source = entities.get(membership.user_id)
            rows.append({"direction": "in", "relationship": "MEMBER_OF", "evidence": "direct",
                         "related_name": source.name if source else membership.user_id,
                         "related_kind": source.kind if source else "user", "related_id": membership.user_id})
    for relationship in snapshot.relationships:
        if relationship.source_id != entity_id and relationship.target_id != entity_id:
            continue
        outgoing = relationship.source_id == entity_id
        related_id = relationship.target_id if outgoing else relationship.source_id
        related = entities.get(related_id)
        rows.append({"direction": "out" if outgoing else "in", "relationship": relationship.kind,
                     "evidence": relationship.evidence, "related_name": related.name if related else related_id,
                     "related_kind": related.kind if related else "uncollected reference", "related_id": related_id,
                     "details": relationship.metadata})
    return sorted(rows, key=lambda item: (item["relationship"], item["related_name"].casefold()))


def _dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _focused_dot(graph: Any, focus_id: str | list[str]) -> str:
    """Build a deterministic left-to-right Graphviz flow for a focused subgraph."""
    focus_ids = {focus_id} if isinstance(focus_id, str) else set(focus_id)
    node_ids = {node_id: f"n{index}" for index, node_id in enumerate(graph.nodes)}
    fills = {"user": "#075985", "domain_user": "#075985", "group": "#065f46",
             "domain_group": "#065f46", "dynamic_group": "#6b21a8", "policy": "#9a3412",
             "confidential_app": "#9f1239", "oauth_app": "#9f1239", "compartment": "#155e75",
             "resource_type": "#334155", "domain": "#831843"}
    lines = ["digraph IAM {", 'graph [rankdir=LR, bgcolor="transparent", pad="0.2", nodesep="0.35", ranksep="0.75"];',
             'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=10, fontcolor="white", color="#64748b", margin="0.14,0.08"];',
             'edge [fontname="Arial", fontsize=8, fontcolor="#cbd5e1", color="#64748b", arrowsize=0.7];']
    for node_id, attrs in graph.nodes(data=True):
        label = str(attrs.get("label", node_id))
        if len(label) > 32:
            label = label[:29] + "…"
        label = f"{label}\n{str(attrs.get('kind', 'entity')).replace('_', ' ')}"
        shape = "doubleoctagon" if node_id in focus_ids else "box"
        fill = "#0e7490" if node_id in focus_ids else fills.get(attrs.get("kind"), "#334155")
        lines.append(f'{node_ids[node_id]} [label="{_dot_escape(label)}", shape="{shape}", fillcolor="{fill}"];')
    for source, target, attrs in graph.edges(data=True):
        relation = str(attrs.get("relation", "RELATED_TO")).replace("_", " ")
        style = "dashed" if attrs.get("evidence") in {"inferred_from_rule", "dynamic_group_rule"} else "solid"
        lines.append(f'{node_ids[source]} -> {node_ids[target]} [label="{_dot_escape(relation)}", style="{style}"];')
    return "\n".join([*lines, "}"])


def _focused_graph_payload(graph: Any, focus_id: str | list[str]) -> dict[str, Any]:
    """Return a portable JSON representation of the currently visible map."""
    focus_ids = [focus_id] if isinstance(focus_id, str) else list(focus_id)
    return {
        "focus_id": focus_ids[0],
        "focus_ids": focus_ids,
        "nodes": [{"id": node_id, **attrs} for node_id, attrs in graph.nodes(data=True)],
        "edges": [{"source": source, "target": target, **attrs}
                  for source, target, attrs in graph.edges(data=True)],
    }


@st.cache_data(show_spinner=False)
def _map_png(payload_json: str) -> bytes:
    """Render a portable hierarchical PNG without external graph binaries."""
    from PIL import Image, ImageDraw, ImageFont

    payload = json.loads(payload_json)
    nodes = {item["id"]: item for item in payload["nodes"]}
    focus_ids = set(payload.get("focus_ids") or [payload["focus_id"]])
    focus_id = payload["focus_id"]
    incoming: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in payload["edges"]:
        outgoing[edge["source"]].add(edge["target"])
        incoming[edge["target"]].add(edge["source"])

    layers: dict[str, int] = {focus_id: 0}
    layers.update({node_id: -1 for node_id in incoming[focus_id]})
    layers.update({node_id: 1 for node_id in outgoing[focus_id]})
    unresolved = set(nodes) - set(layers)
    for _ in range(3):
        for node_id in list(unresolved):
            anchors = [item for item in incoming[node_id] | outgoing[node_id] if item in layers]
            if anchors:
                anchor = min(anchors, key=lambda item: abs(layers[item]))
                sign = -1 if layers[anchor] < 0 else 1
                layers[node_id] = layers[anchor] + sign
                unresolved.remove(node_id)
    layers.update({node_id: 1 for node_id in unresolved})

    grouped: dict[int, list[str]] = {}
    for node_id, layer in layers.items():
        grouped.setdefault(layer, []).append(node_id)
    for values in grouped.values():
        values.sort(key=lambda item: str(nodes[item].get("label", item)).casefold())

    width = 1800
    height = max(900, max(len(items) for items in grouped.values()) * 86 + 150)
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        small = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        font = small = ImageFont.load_default()
    min_layer, max_layer = min(grouped), max(grouped)
    span = max(1, max_layer - min_layer)
    positions: dict[str, tuple[int, int]] = {}
    for layer, node_ids in grouped.items():
        x = 150 + int((layer - min_layer) / span * (width - 300))
        spacing = height / (len(node_ids) + 1)
        for index, node_id in enumerate(node_ids, start=1):
            positions[node_id] = (x, int(index * spacing))

    def line_with_arrow(start: tuple[int, int], end: tuple[int, int], dashed: bool) -> None:
        x1, y1 = start
        x2, y2 = end
        if dashed:
            for step in range(0, 100, 12):
                begin, finish = step / 100, min(1, (step + 7) / 100)
                draw.line((x1 + (x2 - x1) * begin, y1 + (y2 - y1) * begin,
                           x1 + (x2 - x1) * finish, y1 + (y2 - y1) * finish), fill="#64748b", width=2)
        else:
            draw.line((x1, y1, x2, y2), fill="#64748b", width=2)
        direction = 1 if x2 >= x1 else -1
        draw.polygon([(x2, y2), (x2 - 11 * direction, y2 - 6), (x2 - 11 * direction, y2 + 6)], fill="#64748b")

    for edge in payload["edges"]:
        source, target = positions[edge["source"]], positions[edge["target"]]
        direction = 1 if target[0] >= source[0] else -1
        start = (source[0] + 125 * direction, source[1])
        end = (target[0] - 125 * direction, target[1])
        line_with_arrow(start, end, edge.get("evidence") in {"inferred_from_rule", "dynamic_group_rule"})
        midpoint = ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2 - 16)
        draw.text(midpoint, str(edge.get("relation", "RELATED_TO")).replace("_", " "), fill="#334155", font=small, anchor="mm")

    colors = {"user": "#0369a1", "domain_user": "#0369a1", "group": "#047857",
              "domain_group": "#047857", "dynamic_group": "#7e22ce", "policy": "#c2410c",
              "confidential_app": "#be123c", "oauth_app": "#be123c", "compartment": "#0e7490",
              "resource_type": "#475569", "domain": "#9d174d"}
    for node_id, (x, y) in positions.items():
        node = nodes[node_id]
        fill = "#0f172a" if node_id in focus_ids else colors.get(node.get("kind"), "#475569")
        draw.rounded_rectangle((x - 125, y - 34, x + 125, y + 34), radius=12, fill=fill,
                               outline="#f59e0b" if node_id == focus_id else fill, width=4 if node_id == focus_id else 1)
        label = "\n".join(textwrap.wrap(str(node.get("label", node_id)), width=27)[:2])
        draw.multiline_text((x, y - 7), label, fill="white", font=font, anchor="mm", align="center", spacing=2)
        draw.text((x, y + 22), str(node.get("kind", "entity")).replace("_", " "), fill="#e2e8f0",
                  font=small, anchor="mm")

    stream = BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def _focus_summary(snapshot: Snapshot, entity_id: str, rows: list[dict[str, Any]]) -> None:
    """Render a compact selected-entity summary beside the connection flow."""
    entity = next(item for item in snapshot.entities if item.id == entity_id)
    st.markdown(f"### {entity.name}")
    st.caption(entity.kind.replace("_", " ").title())
    st.code(entity.id, language=None)
    incoming = sum(item["direction"] == "in" for item in rows)
    outgoing = sum(item["direction"] == "out" for item in rows)
    cols = st.columns(2)
    cols[0].metric("Incoming", incoming, help=TERM_HELP["Incoming"])
    cols[1].metric("Outgoing", outgoing, help=TERM_HELP["Outgoing"])
    if entity.kind == "user":
        st.info(deterministic_summary(policy_analysis(snapshot, entity.id)))
    elif entity.kind == "dynamic_group":
        st.warning("Rule correlations are possible matches, not proven runtime membership.")
        st.code(entity.metadata.get("matching_rule", "Rule unavailable"), language=None)
    elif entity.kind in {"confidential_app", "oauth_app"}:
        st.info(f"{entity.metadata.get('client_type') or 'OAuth'} client in {entity.metadata.get('domain_name') or 'an identity domain'}.")
    elif entity.description:
        st.write(entity.description)


def _follow_focus(target_id: str) -> None:
    """Continue the investigation from one connected entity."""
    st.session_state["relationship_entity_ids"] = [target_id]


def _relationship_view(snapshot: Snapshot) -> None:
    """Render a focused, hierarchical connection investigation workflow."""
    _help_heading("Focused access investigation", "A capped one- or two-hop view around one or more selected entities; it avoids a tenancy-wide graph.")
    st.caption("Select one or more subjects and correlate only the connections relevant to the question.")
    st.markdown(
        '<div class="flow-rail"><div class="flow-step"><b>1 · Choose</b>Find one identity, group, app, or policy.</div>'
        '<div class="flow-step"><b>2 · Correlate</b>Limit relation types and investigation depth.</div>'
        '<div class="flow-step"><b>3 · Verify</b>Follow a connection and inspect its evidence.</div></div>',
        unsafe_allow_html=True,
    )
    entities = sorted(snapshot.entities, key=lambda item: (item.kind, item.name.casefold()))
    preferred = {"user", "domain_user", "group", "domain_group", "confidential_app", "oauth_app",
                 "dynamic_group", "policy", "domain", "compartment"}
    kinds = sorted({item.kind for item in entities if item.kind in preferred})
    type_control, search_control = st.columns([0.34, 0.66])
    selected_kinds = type_control.multiselect("Entity types", kinds,
                                              default=[kind for kind in kinds if kind in {"user", "group", "confidential_app", "dynamic_group"}],
                                              format_func=lambda item: item.replace("_", " ").title())
    search = search_control.text_input("Find a starting subject", placeholder="Name, email, app, group, policy, or OCID…")
    current_focus_ids = st.session_state.get("relationship_entity_ids", [])
    options = [item for item in entities
               if not selected_kinds or item.kind in selected_kinds or item.id in current_focus_ids]
    if search:
        folded = search.casefold()
        options = [item for item in options
                   if item.id in current_focus_ids or folded in json.dumps(asdict(item), default=str).casefold()]
    if not options:
        st.info("No collected entity matches those filters.")
        return
    option_ids = [item.id for item in options]
    retained = [item for item in current_focus_ids if item in option_ids]
    if not retained:
        retained = [option_ids[0]]
    st.session_state["relationship_entity_ids"] = retained
    selected_ids = st.multiselect(
        f"Matching subjects ({len(options)})",
        option_ids,
        format_func=lambda item: _entity_label(next(entity for entity in options if entity.id == item)),
        key="relationship_entity_ids",
        help="Select one or more subjects to correlate their capped local relationship neighborhoods.",
    )
    if not selected_ids:
        st.info("Select at least one matching subject to build the connection flow.")
        return
    selected_entities = [next(item for item in entities if item.id == selected_id) for selected_id in selected_ids]
    focus_key = sha256("|".join(selected_ids).encode("utf-8")).hexdigest()[:12]

    candidate = build_multi_focus_graph(snapshot, selected_ids, depth=2, max_nodes=80, max_edges=250)
    available_relations = sorted({attrs.get("relation", "RELATED_TO") for _, _, attrs in candidate.edges(data=True)})
    relation_control, depth_control, limit_control = st.columns([0.56, 0.2, 0.24])
    selected_relations = relation_control.multiselect(
        "Connection types", available_relations, default=available_relations,
        format_func=lambda item: item.replace("_", " ").title(), key=f"relations-{focus_key}",
        help="Relationship keywords are explained in the IAM terminology glossary in the sidebar.")
    depth = depth_control.segmented_control("Depth", [1, 2], default=2, key=f"depth-{focus_key}",
                                            help=TERM_HELP["Depth"]) or 2
    edge_limit = limit_control.select_slider("Maximum connections", [8, 12, 18, 24, 32], value=18,
                                              key=f"limit-{focus_key}",
                                              help="Caps visible edges so the focused diagram remains readable.")
    graph = build_multi_focus_graph(snapshot, selected_ids, depth=depth,
                                    max_nodes=edge_limit + len(selected_ids),
                                    relations=set(selected_relations), max_edges=edge_limit)

    summary, diagram = st.columns([0.31, 0.69], gap="large")
    with summary:
        if len(selected_entities) == 1:
            _focus_summary(snapshot, selected_ids[0], _relationship_rows(snapshot, selected_ids[0]))
        else:
            st.markdown(f"### {len(selected_entities)} selected subjects")
            comparison = []
            for entity in selected_entities:
                rows = _relationship_rows(snapshot, entity.id)
                comparison.append({"subject": entity.name, "type": entity.kind.replace("_", " "),
                                   "incoming": sum(item["direction"] == "in" for item in rows),
                                   "outgoing": sum(item["direction"] == "out" for item in rows)})
            _table(comparison, ["subject", "type", "incoming", "outgoing"])
        st.caption("Solid lines are direct or parsed evidence. Dashed lines are rule-derived possibilities.")
    with diagram:
        _help_heading("Connection flow", "Arrows show relationship direction. Solid lines are direct or parsed evidence; dashed lines are inferred from rules.", level=3)
        st.caption(f"{graph.number_of_nodes()} entities · {graph.number_of_edges()} visible connections · arrows show relationship direction")
        if graph.number_of_edges():
            st.graphviz_chart(_focused_dot(graph, selected_ids), width="stretch")
            st.iframe(focused_graph_html(graph, selected_ids), height=46, width="stretch")
            map_payload = _focused_graph_payload(graph, selected_ids)
            payload_json = json.dumps(map_payload, indent=2)
            image_col, json_col = st.columns(2)
            image_col.download_button("Download map image", _map_png(payload_json),
                                      file_name="oci-iam-focused-map.png", mime="image/png", width="stretch")
            json_col.download_button("Download map JSON", payload_json,
                                     file_name="oci-iam-focused-map.json", mime="application/json", width="stretch")
        else:
            st.info("No connections match the selected filters.")

    connected_ids = [node_id for node_id in graph.nodes if node_id not in selected_ids]
    if connected_ids:
        follow_col, button_col = st.columns([0.78, 0.22], vertical_alignment="bottom")
        follow_id = follow_col.selectbox("Continue investigation from a connected entity", connected_ids,
                                         format_func=lambda item: _entity_label(next(entity for entity in entities if entity.id == item)),
                                         key=f"follow-{focus_key}")
        button_col.button("Follow connection", type="primary", width="stretch",
                          on_click=_follow_focus, args=(follow_id,),
                          help="Continue the focused investigation from this connected entity.")

    evidence_tab, details_tab = st.tabs(["Connection evidence", "Selected entity details"])
    with evidence_tab:
        graph_rows = []
        entity_map = {item.id: item for item in entities}
        for source, target, attrs in graph.edges(data=True):
            graph_rows.append({"from": entity_map[source].name, "relationship": attrs.get("relation"),
                               "to": entity_map[target].name, "evidence": attrs.get("evidence", "direct"),
                               "from_id": source, "to_id": target})
        _table(graph_rows, ["from", "relationship", "to", "evidence", "from_id", "to_id"])
        st.download_button("Download focused evidence", json.dumps({"focus": [asdict(item) for item in selected_entities], "connections": graph_rows}, indent=2),
                           file_name="oci-iam-focused-evidence.json", mime="application/json")
    with details_tab:
        if len(selected_ids) == 1:
            _entity_inspector(snapshot, selected_ids[0])
        else:
            inspect_id = st.selectbox("Inspect one selected subject", selected_ids,
                                      format_func=lambda item: _entity_label(next(entity for entity in selected_entities if entity.id == item)),
                                      key=f"inspect-{focus_key}")
            _entity_inspector(snapshot, inspect_id)


def _entity_inspector(snapshot: Snapshot, entity_id: str) -> None:
    """Render a concise summary and expandable evidence for one entity."""
    entities = {entity.id: entity for entity in snapshot.entities}
    entity = entities[entity_id]
    st.markdown(f"### {entity.name}")
    st.caption(entity.kind.replace("_", " ").title())
    if entity.description:
        st.write(entity.description)
    st.code(entity.id, language=None)

    if entity.kind == "user":
        analysis = policy_analysis(snapshot, entity.id)
        assignments = [item for item in _relationship_rows(snapshot, entity.id)
                       if item["relationship"] == "ASSIGNED_TO_APP"]
        st.info(deterministic_summary(analysis))
        metrics = st.columns(4)
        metrics[0].metric("Groups", len(analysis["groups"]), help="Directly collected group memberships for this user.")
        metrics[1].metric("Policies", len({item["policy_id"] for item in analysis["applicable_policy_statements"]}),
                          help="Distinct policies containing parsed statements that target one of this user's groups.")
        metrics[2].metric("Permissions", len(analysis["implied_permissions"]), help=TERM_HELP["Inferred"])
        metrics[3].metric("Apps", len(assignments), help=TERM_HELP["ASSIGNED_TO_APP"])
        with st.expander("Open group membership", expanded=True):
            _table(analysis["groups"], ["name", "id"])
        with st.expander("Open inferred permissions", expanded=True):
            for permission in analysis["implied_permissions"]:
                st.markdown(f"- `{permission}`")
            if not analysis["implied_permissions"]:
                st.caption("No standard group statements matched.")
        with st.expander("View policy evidence"):
            _table(analysis["applicable_policy_statements"],
                   ["principal_name", "verb", "resource_type", "scope", "policy_id", "original_text"])
        with st.expander("Open application assignments"):
            _table(assignments, ["related_name", "related_kind", "evidence", "related_id"])
    elif entity.kind == "domain_user":
        groups = [item for item in _relationship_rows(snapshot, entity.id) if item["relationship"] == "MEMBER_OF"]
        apps = [item for item in _relationship_rows(snapshot, entity.id) if item["relationship"] == "ASSIGNED_TO_APP"]
        st.info(f"Identity Domains user with {len(groups)} collected group memberships and {len(apps)} direct app grants.")
        with st.expander("Open groups", expanded=True):
            _table(groups, ["related_name", "related_kind", "related_id"])
        with st.expander("Open application assignments", expanded=True):
            _table(apps, ["related_name", "related_kind", "evidence", "related_id"])
    elif entity.kind in {"group", "domain_group"}:
        members = [entities[item.user_id] for item in snapshot.memberships
                   if item.group_id == entity.id and item.user_id in entities]
        statements = []
        for item in snapshot.statements:
            parsed = parse_policy_statement(item)
            if entity.kind == "group" and parsed.principal_type == "group" and parsed.principal_name and parsed.principal_name.casefold() == entity.name.casefold():
                statements.append(asdict(parsed) | {"policy_id": item.policy_id})
        apps = [item for item in _relationship_rows(snapshot, entity.id) if item["relationship"] == "ASSIGNED_TO_APP"]
        st.write(f"{len(members)} collected users belong to this group. {len(statements)} parsed policy statements target it. {len(apps)} app grants are correlated.")
        with st.expander("Open members", expanded=True):
            _table([asdict(item) for item in members], ["name", "id", "lifecycle_state"])
        with st.expander("Open policy grants", expanded=True):
            _table(statements, ["verb", "resource_type", "scope", "condition", "policy_id", "original_text"])
        with st.expander("Open application assignments"):
            _table(apps, ["related_name", "related_kind", "evidence", "related_id"])
    elif entity.kind == "policy":
        statements = [item for item in snapshot.statements if item.policy_id == entity.id]
        st.write(f"Policy scoped in `{entity.compartment_id or snapshot.tenancy_id}` with {len(statements)} statements.")
        with st.expander("Open policy statements", expanded=True):
            rows = [asdict(parse_policy_statement(item)) for item in statements]
            _table(rows, ["principal_type", "principal_name", "verb", "resource_type", "scope", "condition", "confidence", "original_text"])
    elif entity.kind == "dynamic_group":
        st.warning("Dynamic-group membership is resource-rule based and is not treated as user membership.")
        st.markdown("**Matching rule**")
        st.code(entity.metadata.get("matching_rule", "Rule not collected"), language=None)
        relationships = _relationship_rows(snapshot, entity.id)
        with st.expander("Open correlated policies and rule references", expanded=True):
            _table(relationships, ["relationship", "evidence", "related_name", "related_kind", "related_id"])
    elif entity.kind in {"confidential_app", "oauth_app"}:
        assignments = [item for item in _relationship_rows(snapshot, entity.id)
                       if item["relationship"] == "ASSIGNED_TO_APP"]
        st.info(f"Identity Domains OAuth client ({entity.metadata.get('client_type') or 'type not reported'}) with {len(assignments)} collected grants.")
        metrics = st.columns(3)
        metrics[0].metric("Assignments", len(assignments), help=TERM_HELP["ASSIGNED_TO_APP"])
        metrics[1].metric("Allowed grants", len(entity.metadata.get("allowed_grants", [])),
                          help="OAuth grant types declared as allowed by the application; these are not issued access tokens.")
        metrics[2].metric("Redirect URIs", len(entity.metadata.get("redirect_uris", [])),
                          help="Registered OAuth callback destinations collected as safe application configuration.")
        with st.expander("Open assigned users and groups", expanded=True):
            _table(assignments, ["related_name", "related_kind", "evidence", "related_id"])
        with st.expander("Open safe OAuth configuration"):
            st.json({key: value for key, value in entity.metadata.items()
                     if key in {"domain_id", "domain_name", "active", "client_type", "allowed_grants",
                                "allowed_operations", "redirect_uris", "allow_offline", "is_enterprise_app", "is_managed_app"}})
    elif entity.kind in {"compartment", "tenancy", "domain"}:
        children = [item for item in snapshot.entities if item.compartment_id == entity.id]
        child_counts: dict[str, int] = {}
        for item in children:
            child_counts[item.kind] = child_counts.get(item.kind, 0) + 1
        st.write("Contained snapshot entities: " + (", ".join(f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(child_counts.items())) or "none"))
    with st.expander("Open raw normalized details"):
        st.json(asdict(entity))


def _user_view(snapshot: Snapshot) -> None:
    users = sorted((entity for entity in snapshot.entities if entity.kind == "user"), key=lambda item: item.name.casefold())
    if not users:
        st.info("No users in this snapshot.")
        return
    user = st.selectbox("Select user", users, format_func=_entity_label, key="user_analysis")
    analysis = policy_analysis(snapshot, user.id)
    cols = st.columns(4)
    cols[0].metric("Groups", len(analysis["groups"]), help="Directly collected user-to-group memberships.")
    cols[1].metric("Matching statements", len(analysis["applicable_policy_statements"]), help=TERM_HELP["Parsed"])
    cols[2].metric("Permission summaries", len(analysis["implied_permissions"]), help=TERM_HELP["Inferred"])
    cols[3].metric("Relevant ambiguities", len(analysis["unresolved_ambiguous_statements"]), help=TERM_HELP["Ambiguous"])
    _help_heading("Deterministic summary", "A local evidence-based summary generated without contacting an LLM.")
    st.info(deterministic_summary(analysis))
    _help_heading("Group membership", TERM_HELP["MEMBER_OF"])
    _table(analysis["groups"], ["name", "id", "lifecycle_state"])
    _help_heading("Inferred permissions", TERM_HELP["Inferred"])
    if analysis["implied_permissions"]:
        for permission in analysis["implied_permissions"]:
            st.markdown(f"- `{permission}`")
    else:
        st.caption("No standard group statements matched.")
    with st.expander("Matching policy evidence", expanded=True):
        _table(analysis["applicable_policy_statements"],
               ["principal_name", "verb", "resource_type", "scope", "condition", "policy_id", "original_text"])
    if st.button("Generate OCI GenAI summary", key=f"summarize-{user.id}"):
        with st.spinner("Generating an audit-friendly summary from cached context…"):
            st.session_state[f"summary-{user.id}"] = OCIReasoner().summarize(analysis)
    if summary := st.session_state.get(f"summary-{user.id}"):
        if summary["source"] == "deterministic_fallback":
            st.warning(summary["summary"])
            st.caption(summary.get("warning", "OCI GenAI unavailable"))
        else:
            st.success(summary["summary"])
            st.caption(f"{summary['model_id']} · response {summary['response_id']}")
    st.download_button("Download user analysis JSON", json.dumps(analysis, indent=2),
                       file_name=f"{user.name}-access.json", mime="application/json")


def _policy_view(snapshot: Snapshot) -> None:
    policies = {entity.id: entity for entity in snapshot.entities if entity.kind == "policy"}
    search = st.text_input("Filter policy statements", placeholder="group, resource type, verb, scope…",
                           help="Searches the locally cached original policy text and parsed fields.")
    records = []
    for statement in snapshot.statements:
        parsed = parse_policy_statement(statement)
        policy = policies.get(statement.policy_id)
        record = asdict(parsed) | {"policy": policy.name if policy else statement.policy_id,
                                   "policy_id": statement.policy_id}
        if not search or search.casefold() in json.dumps(record).casefold():
            records.append(record)
    parsed_count = sum(item["confidence"] == "parsed" for item in records)
    cols = st.columns(3)
    cols[0].metric("Visible statements", len(records), help="Policy statements remaining after the current local filter.")
    cols[1].metric("Parsed", parsed_count, help=TERM_HELP["Parsed"])
    cols[2].metric("Ambiguous", len(records) - parsed_count, help=TERM_HELP["Ambiguous"])
    _table(records, ["policy", "principal_type", "principal_name", "verb", "resource_type", "scope", "condition", "confidence", "original_text"])


def _duplicate_view(snapshot: Snapshot) -> None:
    with st.spinner("Comparing normalized names and policy text…"):
        duplicates = find_duplicates(snapshot)
    cols = st.columns(3)
    cols[0].metric("Exact entity names", len(duplicates["exact_entity_name_candidates"]),
                   help="Same normalized name and entity kind. OCIDs remain authoritative, so these are candidates only.")
    cols[1].metric("Exact statements", len(duplicates["exact_policy_statement_candidates"]),
                   help="Policy statement text that becomes identical after case and whitespace normalization.")
    cols[2].metric("Near-name candidates", len(duplicates["near_entity_name_candidates"]),
                   help="Similar labels above the configured string-similarity threshold; no entities are merged automatically.")
    st.caption(duplicates["note"])
    with st.expander("Exact entity-name candidates", expanded=True):
        rows = [item for group in duplicates["exact_entity_name_candidates"] for item in group]
        _table(rows, ["kind", "name", "id", "compartment_id"])
    with st.expander("Exact policy-statement candidates"):
        rows = [{"duplicate_set": index + 1, **item} for index, group in enumerate(duplicates["exact_policy_statement_candidates"]) for item in group]
        _table(rows, ["duplicate_set", "policy_id", "text", "id"])
    with st.expander("Near-name candidates"):
        rows = [{"kind": item["kind"], "left": item["left"]["name"], "right": item["right"]["name"],
                 "similarity": item["similarity"], "left_id": item["left"]["id"], "right_id": item["right"]["id"]}
                for item in duplicates["near_entity_name_candidates"]]
        _table(rows)


def _drift_rows(records: list[dict[str, Any]], change: str, entity_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Make raw drift records readable while retaining their OCI IDs."""
    rows: list[dict[str, Any]] = []
    for item in records:
        record = item.get("after") if change == "changed" else item
        record = record or {}
        if "user_id" in record:
            user = entity_map.get(record["user_id"])
            group = entity_map.get(record["group_id"])
            rows.append({"change": change, "user": user.name if user else record["user_id"],
                         "group": group.name if group else record["group_id"],
                         "user_id": record["user_id"], "group_id": record["group_id"]})
        elif "text" in record:
            rows.append({"change": change, "policy_id": record.get("policy_id"), "statement_id": record.get("id"),
                         "policy_text": record.get("text"),
                         "changed_fields": ", ".join(item.get("changes", {}).keys()) if change == "changed" else ""})
        elif "source_id" in record:
            source = entity_map.get(record["source_id"])
            target = entity_map.get(record["target_id"])
            rows.append({"change": change, "relationship": record.get("kind"), "from": source.name if source else record["source_id"],
                         "to": target.name if target else record["target_id"], "evidence": record.get("evidence"),
                         "changed_fields": ", ".join(item.get("changes", {}).keys()) if change == "changed" else ""})
        else:
            rows.append({"change": change, "name": record.get("name"), "kind": record.get("kind"),
                         "id": record.get("id"), "changed_fields": ", ".join(item.get("changes", {}).keys()) if change == "changed" else ""})
    return rows


def _drift_view(snapshot: Snapshot) -> None:
    """Compare two retained local collections without any new OCI calls."""
    _help_heading("IAM drift", "Compare two saved collections from the same tenancy to review factual inventory changes.")
    st.caption("No OCI request is made. OCI IDs are used as identity keys; this is a review queue, not a runtime authorization decision.")
    records = [item for item in STORE.list_history() if item.tenancy_id == snapshot.tenancy_id]
    unique_records: list[Any] = []
    seen: set[tuple[str, str | None]] = set()
    for item in records:
        key = (item.collected_at, item.source_hash)
        if key not in seen:
            unique_records.append(item)
            seen.add(key)
    if len(unique_records) < 2:
        st.info("Collect at least one more snapshot to compare IAM changes. The portal retains up to five snapshots per tenancy.")
        return
    paths = [str(item.path) for item in unique_records]
    active_path = str(Path(st.session_state.get("active_snapshot_path", STORE.path)))
    current_index = paths.index(active_path) if active_path in paths else 0
    baseline_options = [path for index, path in enumerate(paths) if index != current_index]
    left, right = st.columns(2)
    current_path = left.selectbox("Current collection", paths, index=current_index,
                                 format_func=lambda path: next(item.collected_at for item in unique_records if str(item.path) == path),
                                 help="The later collection is normally selected as the current state.")
    baseline_options = [path for path in paths if path != current_path]
    baseline_path = right.selectbox("Baseline collection", baseline_options, index=0,
                                    format_func=lambda path: next(item.collected_at for item in unique_records if str(item.path) == path))
    current = _load_snapshot(current_path, Path(current_path).stat().st_mtime_ns)
    baseline = _load_snapshot(baseline_path, Path(baseline_path).stat().st_mtime_ns)
    drift = snapshot_drift(baseline, current)
    if drift["unchanged"]:
        st.success("No collected IAM inventory changes were found between these snapshots.")
    else:
        st.warning("Collected IAM changes found. Review original evidence before taking action.")
    metric_columns = st.columns(4)
    for column, (section, label) in zip(metric_columns, [("entities", "Entities"), ("memberships", "Memberships"), ("policy_statements", "Policy statements"), ("relationships", "App/rule links")]):
        counts = drift["counts"][section]
        column.metric(label, sum(counts.values()), delta=f"+{counts['added']} / −{counts['removed']} / ~{counts['changed']}")

    entity_map = {item.id: item for item in [*baseline.entities, *current.entities]}
    sections = [("entities", "Entities"), ("memberships", "Group memberships"),
                ("policy_statements", "Policy statements"), ("relationships", "Application and rule relationships")]
    for section, label in sections:
        records_for_section = [
            row for change in ("added", "removed", "changed")
            for row in _drift_rows(drift[section][change], change, entity_map)
        ]
        with st.expander(f"{label} ({len(records_for_section)} changes)", expanded=bool(records_for_section)):
            _table(records_for_section)
    warnings = drift["collection_warnings"]
    if warnings["added"] or warnings["resolved"]:
        with st.expander("Collection warning changes"):
            _table([{"change": "added", "warning": item} for item in warnings["added"]] +
                   [{"change": "resolved", "warning": item} for item in warnings["resolved"]])
    st.download_button("Download IAM drift report", json.dumps(drift, indent=2),
                       file_name="oci-iam-drift-report.json", mime="application/json")
    st.caption(" · ".join(drift["limitations"]))


def _chat_evidence(evidence: dict[str, Any]) -> None:
    """Render the retriever evidence behind a conversational answer."""
    entities = evidence.get("matched_entities", [])
    statements = evidence.get("matched_policy_statements", [])
    users = evidence.get("matched_user_access", [])
    relationships = evidence.get("matched_relationships", [])
    if entities:
        st.markdown("**Matched entities**")
        _table(entities, ["kind", "name", "id", "compartment_id"])
    if users:
        st.markdown("**Matched user access**")
        rows = [{"user": item["user"]["name"],
                 "groups": ", ".join(group["name"] for group in item["groups"]),
                 "inferred_permissions": "; ".join(item["implied_permissions"])} for item in users]
        _table(rows)
    if statements:
        st.markdown("**Matched policy text**")
        _table(statements, ["policy_id", "text", "id"])
    if relationships:
        st.markdown("**Matched relationships**")
        _table(relationships, ["kind", "evidence", "source_id", "target_id"])
    if evidence.get("duplicate_candidates"):
        duplicates = evidence["duplicate_candidates"]
        st.json({"exact_entity_name_sets": len(duplicates["exact_entity_name_candidates"]),
                 "exact_statement_sets": len(duplicates["exact_policy_statement_candidates"]),
                 "near_name_pairs": len(duplicates["near_entity_name_candidates"])})
    st.caption(" · ".join(evidence.get("limitations", [])))


def _chat_view(snapshot: Snapshot, compact: bool = False) -> None:
    """Conversational retrieval over the local snapshot with visible evidence."""
    _help_heading("Ask OCI IAM", "Retrieves evidence only from the selected cached snapshot; GenAI writes an optional narrative but does not query IAM.")
    st.caption("Answers use the cached snapshot. OCI is not queried again.")
    use_llm = st.toggle("Use GenAI narrative", value=True, key="chat_use_llm")
    users = sorted((entity for entity in snapshot.entities if entity.kind == "user"), key=lambda item: item.name.casefold())
    sample_user = users[0].name if users else "a user"
    suggestions = ([f"What access does {sample_user} appear to have?",
                    "Show dynamic groups and app assignments"] if compact else [
                    "How many users, groups, confidential apps, and policies are collected?",
                    f"What access does {sample_user} appear to have?",
                    "Which dynamic groups and application assignments are correlated?"])
    suggestion_cols = st.columns(len(suggestions))
    pending = None
    for index, suggestion in enumerate(suggestions):
        if suggestion_cols[index].button(suggestion, key=f"suggestion-{index}", width="stretch"):
            pending = suggestion

    st.session_state.setdefault("iam_chat", [])
    if st.session_state["iam_chat"] and st.button("Clear conversation"):
        st.session_state["iam_chat"] = []
        st.rerun()

    for message in st.session_state["iam_chat"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("evidence"):
                with st.expander("View retrieved evidence"):
                    _chat_evidence(message["evidence"])

    question = pending or st.chat_input("Ask about a user, group, app, dynamic group, policy, permission, or duplicate…")
    if question:
        user_message = {"role": "user", "content": question}
        st.session_state["iam_chat"].append(user_message)
        evidence = collection_query(snapshot, question)
        with st.spinner("Searching cached IAM evidence…"):
            answer = OCIReasoner().answer_question(question, evidence) if use_llm else {
                "summary": deterministic_query_answer(evidence), "source": "deterministic_local"
            }
        assistant_message = {"role": "assistant", "content": answer["summary"],
                             "evidence": evidence, "source": answer["source"]}
        st.session_state["iam_chat"].append(assistant_message)
        # Rerender so the completed exchange joins history above the composer.
        st.rerun()


def _chat_popup(snapshot: Snapshot) -> None:
    """Render chat as a persistent bottom-right overlay launcher."""
    with st.container(key="chat_launcher"):
        with st.popover("Ask IAM", icon=":material/chat:", type="primary", width=520,
                        key="iam_chat_popover"):
            _chat_view(snapshot, compact=True)


def _report_view(snapshot: Snapshot) -> None:
    """Build tabular inventory or multi-user reports from the selected snapshot."""
    users = sorted((entity for entity in snapshot.entities if entity.kind == "user"), key=lambda item: item.name.casefold())
    selected_users = st.multiselect(
        "Users to include",
        users,
        format_func=_entity_label,
        help="Select one or more collected users. Leave empty to build an inventory-only report.",
    )
    include_llm = st.checkbox("Include on-demand OCI GenAI summaries", disabled=not selected_users,
                              help="Makes one summary request per selected user using only cached structured evidence.")
    if st.button("Build report", type="primary", width="stretch"):
        analyses = [policy_analysis(snapshot, user.id) for user in selected_users]
        summaries = [OCIReasoner().summarize(access) for access in analyses] if include_llm else []
        payload = report_payload(snapshot, analyses, find_duplicates(snapshot), summaries)
        st.session_state["web-report"] = payload
    if payload := st.session_state.get("web-report"):
        markdown = markdown_report(payload)
        analyses = payload.get("access_analyses") or ([payload["access_analysis"]]
                                                       if payload.get("access_analysis") else [])
        if analyses:
            st.markdown("### Selected-user comparison")
            rows = []
            for access in analyses:
                policies = {item.get("policy_id") for item in access.get("applicable_policy_statements", [])}
                rows.append({
                    "user": access["user"]["name"],
                    "groups": len(access.get("groups", [])),
                    "matching_policies": len(policies),
                    "implied_permissions": len(access.get("implied_permissions", [])),
                    "relevant_ambiguities": len(access.get("unresolved_ambiguous_statements", [])),
                    "confidence": access.get("confidence", "inferred"),
                })
            _table(rows, ["user", "groups", "matching_policies", "implied_permissions",
                          "relevant_ambiguities", "confidence"])
        st.markdown(markdown)
        markdown_col, pdf_col = st.columns(2)
        markdown_col.download_button("Download Markdown", markdown, file_name="oci-iam-user-report.md",
                                     mime="text/markdown", width="stretch")
        pdf_col.download_button("Download PDF", pdf_report(payload), file_name="oci-iam-user-report.pdf",
                                mime="application/pdf", width="stretch")
        with st.expander("Additional machine-readable downloads"):
            json_col, csv_col, excel_col = st.columns(3)
            json_col.download_button("JSON", json.dumps(payload, indent=2), file_name="oci-iam-report.json",
                                     mime="application/json", width="stretch")
            csv_col.download_button("CSV", csv_report(payload), file_name="oci-iam-report.csv",
                                    mime="text/csv", width="stretch")
            excel_col.download_button("Excel", xlsx_report(snapshot, payload), file_name="oci-iam-report.xlsx",
                                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                      width="stretch")


def _raw_view(snapshot: Snapshot) -> None:
    payload = snapshot.to_dict()
    st.json({"tenancy_id": snapshot.tenancy_id, "collected_at": snapshot.collected_at,
             "source_hash": snapshot.source_hash, "entity_count": len(snapshot.entities),
             "membership_count": len(snapshot.memberships), "relationship_count": len(snapshot.relationships),
             "statement_count": len(snapshot.statements), "warnings": snapshot.warnings})
    st.download_button("Download normalized snapshot", json.dumps(payload, indent=2),
                       file_name="oci-iam-snapshot.json", mime="application/json")


def _inventory_view(snapshot: Snapshot) -> None:
    """Combine inventory posture and raw export in one secondary workspace."""
    _overview(snapshot)
    with st.expander("Open snapshot metadata and download"):
        _raw_view(snapshot)


def main() -> None:
    """Render the local IAM collection and exploration application."""
    st.session_state.setdefault("theme_choice", "System")
    _styles(st.session_state["theme_choice"])
    if not _login_gate():
        return
    snapshot = _snapshot()
    _sidebar(snapshot)
    st.markdown(
        """
        <section class="hero">
          <div class="eyebrow">Read-only identity intelligence</div>
          <h1>OCI IAM Plotter</h1>
          <p>Choose one identity, group, application, or policy and follow its evidence path through memberships,
          grants, rules, and scope—without changing cloud resources.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    if snapshot is None:
        st.info("Start a read-only IAM collection from the sidebar. The dashboard will load the cached snapshot when it completes.")
        return
    tabs = st.tabs(["Investigate", "Inventory", "IAM drift", "User analysis", "Policy statements", "Duplicates", "Reports"])
    with tabs[0]:
        _relationship_view(snapshot)
    with tabs[1]:
        _inventory_view(snapshot)
    with tabs[2]:
        _drift_view(snapshot)
    with tabs[3]:
        _user_view(snapshot)
    with tabs[4]:
        _policy_view(snapshot)
    with tabs[5]:
        _duplicate_view(snapshot)
    with tabs[6]:
        _report_view(snapshot)
    _chat_popup(snapshot)
    st.markdown(f'<div class="footer">OCI IAM Plotter {__version__} · local cache · read-only OCI collection</div>',
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()
