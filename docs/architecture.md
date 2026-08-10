# Architecture and data flow

The portal separates collection from analysis. A collection uses OCI SDK read operations and produces a portable normalized JSON snapshot. All maps, filters, duplicate analysis, drift, reports, and chat retrieval work from the selected cached snapshot rather than making further identity calls.

## Collection coverage

Collection includes tenancy metadata, compartments and subcompartments, classic IAM users and groups, Identity Domains users and groups where permitted, memberships, dynamic groups and matching rules, policies and policy statements, confidential/OAuth applications, and grants. Identity Domains collection is best effort; unavailable optional sources become snapshot warnings.

## Access Map

The map builds a capped one- or two-hop graph around selected entities. Solid links represent direct or parsed evidence. Dashed links represent cautious rule-derived possibilities. Layouts include evidence clusters, left-to-right hierarchy, and an expandable tree.

## Ask IAM

Ask IAM runs constrained retrieval over entities, policy statements, relationships, user access evidence, and duplicate candidates. It passes compact retrieved evidence to OCI Generative AI for a narrative answer and exposes tool/evidence details in the chat. If the model is unavailable, it returns a deterministic answer from the same evidence.

## Snapshot retention

The local working cache retains five timestamped snapshots per tenancy. Object Storage retains durable collections and is used by the explicit bucket collection picker. Snapshot hashes are SHA-256 hashes of IAM content excluding collection time, so no-op refreshes share a content fingerprint.
