"""Read-only OCI Identity API collector using a configurable OCI SDK profile."""

from __future__ import annotations

import configparser
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

from .models import Entity, Membership, PolicyStatement, Relationship, Snapshot
from .relationships import deduplicate_relationships, derive_relationships


class CollectionError(RuntimeError):
    """Raised when a required OCI read operation cannot complete."""


_PROXY_ENVIRONMENT = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def _configure_oci_network() -> None:
    """Use direct OCI API connections unless an operator explicitly enables proxies.

    The OCI SDK inherits proxy variables from its process.  Hosted and direct
    local launches can bypass the shell launcher, so enforce the documented
    safe default at client construction time as well.
    """
    if os.getenv("OCI_IAM_PLOTTER_USE_PROXY", "0") != "1":
        for name in _PROXY_ENVIRONMENT:
            os.environ.pop(name, None)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    """Safely retrieve an OCI SDK model attribute."""
    return getattr(obj, name, default)


class OCICollector:
    """Collect IAM metadata exclusively through OCI SDK GET/list operations.

    The class deliberately exposes no mutating methods. OCI configuration
    defaults to ``~/.oci/config`` and ``DEFAULT`` but callers may select another
    local config file and profile.
    """

    def __init__(self, identity_client: Any, tenancy_id: str, list_all: Callable[..., list[Any]],
                 config: dict[str, Any] | None = None, cleanup: Callable[[], None] | None = None) -> None:
        self.identity = identity_client
        self.tenancy_id = tenancy_id
        self.list_all = list_all
        self.config = config
        self._cleanup = cleanup or (lambda: None)
        self.event_logger: Callable[[str, str], None] | None = None

    def _log(self, message: str, level: str = "info") -> None:
        """Emit credential-safe collection progress when a job listener is attached."""
        if self.event_logger:
            self.event_logger(message, level)

    @classmethod
    def from_default_profile(cls) -> "OCICollector":
        """Create a collector from ``~/.oci/config`` and its DEFAULT profile."""
        return cls.from_profile("~/.oci/config", "DEFAULT")

    @classmethod
    def from_profile(cls, config_file: str | Path = "~/.oci/config", profile_name: str = "DEFAULT") -> "OCICollector":
        """Create a collector from a configurable OCI config path and profile."""
        _configure_oci_network()
        try:
            import oci
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise CollectionError("Install the OCI SDK dependency: pip install oci") from exc
        try:
            config = oci.config.from_file(file_location=str(Path(config_file).expanduser()), profile_name=profile_name)
            oci.config.validate_config(config)
            return cls(oci.identity.IdentityClient(config), config["tenancy"],
                       oci.pagination.list_call_get_all_results, config)
        except Exception as exc:  # OCI emits several configuration exception types
            raise CollectionError(f"Unable to initialize OCI profile {profile_name!r}: {exc}") from exc

    @classmethod
    def from_ephemeral_profile(cls, config_text: str, pem_text: str, profile_name: str = "DEFAULT",
                               security_token_text: str = "", use_security_token: bool = False) -> "OCICollector":
        """Create a collector from browser-supplied credentials kept only for one run.

        OCI's SDK requires file paths for the config and private key. Security-token
        profiles additionally require a token file. All browser-supplied material is
        created in a private temporary directory and removed after the job finishes.
        """
        if not config_text.strip() or not pem_text.strip():
            raise CollectionError("Both an OCI config and private key are required")
        if use_security_token and not security_token_text.strip():
            raise CollectionError("A security token is required when Security Token authentication is selected")
        _configure_oci_network()
        tempdir = TemporaryDirectory(prefix="oci-iam-plotter-")
        root = Path(tempdir.name)
        config_path = root / "config"
        key_path = root / "oci_api_key.pem"
        token_path = root / "security_token"
        try:
            key_path.write_text(pem_text, encoding="utf-8")
            key_path.chmod(0o600)
            if use_security_token:
                token_path.write_text(security_token_text, encoding="utf-8")
                token_path.chmod(0o600)

            # OCI validates key_file while loading the profile, so replace a
            # workstation-specific path before calling oci.config.from_file.
            parser = configparser.RawConfigParser()
            parser.read_string(config_text)
            if profile_name != "DEFAULT" and not parser.has_section(profile_name):
                raise CollectionError(f"OCI config profile {profile_name!r} was not found")
            parser[profile_name]["key_file"] = str(key_path)
            if use_security_token:
                parser[profile_name]["security_token_file"] = str(token_path)
            with config_path.open("w", encoding="utf-8") as stream:
                parser.write(stream)
            config_path.chmod(0o600)

            import oci
            config = oci.config.from_file(file_location=str(config_path), profile_name=profile_name)
            if use_security_token:
                signer = oci.auth.signers.SecurityTokenSigner(
                    security_token_text.strip(), oci.signer.load_private_key_from_file(str(key_path))
                )
                identity_client = oci.identity.IdentityClient(config, signer=signer)
            else:
                oci.config.validate_config(config)
                identity_client = oci.identity.IdentityClient(config)
            return cls(identity_client, config["tenancy"],
                       oci.pagination.list_call_get_all_results, config, cleanup=tempdir.cleanup)
        except Exception as exc:
            tempdir.cleanup()
            raise CollectionError(f"Unable to initialize OCI profile {profile_name!r}: {exc}") from exc

    def close(self) -> None:
        """Remove any temporary browser-supplied credential material."""
        self._cleanup()

    def _all(self, operation: Callable[..., Any], **kwargs: Any) -> list[Any]:
        """Call a paginated OCI list endpoint and return its data list."""
        try:
            return list(self.list_all(operation, **kwargs).data)
        except Exception as exc:
            raise CollectionError(f"OCI read operation {operation.__name__} failed: {exc}") from exc

    @staticmethod
    def _domain_all(operation: Callable[..., Any], **kwargs: Any) -> list[Any]:
        """Read a complete Identity Domains SCIM collection using start indexes."""
        resources: list[Any] = []
        start_index = 1
        while True:
            try:
                page = operation(start_index=start_index, count=1000, **kwargs).data
            except Exception as exc:
                raise CollectionError(f"Identity Domains read {operation.__name__} failed: {exc}") from exc
            batch = list(_value(page, "resources", []) or [])
            resources.extend(batch)
            total = int(_value(page, "total_results", len(resources)) or len(resources))
            if not batch or len(resources) >= total:
                return resources
            start_index += len(batch)

    def collect(self) -> Snapshot:
        """Fetch tenancy-scoped IAM inventory into normalized serializable data."""
        try:
            tenancy = self.identity.get_tenancy(self.tenancy_id).data
        except Exception as exc:
            raise CollectionError(f"Unable to read tenancy metadata: {exc}") from exc

        entities: list[Entity] = [Entity(self.tenancy_id, _value(tenancy, "name", self.tenancy_id), "tenancy")]
        relationships: list[Relationship] = []
        warnings: list[str] = []
        self._log("Reading tenancy-scoped users, groups, and dynamic groups.")
        users = self._all(self.identity.list_users, compartment_id=self.tenancy_id)
        groups = self._all(self.identity.list_groups, compartment_id=self.tenancy_id)
        entities += [self._entity(item, "user") for item in users]
        entities += [self._entity(item, "group") for item in groups]
        dynamic_groups = self._all(self.identity.list_dynamic_groups, compartment_id=self.tenancy_id)
        # Some OCI list responses omit matchingRule. A read-only GET supplies
        # the rule needed for honest resource correlation.
        detailed_dynamic_groups: list[Any] = []
        for item in dynamic_groups:
            if _value(item, "matching_rule") is not None or not hasattr(self.identity, "get_dynamic_group"):
                detailed_dynamic_groups.append(item)
                continue
            try:
                detailed_dynamic_groups.append(self.identity.get_dynamic_group(_value(item, "id")).data)
            except Exception as exc:
                warnings.append(f"Dynamic group {_value(item, 'name', _value(item, 'id'))}: rule unavailable ({exc})")
                detailed_dynamic_groups.append(item)
        entities += [self._entity(item, "dynamic_group", matching_rule=_value(item, "matching_rule"))
                     for item in detailed_dynamic_groups]
        self._log(f"Collected {len(users)} users, {len(groups)} groups, and {len(detailed_dynamic_groups)} dynamic groups.")
        membership_pairs: set[tuple[str, str]] = set()

        # Active compartments provide the hierarchy used for current policy scope.
        compartments = self._all(self.identity.list_compartments, compartment_id=self.tenancy_id,
                                 compartment_id_in_subtree=True, access_level="ACCESSIBLE", lifecycle_state="ACTIVE")
        entities += [self._entity(item, "compartment", compartment_id=_value(item, "compartment_id")) for item in compartments]
        self._log(f"Discovered {len(compartments)} accessible active compartments (including nested compartments).")
        # Domains can be created in a compartment. list_domains has no subtree
        # switch, so enumerate the tenancy plus every accessible descendant
        # compartment exactly as we do for policies.
        domains: list[Any] = []
        if hasattr(self.identity, "list_domains"):
            seen_domain_ids: set[str] = set()
            for compartment_id in [self.tenancy_id, *[item.id for item in compartments]]:
                try:
                    for domain in self._all(self.identity.list_domains, compartment_id=compartment_id):
                        domain_id = _value(domain, "id")
                        if domain_id not in seen_domain_ids:
                            domains.append(domain)
                            seen_domain_ids.add(domain_id)
                except CollectionError as exc:
                    warnings.append(f"Identity Domains in compartment {compartment_id}: {exc}")
            entities += [self._entity(item, "domain", home_region_url=_value(item, "home_region_url"),
                                      home_region=_value(item, "home_region"), domain_type=_value(item, "type"))
                         for item in domains]
            self._log(f"Discovered {len(domains)} Identity Domains across tenancy and accessible compartments.")

        if domains and self.config:
            for domain in domains:
                try:
                    domain_entities, domain_memberships, domain_relationships = self._collect_domain(domain)
                    entities = self._merge_entities(entities, domain_entities)
                    relationships.extend(domain_relationships)
                except CollectionError as exc:
                    warnings.append(f"Domain {_value(domain, 'display_name', _value(domain, 'id'))}: {exc}")
                    domain_memberships = []
                # Domain and classic membership OCIDs overlap in many tenancies.
                membership_pairs.update((item.user_id, item.group_id) for item in domain_memberships)
        # list_policies has no subtree flag. Enumerate the tenancy and each
        # collected compartment explicitly to preserve complete scope evidence.
        policies: list[Any] = []
        for compartment_id in [self.tenancy_id, *[item.id for item in compartments]]:
            scoped_policies = self._all(self.identity.list_policies, compartment_id=compartment_id)
            policies.extend(scoped_policies)
            self._log(f"Read {len(scoped_policies)} policies in scope {compartment_id[-12:]}.")
        entities += [self._entity(item, "policy", compartment_id=_value(item, "compartment_id"), statements=_value(item, "statements", []))
                     for item in policies]
        # OCI requires at least one of user_id/group_id for this endpoint. Group
        # enumeration generally uses fewer calls and each edge is deduplicated.
        for group in groups:
            for item in self._all(self.identity.list_user_group_memberships,
                                  compartment_id=self.tenancy_id, group_id=group.id):
                membership_pairs.add((_value(item, "user_id"), _value(item, "group_id")))
        memberships = [Membership(user_id, group_id) for user_id, group_id in sorted(membership_pairs)]
        self._log(f"Collected {len(memberships)} direct user-to-group memberships.")
        statements = [PolicyStatement(f"{_value(policy, 'id')}#{index}", _value(policy, "id"), text, index)
                      for policy in policies for index, text in enumerate(_value(policy, "statements", []) or [])]
        snapshot = Snapshot(self.tenancy_id, datetime.now(timezone.utc).isoformat(), entities, memberships,
                            statements, relationships=relationships, warnings=warnings)
        synthetic, derived = derive_relationships(snapshot)
        snapshot.entities.extend(item for item in synthetic if item.id not in {entity.id for entity in snapshot.entities})
        snapshot.relationships = deduplicate_relationships([*snapshot.relationships, *derived])
        self._log(f"Derived {len(snapshot.relationships)} evidence correlations from collected metadata.")
        return replace(snapshot, source_hash=None)

    def _collect_domain(self, domain: Any) -> tuple[list[Entity], list[Membership], list[Relationship]]:
        """Collect safe, non-secret Identity Domains data from one domain endpoint."""
        try:
            import oci
            client = oci.identity_domains.IdentityDomainsClient(
                self.config, service_endpoint=_value(domain, "home_region_url")
            )
        except Exception as exc:
            raise CollectionError(f"Unable to initialize Identity Domains client: {exc}") from exc

        domain_id = _value(domain, "id")
        domain_name = _value(domain, "display_name", domain_id)
        self._log(f"Reading Identity Domains SCIM inventory for {domain_name}.")
        users = self._domain_all(client.list_users, attributes=(
            "id,ocid,userName,displayName,description,active,groups,domainOcid,compartmentOcid"))
        groups = self._domain_all(client.list_groups, attributes=(
            "id,ocid,displayName,members,domainOcid,compartmentOcid"))
        apps = self._domain_all(client.list_apps, filter="isOAuthClient eq true", attributes=(
            "id,ocid,name,displayName,description,active,isOAuthClient,clientType,redirectUris,"
            "allowedGrants,allowedOperations,allowOffline,isEnterpriseApp,isManagedApp,domainOcid,compartmentOcid"))
        grants = self._domain_all(client.list_grants, attributes=(
            "id,ocid,grantMechanism,isFulfilled,grantee,app,entitlement,domainOcid,compartmentOcid"))
        self._log(f"Domain {domain_name}: {len(users)} users, {len(groups)} groups, {len(apps)} OAuth apps, {len(grants)} grants.")

        user_ids = {_value(item, "id"): self._domain_entity_id(item, domain_id, "user") for item in users}
        group_ids = {_value(item, "id"): self._domain_entity_id(item, domain_id, "group") for item in groups}
        app_ids = {_value(item, "id"): self._domain_entity_id(item, domain_id, "app") for item in apps}
        entities: list[Entity] = []
        for item in users:
            entities.append(self._domain_entity(item, "domain_user", domain_id, domain_name,
                                                username=_value(item, "user_name"), active=_value(item, "active"),
                                                scim_id=_value(item, "id")))
        for item in groups:
            entities.append(self._domain_entity(item, "domain_group", domain_id, domain_name,
                                                active=_value(item, "active"), scim_id=_value(item, "id")))
        for item in apps:
            client_type = str(_value(item, "client_type", "") or "").casefold()
            kind = "confidential_app" if client_type == "confidential" else "oauth_app"
            entities.append(self._domain_entity(
                item, kind, domain_id, domain_name, scim_id=_value(item, "id"),
                active=_value(item, "active"), client_type=_value(item, "client_type"),
                allowed_grants=_plain_list(_value(item, "allowed_grants")),
                allowed_operations=_plain_list(_value(item, "allowed_operations")),
                redirect_uris=_plain_list(_value(item, "redirect_uris")),
                allow_offline=_value(item, "allow_offline"),
                is_enterprise_app=_value(item, "is_enterprise_app"),
                is_managed_app=_value(item, "is_managed_app"),
            ))

        memberships: set[tuple[str, str]] = set()
        for group in groups:
            group_id = group_ids.get(_value(group, "id"))
            for member in _value(group, "members", []) or []:
                user_id = user_ids.get(_value(member, "value"))
                if user_id and group_id:
                    memberships.add((user_id, group_id))

        relationships: list[Relationship] = []
        for grant in grants:
            grantee = _value(grant, "grantee")
            app_ref = _value(grant, "app")
            grantee_scim_id = _value(grantee, "value")
            app_scim_id = _value(app_ref, "value")
            grantee_id = user_ids.get(grantee_scim_id) or group_ids.get(grantee_scim_id)
            app_id = app_ids.get(app_scim_id)
            if grantee_id and app_id:
                relationships.append(Relationship(
                    grantee_id, app_id, "ASSIGNED_TO_APP", "identity_domains_grant",
                    {"grant_id": _value(grant, "id"), "grant_mechanism": _value(grant, "grant_mechanism"),
                     "fulfilled": _value(grant, "is_fulfilled"),
                     "entitlement": _safe_reference(_value(grant, "entitlement")),
                     "domain_id": domain_id},
                ))
        return entities, [Membership(*pair) for pair in sorted(memberships)], relationships

    @staticmethod
    def _domain_entity_id(item: Any, domain_id: str, suffix: str) -> str:
        return _value(item, "ocid") or f"{domain_id}:{suffix}:{_value(item, 'id')}"

    @classmethod
    def _domain_entity(cls, item: Any, kind: str, domain_id: str, domain_name: str,
                       **metadata: Any) -> Entity:
        suffix = "app" if kind in {"confidential_app", "oauth_app"} else kind.removeprefix("domain_")
        return Entity(
            id=cls._domain_entity_id(item, domain_id, suffix),
            name=_value(item, "display_name", _value(item, "name", _value(item, "user_name", _value(item, "id")))),
            kind=kind, description=_value(item, "description"),
            compartment_id=_value(item, "compartment_ocid"), lifecycle_state=None,
            metadata={"domain_id": domain_id, "domain_name": domain_name,
                      **{key: value for key, value in metadata.items() if value is not None}},
        )

    @staticmethod
    def _merge_entities(existing: list[Entity], additions: list[Entity]) -> list[Entity]:
        """Merge SCIM enrichment into classic users/groups that share an OCID."""
        merged = {item.id: item for item in existing}
        for item in additions:
            current = merged.get(item.id)
            if current and current.kind in {"user", "group"} and item.kind in {"domain_user", "domain_group"}:
                merged[item.id] = replace(current, description=current.description or item.description,
                                          metadata={**current.metadata, **item.metadata, "identity_domain_enriched": True})
            elif not current:
                merged[item.id] = item
        return list(merged.values())

    @staticmethod
    def _entity(item: Any, kind: str, **metadata: Any) -> Entity:
        """Normalize a common OCI IAM summary model without retaining SDK models."""
        return Entity(
            id=_value(item, "id"), name=_value(item, "name", _value(item, "display_name", _value(item, "id"))), kind=kind,
            description=_value(item, "description"), compartment_id=metadata.pop("compartment_id", _value(item, "compartment_id")),
            lifecycle_state=_value(item, "lifecycle_state"), metadata={key: value for key, value in metadata.items() if value is not None},
        )


def _plain_list(value: Any) -> list[Any]:
    """Return JSON-safe scalar values from a safe, explicitly selected SCIM field."""
    return [item if isinstance(item, (str, int, float, bool)) else str(item) for item in (value or [])]


def _safe_reference(value: Any) -> dict[str, Any] | None:
    """Serialize only identifiers and labels from a nested SCIM reference."""
    if value is None:
        return None
    return {key: item for key in ("value", "display", "type") if (item := _value(value, key)) is not None}
