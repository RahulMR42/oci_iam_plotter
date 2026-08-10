# Security and IAM boundaries

## Read-only boundary

The collector is limited to OCI SDK `get_*` and `list_*` operations. It does not create, update, delete, or attach OCI resources, and it never mutates IAM policies.

## Credentials and sensitive data

Browser-supplied OCI config, private-key, and security-token material is written only to owner-only temporary files for the collection lifetime and is removed in a `finally` path. It is not added to snapshots, reports, logs, or chat evidence.

Snapshots can contain IAM names, OCIDs, policy statements, dynamic rules, and relationships. Treat the local cache, Object Storage bucket, report downloads, and map exports as sensitive audit material.

## Analysis limits

Policy parsing and relationship correlation are evidence aids, not proof of effective authorization. OCI authorization can depend on compartment ancestry, policy conditions, domain behavior, service-specific verb expansion, request context, resource state, cross-tenancy controls, and policies unavailable to the collector.

Dynamic-group matching is especially conservative: a collected rule reference is not proof of live runtime membership. Duplicate findings are candidates only; OCIDs remain authoritative and the tool never merges or deletes entities.
