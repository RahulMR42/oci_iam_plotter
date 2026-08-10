"""Serializable normalized models used by the local snapshot and analysis layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Entity:
    """A normalized OCI IAM entity."""

    id: str
    name: str
    kind: str
    description: str | None = None
    compartment_id: str | None = None
    lifecycle_state: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Membership:
    """A user-to-group membership relationship."""

    user_id: str
    group_id: str


@dataclass(frozen=True)
class PolicyStatement:
    """A policy statement preserved verbatim and annotated with its policy."""

    id: str
    policy_id: str
    text: str
    index: int


@dataclass(frozen=True)
class Relationship:
    """A normalized evidence or inferred relationship between two entities."""

    source_id: str
    target_id: str
    kind: str
    evidence: str = "direct"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Snapshot:
    """Portable collection snapshot; no SDK response objects are persisted."""

    tenancy_id: str
    collected_at: str
    entities: list[Entity] = field(default_factory=list)
    memberships: list[Membership] = field(default_factory=list)
    statements: list[PolicyStatement] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_hash: str | None = None
    schema_version: int = 2

    @classmethod
    def empty(cls, tenancy_id: str) -> "Snapshot":
        return cls(tenancy_id=tenancy_id, collected_at=datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Snapshot":
        return cls(
            tenancy_id=data["tenancy_id"], collected_at=data["collected_at"],
            entities=[Entity(**item) for item in data.get("entities", [])],
            memberships=[Membership(**item) for item in data.get("memberships", [])],
            statements=[PolicyStatement(**item) for item in data.get("statements", [])],
            relationships=[Relationship(**item) for item in data.get("relationships", [])],
            warnings=list(data.get("warnings", [])),
            source_hash=data.get("source_hash"), schema_version=data.get("schema_version", 1),
        )
