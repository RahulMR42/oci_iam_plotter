"""Evidence retrieval and conversational answers over a cached IAM snapshot."""

from __future__ import annotations

from dataclasses import asdict
import json
import re
from typing import Any

from .analysis import find_duplicates, policy_analysis
from .models import Snapshot

_STOP_WORDS = {"a", "an", "and", "are", "can", "does", "for", "from", "has", "have", "iam", "in",
               "is", "me", "of", "on", "show", "tell", "the", "to", "what", "which", "who", "with"}
_GROUP_KINDS = {"group", "domain_group"}


def group_name_contains_query(snapshot: Snapshot, question: str) -> dict[str, Any] | None:
    """Recognize an explicit request to list groups by a name fragment.

    This is deliberately deterministic: an exact inventory listing should not
    be rewritten, truncated, or guessed by the language model.
    """
    folded = question.casefold()
    if not re.search(r"\bgroups?\b", folded) or not re.search(r"\bcontain(?:s)?\b", folded):
        return None
    quoted = re.findall(r"[\"']([^\"']+)[\"']", question)
    if quoted:
        fragment = quoted[-1].strip()
    else:
        match = re.search(r"\bcontain(?:s)?\s+(?:a\s+)?(?:name\s+)?([\w.-]+)\b", folded)
        fragment = match.group(1).strip() if match else ""
    if not fragment:
        return None
    matches = [entity for entity in snapshot.entities
               if entity.kind in _GROUP_KINDS and fragment.casefold() in entity.name.casefold()]
    matches.sort(key=lambda entity: (entity.name.casefold(), entity.kind, entity.id))
    shown = matches[:250]
    suffix = "" if len(matches) <= len(shown) else f" Showing the first {len(shown)}."
    if shown:
        labels = "; ".join(f"{entity.name} ({entity.kind})" for entity in shown)
        answer = f'Groups with a name containing "{fragment}" ({len(matches)}): {labels}.{suffix}'
    else:
        answer = f'No collected groups have a name containing "{fragment}".'
    return {"fragment": fragment, "total": len(matches), "entities": shown, "answer": answer}


def collection_query(snapshot: Snapshot, question: str, limit: int = 18) -> dict[str, Any]:
    """Retrieve compact, structured evidence relevant to a natural-language query."""
    folded = question.casefold()
    structured_group_query = group_name_contains_query(snapshot, question)
    terms = [term for term in re.findall(r"[\w@./:-]+", folded) if len(term) > 2 and term not in _STOP_WORDS]
    counts: dict[str, int] = {}
    for entity in snapshot.entities:
        counts[entity.kind] = counts.get(entity.kind, 0) + 1

    scored_entities: list[tuple[int, Any]] = []
    for entity in snapshot.entities:
        haystack = f"{entity.name} {entity.id} {entity.kind} {entity.description or ''}".casefold()
        score = sum(3 if term in entity.name.casefold() else 1 for term in terms if term in haystack)
        if entity.name.casefold() in folded or entity.id.casefold() in folded:
            score += 10
        if score:
            scored_entities.append((score, entity))
    matched_entities = [entity for _, entity in sorted(scored_entities, key=lambda item: (-item[0], item[1].name.casefold()))[:limit]]

    scored_statements: list[tuple[int, Any]] = []
    for statement in snapshot.statements:
        text = statement.text.casefold()
        score = sum(1 for term in terms if term in text)
        if score:
            scored_statements.append((score, statement))
    matched_statements = [statement for _, statement in sorted(scored_statements, key=lambda item: -item[0])[:limit]]

    matched_ids = {entity.id for entity in matched_entities}
    scored_relationships: list[tuple[int, Any]] = []
    for relationship in snapshot.relationships:
        haystack = json.dumps(asdict(relationship), default=str).casefold()
        score = sum(1 for term in terms if term in haystack)
        if relationship.source_id in matched_ids or relationship.target_id in matched_ids:
            score += 5
        if score:
            scored_relationships.append((score, relationship))
    matched_relationships = [item for _, item in sorted(
        scored_relationships, key=lambda pair: (-pair[0], pair[1].kind)
    )[:limit]]

    users = []
    for entity in matched_entities:
        if entity.kind == "user" and len(users) < 3:
            users.append(policy_analysis(snapshot, entity.id))
    duplicates = find_duplicates(snapshot) if any(word in folded for word in ("duplicate", "overlap", "redundant", "similar")) else None
    result = {
        "question": question,
        "snapshot": {"tenancy_id": snapshot.tenancy_id, "collected_at": snapshot.collected_at},
        "inventory": counts,
        "matched_entities": [asdict(entity) for entity in matched_entities],
        "matched_policy_statements": [asdict(statement) for statement in matched_statements],
        "matched_relationships": [asdict(item) for item in matched_relationships],
        "matched_user_access": users,
        "duplicate_candidates": duplicates,
        "limitations": ["Evidence comes from the cached snapshot, not a new OCI query.",
                        "Policy matches are best-effort and are not final OCI authorization decisions."],
    }
    if structured_group_query:
        result["matched_entities"] = [asdict(entity) for entity in structured_group_query["entities"]]
        result["structured_query"] = {"intent": "list_groups_name_contains",
                                      "name_fragment": structured_group_query["fragment"],
                                      "total": structured_group_query["total"]}
        result["direct_answer"] = structured_group_query["answer"]
    return result


def run_iam_agent(snapshot: Snapshot, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Run a constrained, read-only evidence agent over one cached snapshot.

    Planning is deterministic and every tool is local to the selected snapshot.
    The language model may summarize tool output, but never selects OCI actions.
    """
    history = history or []
    resolved = question
    folded = question.casefold()
    prior_questions = [item.get("text", "") for item in history if item.get("role") == "user"][-6:]
    if ("those groups" in folded or "them" in folded) and "group" in folded and not re.findall(r"[\"']([^\"']+)[\"']", question):
        for prior in reversed(prior_questions):
            quoted = re.findall(r"[\"']([^\"']+)[\"']", prior)
            if "group" in prior.casefold() and quoted:
                resolved = f'List all groups contain a name "{quoted[-1]}"'
                break
    evidence = collection_query(snapshot, resolved)
    tools = ["snapshot_inventory"]
    if evidence.get("structured_query"):
        tools.append("list_groups_by_name")
    else:
        tools.append("search_cached_entities")
        if evidence.get("matched_policy_statements"):
            tools.append("search_policy_statements")
        if evidence.get("matched_relationships"):
            tools.append("find_relationships")
        if evidence.get("matched_user_access"):
            tools.append("analyze_user_access")
        if evidence.get("duplicate_candidates") is not None:
            tools.append("find_duplicate_candidates")
    evidence["agent"] = {
        "mode": "constrained_cached_evidence",
        "resolved_question": resolved,
        "tools": tools,
        "verified": True,
        "scope": {"tenancy_id": snapshot.tenancy_id, "collected_at": snapshot.collected_at},
    }
    evidence["conversation_context"] = [item for item in history[-6:] if item.get("role") in {"user", "assistant"}]
    return evidence


def deterministic_query_answer(evidence: dict[str, Any]) -> str:
    """Return a concise fallback answer when OCI GenAI is unavailable."""
    if evidence.get("direct_answer"):
        return evidence["direct_answer"]
    users = evidence["matched_user_access"]
    if users:
        user = users[0]
        groups = ", ".join(item["name"] for item in user["groups"]) or "no groups"
        permissions = "; ".join(user["implied_permissions"]) or "no matched standard policy permissions"
        return f"{user['user']['name']} belongs to {groups}. Inferred access: {permissions}. This is cached policy evidence, not a final authorization decision."
    entities = evidence["matched_entities"]
    if entities:
        labels = ", ".join(f"{item['name']} ({item['kind']})" for item in entities[:6])
        relationship_count = len(evidence.get("matched_relationships", []))
        return f"The closest cached matches are: {labels}. {relationship_count} related evidence records were found; open the evidence for details."
    counts = evidence["inventory"]
    return "No direct name or policy-text match was found. The snapshot contains " + ", ".join(
        f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(counts.items())) + "."
