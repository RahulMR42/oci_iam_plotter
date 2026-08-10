"""Command-line interface for read-only OCI IAM Plotter workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from .analysis import find_duplicates, policy_analysis
from .collector import CollectionError, OCICollector
from .graph import build_graph, export_graph, graph_data
from .reporting import report_payload, write_report
from .store import SnapshotStore
from .summarizer import OCIReasoner


def _store(args: argparse.Namespace) -> SnapshotStore:
    return SnapshotStore(Path(args.cache_dir))


def _dump(data: dict) -> None:
    print(json.dumps(data, indent=2, default=str))


def command_collect(args: argparse.Namespace) -> None:
    """Collect and cache the latest read-only IAM snapshot."""
    snapshot = OCICollector.from_profile(args.oci_config_file, args.oci_profile).collect()
    path = _store(args).save(snapshot)
    _dump({"status": "collected", "snapshot_path": str(path), "tenancy_id": snapshot.tenancy_id,
           "entities": len(snapshot.entities), "memberships": len(snapshot.memberships),
           "relationships": len(snapshot.relationships), "policy_statements": len(snapshot.statements),
           "warnings": snapshot.warnings,
           "read_only": True})


def command_build_graph(args: argparse.Namespace) -> None:
    """Build an exportable graph JSON artifact from the cache."""
    graph = build_graph(_store(args).load())
    output = export_graph(graph, Path(args.output), args.focus)
    _dump({"graph_path": str(output), "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()})


def command_visualize(args: argparse.Namespace) -> None:
    """Export an interactive graph view from cached data."""
    graph = build_graph(_store(args).load())
    output = export_graph(graph, Path(args.output), args.focus_user or args.focus)
    _dump({"visualization_path": str(output), "focus": args.focus_user or args.focus})


def command_analyze_user(args: argparse.Namespace) -> None:
    """Print structured, conservative access inference for one cached user."""
    _dump(policy_analysis(_store(args).load(), args.user_id))


def command_find_duplicates(args: argparse.Namespace) -> None:
    """Print entity and statement duplicate candidates from cached data."""
    _dump(find_duplicates(_store(args).load(), args.threshold))


def command_summarize(args: argparse.Namespace) -> None:
    """Generate a local-context access summary, using OCI GenAI only on demand."""
    access = policy_analysis(_store(args).load(), args.user_id)
    _dump(OCIReasoner(model_id=args.model_id).summarize(access))


def command_report(args: argparse.Namespace) -> None:
    """Create a portable report sourced entirely from the local snapshot."""
    snapshot = _store(args).load()
    access = policy_analysis(snapshot, args.focus_user) if args.focus_user else None
    summary = OCIReasoner(model_id=args.model_id).summarize(access) if args.focus_user and args.with_summary else None
    payload = report_payload(snapshot, access, find_duplicates(snapshot), summary)
    output = write_report(payload, Path(args.output), snapshot)
    _dump({"report_path": str(output), "format": output.suffix.lstrip("."), "focus_user": args.focus_user})


def parser() -> argparse.ArgumentParser:
    """Build the CLI parser and its subcommands."""
    root = argparse.ArgumentParser(description="OCI IAM Plotter (read-only OCI IAM analysis)")
    root.add_argument("--cache-dir", default=".iam-plotter-cache", help="Local snapshot directory (default: %(default)s)")
    root.add_argument("--oci-config-file", default="~/.oci/config", help="OCI SDK config path (default: %(default)s)")
    root.add_argument("--oci-profile", default="DEFAULT", help="OCI SDK profile for collection (default: %(default)s)")
    commands = root.add_subparsers(dest="command", required=True)
    def add(name: str, func: Callable, **kwargs: object) -> argparse.ArgumentParser:
        child = commands.add_parser(name, **kwargs)
        child.set_defaults(func=func)
        return child
    add("collect", command_collect, help="Read OCI IAM data and cache a snapshot")
    graph = add("build-graph", command_build_graph, help="Export graph JSON or HTML from cache")
    graph.add_argument("--output", default="iam-graph.json")
    graph.add_argument("--focus", help="Optional entity OCID/node id")
    viz = add("visualize", command_visualize, help="Export interactive HTML (or graph JSON)")
    viz.add_argument("--output", default="iam-graph.html")
    viz.add_argument("--focus-user")
    viz.add_argument("--focus", help="Optional entity OCID/node id")
    user = add("analyze-user", command_analyze_user, help="Infer policy exposure for a cached user")
    user.add_argument("--user-id", required=True)
    dup = add("find-duplicates", command_find_duplicates, help="Find duplicate and near-duplicate candidates")
    dup.add_argument("--threshold", type=float, default=0.86)
    summ = add("summarize", command_summarize, help="Ask OCI GenAI to summarize cached user analysis")
    summ.add_argument("--user-id", required=True)
    summ.add_argument("--model-id", default="xai.grok-4", help="OCI-hosted OpenAI or xAI model id")
    report = add("report", command_report, help="Write a JSON, Markdown, PDF, CSV, or Excel report")
    report.add_argument("--output", default="iam-report.md", help="Output .md, .pdf, .json, .csv, or .xlsx file")
    report.add_argument("--focus-user")
    report.add_argument("--with-summary", action="store_true")
    report.add_argument("--model-id", default="xai.grok-4", help="OCI-hosted OpenAI or xAI model id")
    return root


def main(argv: list[str] | None = None) -> None:
    """Run CLI and map expected operational errors to a clean exit status."""
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except (CollectionError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc), "read_only": True}), file=sys.stderr)
        raise SystemExit(2) from exc
