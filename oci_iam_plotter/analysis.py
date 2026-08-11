"""Policy parsing, conservative user-access reasoning, and duplicate detection."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Iterable

from .models import Entity, PolicyStatement, Snapshot

_POLICY = re.compile(
    r"^\s*allow\s+(group|dynamic-group)\s+(.+?)\s+to\s+([\w-]+)\s+([\w-]+)(?:\s+in\s+(tenancy|compartment(?:\s+id)?\s+[\w.-]+))?(?:\s+where\s+(.+))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedStatement:
    """Best-effort semantic fields extracted from an OCI IAM policy statement."""

    statement_id: str
    principal_type: str | None
    principal_name: str | None
    verb: str | None
    resource_type: str | None
    scope: str | None
    condition: str | None
    confidence: str
    original_text: str


def parse_policy_statement(statement: PolicyStatement) -> ParsedStatement:
    """Parse a standard ``Allow group ...`` statement without overclaiming semantics."""
    match = _POLICY.match(statement.text)
    if not match:
        return ParsedStatement(statement.id, None, None, None, None, None, None, "ambiguous", statement.text)
    principal_type, principal_name, verb, resource_type, scope, condition = match.groups()
    return ParsedStatement(statement.id, principal_type.lower(), principal_name.strip(), verb.lower(), resource_type.lower(), scope, condition, "parsed", statement.text)


def policy_analysis(snapshot: Snapshot, user_id: str) -> dict:
    """Return evidence-backed, best-effort policy exposure for a given user.

    OCI ultimately evaluates policies, hierarchy, conditions, and service-specific
    permissions. This result therefore reports applicable-looking statements,
    not a proof of authorization.
    """
    entities = {entity.id: entity for entity in snapshot.entities}
    user = entities.get(user_id)
    if not user or user.kind not in {"user", "domain_user"}:
        raise ValueError(f"No user with id {user_id!r} exists in the snapshot")
    group_ids = {m.group_id for m in snapshot.memberships if m.user_id == user_id}
    groups = [entities[group_id] for group_id in sorted(group_ids) if group_id in entities]
    names = {group.name.casefold(): group for group in groups}
    group_names = set(names)
    administrator_roles = []
    # These are OCI's standard administrator group names. Match exactly so a
    # custom group with a loosely similar name is not silently exempted.
    if "administrators" in group_names:
        administrator_roles.append("Administrator")
    if "domain administrators" in group_names:
        administrator_roles.append("Domain administrator")
    applicable: list[dict] = []
    ambiguous: list[dict] = []
    ambiguous_total = 0
    for statement in snapshot.statements:
        parsed = parse_policy_statement(statement)
        record = asdict(parsed) | {"policy_id": statement.policy_id}
        if parsed.confidence == "parsed" and parsed.principal_type == "group" and parsed.principal_name.casefold() in names:
            record["matched_group_id"] = names[parsed.principal_name.casefold()].id
            applicable.append(record)
        elif parsed.confidence == "ambiguous":
            ambiguous_total += 1
            # Only surface unresolved statements that name one of this user's
            # groups. All other ambiguous statements are inventory-level data,
            # not evidence of access for this user.
            folded = statement.text.casefold()
            if any(re.search(rf"\bgroup\s+{re.escape(name)}(?:\s|$)", folded) for name in names):
                ambiguous.append(record)
    permissions = sorted({f"{item['verb']} {item['resource_type']} ({item['scope'] or 'scope not explicit'})" for item in applicable})
    risk = access_risk(applicable, tenancy_administrator="Administrator" in administrator_roles)
    return {
        "user": asdict(user), "groups": [asdict(group) for group in groups],
        "administrator_roles": administrator_roles,
        "applicable_policy_statements": applicable, "implied_permissions": permissions,
        "risk": risk,
        "confidence": "inferred", "limitations": [
            "This is a policy-text inference, not OCI's final authorization decision.",
            "Dynamic groups do not contain users and are not treated as user access.",
            "Conditions, service-specific permissions, policy inheritance, and runtime context can change effective access.",
        ], "unresolved_ambiguous_statements": ambiguous,
        "snapshot_ambiguous_statement_count": ambiguous_total,
    }


def access_risk(statements: list[dict], tenancy_administrator: bool = False) -> dict:
    """Classify potentially powerful policy text with auditable, conservative rules.

    This is a prioritization aid, not an OCI authorization decision.  The rules are
    deliberately visible in the returned evidence so an operator can challenge the
    classification rather than treating a label as a black-box verdict.
    """
    signals: list[dict] = []
    excluded_signals: list[dict] = []
    highest = 0
    sensitive_resources = {"all-resources", "identity", "users", "groups", "policies", "compartments",
                           "tag-namespaces", "vaults", "keys", "secret-family", "database-family"}
    for statement in statements:
        verb = statement.get("verb", "")
        resource = statement.get("resource_type", "")
        scope = statement.get("scope") or "scope not explicit"
        if tenancy_administrator and verb == "manage" and resource == "all-resources" and scope == "tenancy":
            excluded_signals.append({"permission": f"{verb} {resource} ({scope})",
                                     "reason": "Expected for a member of the standard Administrators group"})
            continue
        score = 0
        reasons: list[str] = []
        if verb == "manage":
            score += 55; reasons.append("manage can create, modify, and delete resources")
        elif verb == "use":
            score += 25; reasons.append("use can operate supported resources")
        elif verb == "read":
            score += 8; reasons.append("read can expose inventory or metadata")
        elif verb == "inspect":
            # Inspect is commonly granted tenancy-wide so users can enumerate
            # compartments and navigate the console. Treat it as inventory-only.
            reasons.append("inspect is inventory-only and excluded from risk findings")
        if resource == "all-resources":
            score += 45; reasons.append("all-resources is broad")
        elif resource in sensitive_resources:
            score += 30; reasons.append(f"{resource} is security-sensitive")
        if scope == "tenancy":
            score += 25; reasons.append("tenancy scope is broad")
        elif "compartment" in scope:
            score += 8; reasons.append("compartment scope can still be broad")
        if statement.get("condition"):
            score = max(0, score - 10); reasons.append("a condition may narrow this statement; verify it")
        if verb == "manage" and resource in {"all-resources", "identity", "users", "groups", "policies", "compartments"}:
            reasons.append("may enable IAM administration or indirect privilege escalation; verify separation of duties")
        if score >= 85:
            level = "critical"
        elif score >= 55:
            level = "high"
        elif score >= 25:
            level = "medium"
        else:
            level = "low"
        highest = max(highest, score)
        if score >= 25:
            signals.append({"level": level, "score": score, "permission": f"{verb} {resource} ({scope})",
                            "reasons": reasons, "statement_id": statement.get("statement_id"),
                            "original_text": statement.get("original_text")})
    if highest >= 85:
        level = "critical"
    elif highest >= 55:
        level = "high"
    elif highest >= 25:
        level = "medium"
    else:
        level = "low"
    return {"level": level, "score": highest, "signals": sorted(signals, key=lambda item: item["score"], reverse=True),
            "excluded_signals": excluded_signals,
            "method": "Heuristic policy-text prioritization: verb breadth, resource sensitivity, and scope. Conditions reduce confidence but do not remove the finding. Expected standard tenancy-administrator grants are excluded."}


def tenancy_risk_analysis(snapshot: Snapshot, analyses: list[dict]) -> dict:
    """Summarize report-wide access risk from per-user policy evidence."""
    distribution = {level: 0 for level in ("critical", "high", "medium", "low")}
    for analysis in analyses:
        distribution[analysis["risk"]["level"]] += 1
    flagged = [analysis for analysis in analyses if analysis["risk"]["level"] in {"critical", "high"}]
    top_signals = []
    for analysis in analyses:
        for signal in analysis["risk"]["signals"]:
            roles = analysis.get("administrator_roles", [])
            label = f"\n{', '.join(roles)}" if roles else ""
            top_signals.append({"user_id": analysis["user"]["id"], "user": analysis["user"]["name"] + label,
                                "administrator_roles": roles, **signal})
    top_signals.sort(key=lambda item: item["score"], reverse=True)
    return {"user_count": len(analyses), "distribution": distribution,
            "flagged_users": [{"id": item["user"]["id"], "name": item["user"]["name"],
                               "administrator_roles": item.get("administrator_roles", []),
                               "risk_level": item["risk"]["level"], "risk_score": item["risk"]["score"],
                               "signals": item["risk"]["signals"]} for item in flagged],
            "top_risk_elements": top_signals[:20],
            "method": "Risk levels are evidence-based prioritization labels, not proof of effective OCI authorization."}


def find_duplicates(snapshot: Snapshot, similarity_threshold: float = 0.86) -> dict:
    """Find exact and cautious near-duplicate candidates without merging data."""
    def entity_ref(entity: Entity) -> dict:
        return {"id": entity.id, "name": entity.name, "kind": entity.kind, "compartment_id": entity.compartment_id}

    exact: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entity in snapshot.entities:
        exact[(entity.kind, entity.name.casefold().strip())].append(entity_ref(entity))
    exact_entities = [items for items in exact.values() if len(items) > 1]
    normalized: dict[str, list[dict]] = defaultdict(list)
    for statement in snapshot.statements:
        normalized[re.sub(r"\s+", " ", statement.text.casefold()).strip()].append(asdict(statement))
    exact_statements = [items for items in normalized.values() if len(items) > 1]
    candidates: list[dict] = []
    entities = list(snapshot.entities)
    for index, left in enumerate(entities):
        for right in entities[index + 1:]:
            if left.kind != right.kind or left.name.casefold() == right.name.casefold():
                continue
            score = SequenceMatcher(None, left.name.casefold(), right.name.casefold()).ratio()
            if score >= similarity_threshold:
                candidates.append({"kind": left.kind, "left": entity_ref(left), "right": entity_ref(right), "similarity": round(score, 3)})
    return {"exact_entity_name_candidates": exact_entities, "exact_policy_statement_candidates": exact_statements,
            "near_entity_name_candidates": candidates, "note": "Candidates are not automatic duplicates; OCIDs remain authoritative."}
