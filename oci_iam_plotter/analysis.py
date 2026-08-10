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
    if not user or user.kind != "user":
        raise ValueError(f"No user with id {user_id!r} exists in the snapshot")
    group_ids = {m.group_id for m in snapshot.memberships if m.user_id == user_id}
    groups = [entities[group_id] for group_id in sorted(group_ids) if group_id in entities]
    names = {group.name.casefold(): group for group in groups}
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
    return {
        "user": asdict(user), "groups": [asdict(group) for group in groups],
        "applicable_policy_statements": applicable, "implied_permissions": permissions,
        "confidence": "inferred", "limitations": [
            "This is a policy-text inference, not OCI's final authorization decision.",
            "Dynamic groups do not contain users and are not treated as user access.",
            "Conditions, service-specific permissions, policy inheritance, and runtime context can change effective access.",
        ], "unresolved_ambiguous_statements": ambiguous,
        "snapshot_ambiguous_statement_count": ambiguous_total,
    }


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
