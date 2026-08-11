"""OCI Object Storage archive for portable IAM snapshots.

The SDK import is deliberately lazy: local development and unit tests can use
the portal without Object Storage credentials, while the hosted application
uses its resource principal when OCI supplies one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - types only, keeps OCI optional at import time
    from .models import Snapshot
    from .settings import Settings


def _safe_part(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return value[:72] or fallback


def tenancy_label(snapshot: "Snapshot") -> str:
    name = next((entity.name for entity in snapshot.entities
                 if entity.id == snapshot.tenancy_id and entity.name), "tenancy")
    suffix = hashlib.sha256(snapshot.tenancy_id.encode()).hexdigest()[:12]
    return f"{_safe_part(name, 'tenancy')}--{suffix}"


@dataclass(frozen=True)
class BucketSnapshotRecord:
    object_name: str
    tenancy_id: str
    tenancy_name: str
    collected_at: str
    source_hash: str | None


@dataclass(frozen=True)
class BucketReportRecord:
    object_name: str
    tenancy_id: str
    created_at: str


class ObjectSnapshotArchive:
    """Read/write snapshots using API-key (local) or resource-principal (hosted) auth."""

    def __init__(self, bucket_name: str, config_file: str, profile: str, use_resource_principal: bool = False,
                 namespace: str = "", region: str = "", client: Any | None = None) -> None:
        self.bucket_name = bucket_name
        self.config_file = config_file
        self.profile = profile
        self.use_resource_principal = use_resource_principal
        self._namespace = namespace
        self.region = region
        self._client = client

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ObjectSnapshotArchive | None":
        if not settings.object_storage_enabled or not settings.object_storage_bucket:
            return None
        return cls(settings.object_storage_bucket, str(settings.oci_config_file), settings.oci_config_profile,
                   settings.object_storage_resource_principal, settings.object_storage_namespace,
                   settings.object_storage_region)

    def _oci_client(self):
        if self._client is not None:
            return self._client
        import oci
        if self.use_resource_principal:
            signer = oci.auth.signers.get_resource_principals_signer()
            # ObjectStorageClient needs a region or endpoint even when requests are
            # signed with a resource principal. Prefer the explicit app setting,
            # then standard OCI runtime variables, then the signer metadata.
            region = (self.region or os.getenv("OCI_REGION", "") or
                      os.getenv("OCI_RESOURCE_PRINCIPAL_REGION", "") or
                      getattr(signer, "region", ""))
            if not region:
                raise RuntimeError(
                    "Object Storage region is not configured. Set "
                    "OCI_IAM_PLOTTER_OBJECT_STORAGE_REGION."
                )
            self._client = oci.object_storage.ObjectStorageClient(config={"region": region}, signer=signer)
        else:
            config = oci.config.from_file(self.config_file, self.profile)
            self._client = oci.object_storage.ObjectStorageClient(config)
        return self._client

    def _namespace_name(self) -> str:
        if not self._namespace:
            self._namespace = self._oci_client().get_namespace().data
        return self._namespace

    def object_name(self, snapshot: "Snapshot") -> str:
        # Date is its own prefix to keep browsable bucket collections ordered.
        date = _safe_part(snapshot.collected_at.replace(":", "-"), "unknown-date")
        fingerprint = (snapshot.source_hash or "nohash")[:12]
        return f"tenancies/{tenancy_label(snapshot)}/{date}/snapshot-{fingerprint}.json"

    def put(self, snapshot: "Snapshot", payload: dict) -> str:
        object_name = self.object_name(snapshot)
        name = next((entity.name for entity in snapshot.entities
                     if entity.id == snapshot.tenancy_id and entity.name), snapshot.tenancy_id)
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._oci_client().put_object(
            self._namespace_name(), self.bucket_name, object_name, io.BytesIO(data),
            content_type="application/json", opc_meta={
                "tenancy-id": snapshot.tenancy_id, "tenancy-name": name,
                "collected-at": snapshot.collected_at, "source-hash": snapshot.source_hash or "",
            },
        )
        return object_name

    def list(self, limit: int = 250) -> list[BucketSnapshotRecord]:
        response = self._oci_client().list_objects(self._namespace_name(), self.bucket_name,
                                                   prefix="tenancies/", fields="name,timeCreated", limit=limit)
        records: list[BucketSnapshotRecord] = []
        for item in response.data.objects:
            if not item.name.endswith(".json"):
                continue
            try:
                head = self._oci_client().head_object(self._namespace_name(), self.bucket_name, item.name)
                headers = {key.lower(): value for key, value in head.headers.items()}
                tenancy_id = headers.get("opc-meta-tenancy-id", "")
                collected_at = headers.get("opc-meta-collected-at", "")
                if not tenancy_id or not collected_at:
                    continue
                records.append(BucketSnapshotRecord(item.name, tenancy_id,
                    headers.get("opc-meta-tenancy-name", tenancy_id), collected_at,
                    headers.get("opc-meta-source-hash") or None))
            except Exception:
                # A deleted/corrupt object must not make the collection picker unusable.
                continue
        return sorted(records, key=lambda record: record.collected_at, reverse=True)

    def load(self, object_name: str) -> dict:
        response = self._oci_client().get_object(self._namespace_name(), self.bucket_name, object_name)
        try:
            return json.loads(response.data.content.decode("utf-8"))
        finally:
            response.data.close()

    def report_object_name(self, snapshot: "Snapshot") -> str:
        timestamp = _safe_part(datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z").replace(":", "-"), "unknown-date")
        return f"tenancies/{tenancy_label(snapshot)}/reports/{timestamp}/iam-access-risk-report.json"

    def put_report(self, snapshot: "Snapshot", payload: dict) -> str:
        """Persist the canonical report JSON; PDF/Markdown are rendered from this evidence."""
        object_name = self.report_object_name(snapshot)
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._oci_client().put_object(
            self._namespace_name(), self.bucket_name, object_name, io.BytesIO(data), content_type="application/json",
            opc_meta={"tenancy-id": snapshot.tenancy_id, "report-kind": "iam-access-risk",
                      "created-at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        )
        return object_name

    def list_reports(self, tenancy_id: str, limit: int = 3) -> list[BucketReportRecord]:
        response = self._oci_client().list_objects(self._namespace_name(), self.bucket_name,
                                                   prefix="tenancies/", fields="name,timeCreated", limit=250)
        records: list[BucketReportRecord] = []
        for item in response.data.objects:
            if not item.name.endswith("/iam-access-risk-report.json"):
                continue
            try:
                head = self._oci_client().head_object(self._namespace_name(), self.bucket_name, item.name)
                headers = {key.lower(): value for key, value in head.headers.items()}
                if headers.get("opc-meta-tenancy-id") != tenancy_id:
                    continue
                records.append(BucketReportRecord(item.name, tenancy_id,
                    headers.get("opc-meta-created-at") or str(item.time_created)))
            except Exception:
                continue
        return sorted(records, key=lambda record: record.created_at, reverse=True)[:limit]
