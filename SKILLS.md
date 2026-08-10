# OCI IAM Plotter skills

The application keeps collection and reasoning deterministic. The LLM is used only for optional narrative output.

## Collection skill

- Reads OCI IAM and Identity Domains through an OCI SDK config/profile, defaulting to `~/.oci/config` and `DEFAULT`.
- Collects tenancy, compartments, domains, users, groups, memberships, dynamic groups, policies, OAuth/confidential apps, and grants.
- Requests allowlisted Identity Domains attributes and never requests client secrets or credentials.
- Caches a normalized, content-hashed snapshot for local reuse and archives every successful web collection to `bucket_iam_plotter`.
- Accepts a selectable OCI SDK config path and profile, defaulting to `~/.oci/config` and `DEFAULT`.
- Retains the newest five timestamped collections per tenancy in the local working cache; the Object Storage collection picker can activate any durable archived collection.

## Correlation skill

- Connects users to groups and Identity Domains principals to application grants.
- Connects groups and dynamic groups to policies through parsed policy evidence.
- Identifies dynamic-group rule references to collected OCIDs and resource types.
- Labels rule-derived possibilities separately from direct evidence.

## Access Map skill

- Starts from one or more selected entities and unions their capped one- or two-hop connection flows.
- Highlights all selected subjects and deduplicates repeated nodes and edges.
- Filters by relationship kind and supports follow-the-connection drill-down.
- Exposes per-subject summaries, normalized evidence, metadata, and explicit confidence limitations.
- Presents the focused diagram in the **Access Map** workspace with pan, zoom, fit-to-home, separate-tab, PNG/PDF export, and expandable-tree controls.

## Reporting skill

- Accepts zero, one, or multiple selected users for inventory or comparative access reporting.
- Produces tabular Markdown and paginated PDF reports with comparison and per-user evidence sections.
- Produces structured JSON, CSV, and Excel-compatible `.xlsx` reports for downstream analysis.
- Exports the focused connection map as PNG and JSON.
- Generates per-user access summaries, confidence/limitations, and duplicate/overlap candidates.

## Conversation skill

- Retrieves compact evidence from the local snapshot for each question.
- Retrieves relevant cached evidence first, then uses OCI's OpenAI-compatible Responses API for an evidence-grounded narrative when configured.
- Falls back to deterministic answers if the model is unavailable.
- Keeps conversation history above a bottom-anchored question composer in the popup.

## Snapshot storage skill

- Writes normalized snapshots to the configured cache directory and archives durable copies to `bucket_iam_plotter` as `tenancies/<tenancy-name-and-id>/<collection-date>/`.
- Uses the local OCI user principal for archive access and the OCI Generative AI hosted application's resource principal when deployed.
- Keeps the latest snapshot plus at most five timestamped working collections per tenancy locally, without pruning older bucket collections.
- Reuses the selected cached snapshot for analysis, graphs, chat retrieval, summaries, and reports.
- Never persists OCI SDK signers, API private keys, security tokens, OAuth client secrets, or LLM API keys in report data.

## Safety boundary

Every OCI operation is a read operation. The application provides no create, update, delete, or policy mutation capability. Correlations are audit leads, not proof of OCI runtime authorization. The local UI is password-gated; an unconfigured installation generates a strong random password rather than using a hardcoded shared secret.
