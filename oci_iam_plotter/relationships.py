"""Derive conservative cross-entity relationships from normalized IAM evidence."""

from __future__ import annotations

from dataclasses import asdict
import json
import re

from .analysis import parse_policy_statement
from .models import Entity, Relationship, Snapshot

_OCID = re.compile(r"ocid1\.[\w.-]+", re.IGNORECASE)
_RESOURCE_TYPE = re.compile(r"resource\.type\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)


def derive_relationships(snapshot: Snapshot) -> tuple[list[Entity], list[Relationship]]:
    """Return synthetic resource types and evidence-backed derived relationships.

    Policy principal matches are parsed evidence. Dynamic-group rules can name
    OCIDs or resource types; these references do not prove that a resource is a
    member, so they are explicitly labelled as inferred rule references.
    """
    entities = {entity.id: entity for entity in snapshot.entities}
    names: dict[tuple[str, str], str] = {}
    for entity in snapshot.entities:
        names[(entity.kind, entity.name.casefold())] = entity.id
        names[(entity.kind.replace("_", "-"), entity.name.casefold())] = entity.id
    relationships: list[Relationship] = []
    synthetic: dict[str, Entity] = {}

    for statement in snapshot.statements:
        parsed = parse_policy_statement(statement)
        principal_id = names.get((parsed.principal_type or "", (parsed.principal_name or "").casefold()))
        if principal_id:
            relationships.append(Relationship(
                principal_id, statement.policy_id, "GRANTED_BY_POLICY", "parsed_policy_text",
                {key: value for key, value in asdict(parsed).items()
                 if key in {"statement_id", "verb", "resource_type", "scope", "condition", "confidence"}},
            ))

    for entity in snapshot.entities:
        if entity.kind != "dynamic_group":
            continue
        rule = str(entity.metadata.get("matching_rule") or "")
        for ocid in sorted(set(_OCID.findall(rule))):
            if ocid in entities:
                relationships.append(Relationship(
                    entity.id, ocid, "RULE_REFERENCES", "dynamic_group_rule",
                    {"matching_rule": rule, "note": "Reference does not prove runtime membership."},
                ))
        for resource_type in sorted(set(_RESOURCE_TYPE.findall(rule))):
            resource_id = f"resource-type:{resource_type.casefold()}"
            synthetic[resource_id] = Entity(resource_id, resource_type, "resource_type",
                                                   description="Resource type referenced by a dynamic-group matching rule")
            relationships.append(Relationship(
                entity.id, resource_id, "MAY_MATCH_RESOURCE_TYPE", "inferred_from_rule",
                {"matching_rule": rule, "note": "Actual matching depends on each resource's runtime attributes."},
            ))
    return list(synthetic.values()), deduplicate_relationships(relationships)


def deduplicate_relationships(items: list[Relationship]) -> list[Relationship]:
    """Remove repeated edges while retaining materially distinct evidence."""
    unique: dict[tuple[str, str, str, str, str], Relationship] = {}
    for item in items:
        key = (item.source_id, item.target_id, item.kind, item.evidence,
               json.dumps(item.metadata, sort_keys=True, default=str))
        unique[key] = item
    return sorted(unique.values(), key=lambda item: (item.kind, item.source_id, item.target_id))
