# OCI IAM Plotter

OCI IAM Plotter is a local, read-only Python application for collecting OCI IAM metadata once, analyzing the cached snapshot, visualizing relationships, and producing audit-friendly user access reports.

The collector contains only OCI SDK `get_*` and `list_*` calls. It never creates, updates, or deletes OCI resources. Analysis is intentionally conservative: policy exposure is inferred from collected group membership and policy text, while OCI remains the authority for runtime authorization.

## Capabilities

- Collects tenancy metadata, compartments, classic and Identity Domains users/groups, memberships, dynamic groups and their detailed matching rules, policies, policy statements, OAuth/confidential apps, and app grants.
- Requests an explicit safe Identity Domains attribute allowlist. Client secrets, hashed secrets, credentials, and tokens are never requested or persisted.
- Normalizes OCI SDK models into a portable JSON snapshot with a semantic content hash.
- Provides a focused choose → correlate → verify investigation flow with multi-subject selection, a capped hierarchical connection diagram, evidence filters, and follow-the-connection drill-down; full graph export remains an optional CLI artifact.
- The System theme inherits the active Streamlit palette; the checked-in local default is dark.
- Includes Light and Simple light palettes alongside System, Dark, Ocean, and High contrast themes.
- Downloads the visible focused map as PNG or structured JSON.
- Analyzes each selected user's group memberships and matching standard `Allow group ...` policy statements.
- Detects exact names, exact normalized policy statements, and cautious near-name candidates.
- Compares two retained snapshots from the same tenancy to produce an exportable IAM inventory drift review, including entity, membership, policy-statement, relationship, and collection-warning changes.
- Calls OCI Generative AI only on demand, using compact local analysis context.
- Falls back to a deterministic summary when GenAI is unavailable.
- Builds inventory or multi-user comparison reports with per-user evidence tables.
- Exports reports as Markdown, PDF, JSON, CSV, and formatted multi-sheet Excel `.xlsx` workbooks.

## Architecture

```text
OCI Identity read APIs -> normalized JSON snapshot -> deterministic local layers
                                                   |-> policy analysis
                                                   |-> duplicate detection
                                                   |-> relationship explorer
                                                   |-> optional graph JSON / HTML
                                                   |-> JSON / Markdown / PDF / CSV / Excel report
                                                   `-> optional OCI GenAI summary
```

No agent framework is used in the initial implementation. The workflow is linear and deterministic, so a small explicit orchestration layer is easier to audit. The LLM is a narrative aid, never the source of truth.

## Requirements and installation

- Python 3.10 or newer
- OCI CLI-style config at `~/.oci/config`
- A valid OCI SDK profile with `tenancy`, `user`, `fingerprint`, `key_file`, and `region`
- IAM permissions to read the relevant identity metadata

Create an environment and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

The collector defaults to `~/.oci/config` and profile `DEFAULT`. Both values can be changed in the web sidebar or with CLI options. The application does not log config values, tokens, private keys, or SDK signer details.

### Durable Object Storage snapshots

Each successful web collection is saved locally and archived to `bucket_iam_plotter`. Bucket objects are separated as `tenancies/<tenancy-name-and-id>/<collection-date>/snapshot-<hash>.json`. The portal keeps only the newest five working snapshots per tenancy locally, while **Object Storage collections** in the sidebar lists the durable archive and lets an operator activate any selected collection on demand.

Local runs use the OCI user principal from `OCI_CONFIG_FILE` / `OCI_CONFIG_PROFILE`; the OCI Generative AI hosted runtime uses its resource principal (`OCI_IAM_PLOTTER_HOSTED=true`). The caller needs permission to read the bucket and read/write objects. Give the hosted application's resource-principal dynamic group the equivalent Object Storage permissions in the bucket compartment before publishing the hosted artifact. A bucket permission failure never discards a completed local snapshot; it appears in Collection logs as an archive warning.

## Quick start

Start the local web application:

```bash
./start.sh
```

Open `http://127.0.0.1:8501`. Use the compact **Collect** action in the collapsible left sidebar to start a background, read-only collection. Its dialog explains the archive flow and accepts either API-signing authentication (config plus PEM private key) or security-token authentication (config, security token, and its matching signing key). Credential material is written only to owner-only temporary files and is removed as soon as the run finishes. The tenancy selector drives every workspace, uses its latest retained snapshot by default, and keeps the newest five snapshots independently for each tenancy. The overview also highlights the active-user count.

The web UI has no application login in the OCI hosted deployment. Access is intentionally configured with hosted-app inbound authentication set to `NO_AUTH_CONFIG`; deploy it only where that exposure is acceptable. Supplied OCI credentials are used only for the user-started read-only collection and are removed immediately afterward.

The **Access Map** tab avoids a tenancy-wide node map. It unions capped neighborhoods around one or more subjects, starts at one hop, and distinguishes direct/parsed evidence from rule-derived possibilities with solid and dashed lines. Evidence clusters, hierarchy, and an expandable tree are available; click a tree branch to collapse or expand it. The selected subjects are highlighted in the professional themed connection diagram. Choose **Maximize map** to open the map alone in a new tab, with pan, zoom, fit, and export controls. The visible map and connection evidence can be downloaded as PNG, PDF, or JSON. The compact bottom-right **Ask IAM** action opens a multi-turn conversation: it retrieves entities and correlations locally before producing an OCI Generative AI narrative when configured, with a deterministic fallback and visible evidence.

The **Reports** tab accepts zero, one, or multiple users. An empty selection creates an inventory report; selected users produce a comparison table plus per-user group, policy, permission, ambiguity, confidence, and limitation evidence. Markdown and PDF are the primary human-readable downloads. JSON, CSV, and Excel remain available for downstream analysis, including filtered exports. OCI Generative AI summaries are enabled by default for selected users and fall back safely to local deterministic summaries if the service is unavailable.

The **IAM drift** tab compares any two saved collections from the same tenancy without querying OCI again. It uses OCI or normalized record IDs rather than names, presents additions, removals, and changed records separately, and exports the complete evidence as JSON. It is an inventory review aid, not a runtime authorization or risk decision.

Hover over dotted-underlined section titles, metric help icons, and investigation controls for contextual definitions. The sidebar **IAM terminology** glossary explains table and diagram keywords including `Parsed`, `Ambiguous`, `Inferred`, `MEMBER_OF`, `GRANTED_BY_POLICY`, `RULE_REFERENCES`, and `MAY_MATCH_RESOURCE_TYPE`.

## User walkthrough video

A credential-free, caption-led HD product tour explains the complete user journey: secure collection, tenancy and snapshot selection, multi-subject investigation, map layouts and exports, inventory, user and policy analysis, duplicate candidates, drift, reports, collection logs, and Ask IAM.

- [Watch or download the OCI IAM Plotter walkthrough](docs/video/oci-iam-plotter-user-journey.mp4)
- [Read or adapt the walkthrough copy](docs/video/narration.md)
- [Re-render the video](docs/video/README.md)

The video intentionally excludes protected-login content, customer tenant data, and credentials.

The startup script creates or reuses `.venv`, installs dependencies only when `pyproject.toml` changes, disables proxy variables by default, and launches the same FastAPI/React portal used by the hosted deployment. Set `OCI_IAM_PLOTTER_USE_PROXY=1` to preserve proxy variables, `OCI_IAM_PLOTTER_HOST` to change the bind address, or `OCI_IAM_PLOTTER_PORT` to change the port.

## Docker

Build and run the container with Docker Compose:

```bash
docker compose build
docker compose up -d
docker compose logs oci-iam-plotter
```

Open `http://127.0.0.1:8501`. Compose mounts the host's `~/.oci` directory read-only at `/home/plotter/.oci` and stores cached snapshots plus the generated local login password in the `iam-plotter-data` volume. For portable OCI authentication, set `key_file=~/.oci/<private-key-file>` in the selected OCI config profile. The container runs as non-root user `10001`, uses a read-only root filesystem, publishes only to localhost, and clears proxy variables unless `OCI_IAM_PLOTTER_USE_PROXY=1` is exported before startup.

Supply the optional GenAI credential through `OCI_GENAI_API_KEY`; it is passed at runtime and is never included in the image.

## OCI Generative AI hosted deployment

The hosted runtime listens on `PORT` (OCI sets this to `8080`) and uses no ingress authentication. A user still supplies a config together with either an API-signing PEM key or a security token and its matching signing key for read-only IAM collection. The app uses the hosted application's resource principal only for durable Object Storage snapshot archive and retrieval; it creates owner-only temporary credential files for the IAM collector, deletes them in a `finally` block when the collection finishes or fails, and retains only the normalized IAM snapshot.

Deployment configuration is in [deploy/hosted-runtime-config.json](deploy/hosted-runtime-config.json). It injects `OCI_GENAI_API_KEY` from the supplied Vault secret OCID and maps the supplied application-password secret without placing either value in source or an image. The app password is deliberately unused while `APP_AUTH_MODE=no_auth` is selected.

Build, push, and deploy locally (no DevOps pipeline):

```bash
export OCIR_USERNAME='<tenancy-namespace>/<oci-username>'
export OCIR_AUTH_TOKEN='<OCIR auth token>'
./deploy/deploy-hosted-application.sh
```

The script builds a Linux AMD64 image, pushes it to `ord.ocir.io`, creates or updates the hosted application in the supplied Chicago compartment, injects the two Vault references, prunes the oldest inactive artifact only when OCI's 20-artifact limit is reached, and explicitly activates the new artifact. Set `OCIR_REPOSITORY`, `IMAGE_TAG`, `HOSTED_APP_NAME`, or `HOSTED_DEPLOYMENT_NAME` to override defaults. OCI CLI credentials used by the script need permission to manage the hosted application/deployment and push to the chosen OCIR repository.

Run without Compose:

```bash
docker build --tag oci-iam-plotter:local .
docker run --rm --name oci-iam-plotter \
  --publish 127.0.0.1:8501:8501 \
  --volume "$HOME/.oci:/home/plotter/.oci:ro" \
  --volume oci-iam-plotter-data:/app/data \
  oci-iam-plotter:local
```

Stop the Compose deployment with `docker compose down`. Add `--volumes` only when you intentionally want to delete cached snapshots and the generated local password.

## Skills and configuration

[SKILLS.md](SKILLS.md) documents the collector, correlation, investigation, reporting, conversation, storage, and safety capabilities. Copy [.env.example](.env.example) as a reference for supported shell variables. The local launcher does not automatically load `.env`; Docker Compose follows its standard behavior and reads a project `.env` file when present.

| Variable | Default | Purpose |
|---|---|---|
| `OCI_IAM_PLOTTER_CACHE_DIR` | `.iam-plotter-cache` | Local normalized snapshot directory |
| `OCI_IAM_PLOTTER_HOST` | `127.0.0.1` | Web bind address used by `start.sh` |
| `OCI_IAM_PLOTTER_PORT` | `8501` | Web port used by `start.sh` |
| `OCI_IAM_PLOTTER_USE_PROXY` | `0` | Preserve proxy variables only when set to `1` |
| `OCI_CONFIG_FILE` | `~/.oci/config` | Default OCI SDK configuration file shown in the collector UI |
| `OCI_CONFIG_PROFILE` | `DEFAULT` | Default OCI SDK profile shown in the collector UI |
| `OCI_IAM_PLOTTER_OBJECT_STORAGE_BUCKET` | `bucket_iam_plotter` | Durable snapshot archive bucket |
| `OCI_IAM_PLOTTER_OBJECT_STORAGE_NAMESPACE` | auto-detected | Object Storage namespace; set only when namespace discovery is restricted |
| `OCI_IAM_PLOTTER_OBJECT_STORAGE_ENABLED` | `true` | Set to `false` to keep local-only snapshots |
| `OCI_IAM_PLOTTER_HOSTED` | unset | Uses OCI resource principal for Object Storage in hosted runtime |
| `OCI_GENAI_PROJECT_OCID` | configured project OCID | OCI Generative AI project |
| `OCI_GENAI_MODEL_ID` | `xai.grok-4` | OCI-hosted OpenAI or xAI Responses model |
| `OCI_GENAI_BASE_URL` | Chicago OpenAI-compatible endpoint | Responses API endpoint |
| `OCI_GENAI_API_KEY_FILE` | `.oci-genai-api-key` | Permission-restricted API key file |
| `OCI_GENAI_API_KEY` | unset | Preferred in-memory API key |
| `OPENAI_API_KEY` | unset | OpenAI SDK-compatible fallback key variable |

### CLI

Collect once from OCI:

```bash
python -m oci_iam_plotter collect
python -m oci_iam_plotter --oci-config-file ~/.oci/config --oci-profile DEFAULT collect
```

All remaining commands reuse `.iam-plotter-cache/snapshot.json` and do not query OCI Identity:

```bash
python -m oci_iam_plotter build-graph --output artifacts/iam-graph.json
python -m oci_iam_plotter visualize --output artifacts/iam-graph.html
python -m oci_iam_plotter analyze-user --user-id ocid1.user.oc1..example
python -m oci_iam_plotter visualize --focus-user ocid1.user.oc1..example --output artifacts/user.html
python -m oci_iam_plotter find-duplicates
python -m oci_iam_plotter report --focus-user ocid1.user.oc1..example --output artifacts/user-report.md
python -m oci_iam_plotter report --focus-user ocid1.user.oc1..example --output artifacts/user-report.pdf
python -m oci_iam_plotter report --output artifacts/iam-report.csv
python -m oci_iam_plotter report --output artifacts/iam-report.xlsx
```

Generate the user narrative with OCI Generative AI:

```bash
python -m oci_iam_plotter summarize --user-id ocid1.user.oc1..example
python -m oci_iam_plotter report --focus-user ocid1.user.oc1..example --with-summary --output artifacts/user-report.json
```

The configured GenAI project OCID is:

```text
ocid1.generativeaiproject.oc1.us-chicago-1.amaaaaaafigrwqyaszdh7vv7uymklym7vjid2dac4niv6pxokjd54hve4l7a
```

The default model is the OCI-hosted xAI model `xai.grok-4`; it produced complete concise summaries in live verification. Use `--model-id` to select another OCI Responses-compatible OpenAI or xAI model enabled for the project, such as `openai.gpt-oss-120b`. Cohere is not used. Summarization uses the official OpenAI Python SDK, OCI's Chicago OpenAI-compatible endpoint, `client.responses.create(...)`, and the configured project OCID. A failed request returns a structured warning and deterministic summary rather than failing the report.

Provide the OCI Generative AI API-key secret through `OCI_GENAI_API_KEY`, `OPENAI_API_KEY`, or a permission-restricted `.oci-genai-api-key` file. The file is git-ignored. The application never prints the secret or includes it in reports.

Use a different local cache without changing OCI authentication:

```bash
python -m oci_iam_plotter --cache-dir ./private-cache collect
python -m oci_iam_plotter --cache-dir ./private-cache report --output report.md
```

## Output conventions

CLI results are JSON on standard output. Operational errors are JSON on standard error with a non-zero status. Analysis output includes:

- user and group evidence;
- matching policy statement records;
- deduplicated implied-permission descriptions;
- unresolved ambiguous statements;
- an explicit confidence and limitations section.

Relationship JSON records include source, target, kind, evidence type, and safe metadata. Focused-map JSON contains all selected focus IDs, visible nodes, and visible edges; its companion PNG preserves the same filtered diagram. Reports contain snapshot metadata, entity and relationship inventories, zero or more selected-user access analyses, duplicate candidates, optional per-user summaries, confidence, and limitations. Markdown and PDF include a multi-user comparison plus per-user evidence tables. Excel output separates summary, entities, relationships, memberships, policy statements, and selected-user access into filterable worksheets.

To try local analysis without OCI, copy the sample snapshot:

```bash
mkdir -p .iam-plotter-cache
cp examples/sample_snapshot.json .iam-plotter-cache/snapshot.json
python -m oci_iam_plotter analyze-user --user-id user-1
```

## Policy interpretation and limitations

The parser currently recognizes the common form:

```text
Allow group <name> to <verb> <resource-type> in <scope> [where <condition>]
Allow dynamic-group <name> to <verb> <resource-type> in <scope> [where <condition>]
```

Unknown syntax is preserved verbatim and marked `ambiguous`. User analysis matches only explicit cached user-to-group membership to parsed group principals. It does not claim exact effective permissions because authorization can also depend on compartment ancestry, identity-domain behavior, policy conditions, service-specific verb expansion, request attributes, cross-tenancy endorsements/admissions, network sources, resource state, and policies unavailable to the caller.

Dynamic-group matching rules are fetched with read-only detail calls when list responses omit them. The app correlates named OCIDs, referenced resource types, and policies targeting a dynamic group. These are labelled rule references or possible resource types—not proven runtime membership—because actual matching requires service resource inventory and runtime attributes. Identity Domains SCIM collection is best effort per domain; missing endpoint permissions appear as snapshot warnings without failing classic IAM collection.

Duplicate findings are candidates only. OCIDs are authoritative, and the tool never merges or deletes entities.

## Snapshot refresh behavior

`collect` performs one paginated pull for each IAM collection and atomically replaces the latest local snapshot. It also archives each result to `bucket_iam_plotter` under its tenancy name/identity and collection timestamp. The UI selects a tenancy and uses its latest collection by default; storage automatically retains the newest five local working snapshots independently for each tenancy. Older durable bucket collections remain available through the explicit Object Storage collection picker. Every snapshot includes a SHA-256 hash of semantic IAM content, excluding collection time, so unchanged refreshes have the same hash. Plotting, analysis, duplicate detection, summarization context, and reporting use only the selected cached file.

For the most complete inventory, collection should be run by a tenancy administrator or an identity with equivalent read permissions. Lower-privilege profiles remain supported, but inaccessible IAM or Identity Domains data can make correlations incomplete; collection warnings identify optional data that could not be read.

Raw SDK objects are not persisted. This reduces accidental sensitive-data retention, but IAM names, OCIDs, rules, policy text, and relationships can still be sensitive; protect the cache and generated artifacts accordingly.

## Tests

```bash
python -m pytest
```

Tests cover policy parsing, user inference, single- and multi-subject graph construction, duplicate detection, summary input formatting, deterministic fallback wording, stable semantic snapshot hashing, environment settings, multi-user Markdown/PDF output, CSV output, and Excel workbook structure.

## Project layout

```text
oci_iam_plotter/
  analysis.py       policy parser, user analysis, duplicates
  collector.py      read-only OCI SDK collection
  relationships.py derived policy, application, and dynamic-group correlations
  graph.py          NetworkX graph building, multi-focus flow, JSON/HTML export
  jobs.py           background web collection worker
  models.py         normalized serializable dataclasses
  reporting.py      JSON/Markdown/PDF/CSV/Excel report generation
  auth.py           local password gate and secure generated credentials
  query.py          deterministic cached-snapshot conversational retrieval
  settings.py       environment-backed runtime configuration
  store.py          atomic local snapshot storage
  summarizer.py     OCI GenAI and deterministic fallback
  cli.py            command orchestration
  web.py            Streamlit collection and investigation UI
examples/
  sample_snapshot.json
tests/
Dockerfile           non-root application image
compose.yaml         local container runtime with persistent cache
start.sh             local environment bootstrap and web launcher
```

## Extension points

The normalized models and command functions deliberately separate OCI collection from analysis. Natural next steps are a fuller policy grammar, compartment ancestry evaluation, opt-in read-only service resource inventories for stronger dynamic-group matching, and richer historical snapshot comparison. Each should preserve the rule that live OCI calls are read-only and collection is separate from cached analysis.

## Recommended roadmap

The following additions would provide the most user value while preserving the read-only boundary:

1. **Snapshot change analysis** - Compare any two retained collections and show added or removed users, memberships, policies, statements, application grants, dynamic-group rules, and privilege changes. Highlight access gained since the previous collection.
2. **Privilege-risk findings** - Deterministically flag tenancy-wide `manage`, `all-resources`, `any-user`, broad dynamic-group rules, missing conditions, dormant privileged accounts, and administrator-role concentration. Findings should always link back to exact evidence.
3. **Permission and API-operation expansion** - Enrich parsed verb/resource combinations with OCI's documented atomic permissions and required API operations. Keep conditions and compartment scope visible because a permission list alone is not effective authorization.
4. **Observed-use timeline** - Optionally collect OCI Audit and Identity Domains report data to distinguish entitled access from recently exercised access, failed sign-ins, dormant users, and application usage. Store this in a separate time-bounded snapshot with its own collection warnings.
5. **Identity security posture** - Add read-only views for identity-domain administrator roles, MFA enrollment/configuration, sign-on policies, identity providers, password policies, and high-impact application roles.
6. **Stronger dynamic-group correlation** - Optionally use OCI Resource Search across selected regions to enumerate candidate resources and evaluate supported matching-rule attributes. Results must remain labelled as candidates unless all required attributes were collected.
7. **Local access-review workflow** - Let reviewers add local-only owner, disposition, ticket, expiry, and review notes to findings; export a signed evidence manifest without changing OCI.
8. **Saved investigations and report profiles** - Persist selected subjects, filters, report columns, and redaction choices locally so recurring audits are reproducible.

OCI's policy reference explains the relationship among policy verbs, resource types, atomic permissions, and API operations: [Permissions](https://docs.oracle.com/iaas/Content/Identity/policies/permissions.htm). OCI Resource Search can query indexed resources by type, OCID, compartment, tags, and other supported attributes: [Querying Resources](https://docs.oracle.com/en-us/iaas/Content/Search/Tasks/queryingresources.htm). Identity Domains provides administrator roles, sign-on security settings, and operational reports: [Administrator Roles](https://docs.oracle.com/iaas/Content/Identity/roles/understand-administrator-roles.htm), [Sign-On Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/managingsignonpolicies.htm), and [Report Types](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/understand-types-reports.htm). OCI Audit provides longer-lived activity evidence for supported API operations: [Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/home.htm).
