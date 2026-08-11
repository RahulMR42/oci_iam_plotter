# Reports & Risks design

## Purpose and boundaries

Reports & Risks turns a selected, read-only IAM snapshot into reviewable user-access and tenancy-risk evidence. It is a prioritization tool: OCI remains the authority for effective authorization because policy conditions, service permissions, inheritance, and runtime context can alter access.

## Per-user reports

The user picker accepts one or more classic IAM or Identity Domains users. For each selected user, the service traces direct group membership, policy statements that name those groups, implied permissions, unresolved policy matches, and risk evidence. The report combines those results into a comparable view rather than evaluating users in isolation.

The console renders the generated HTML report in place. The same evidence can be downloaded as HTML, Markdown, or PDF. Markdown is retained as a portable audit format; HTML is the readable console and browser format.

## Risk posture

Risk posture evaluates all collected users, groups their results by severity, and presents the most important individual policy signals. Counts are interactive filters: selecting a severity narrows the evidence table. Operators can also filter by minimum score or search user, permission, policy text, or reason.

Each successful collection creates a tenancy-level posture report. When Object Storage archiving is enabled, it is stored with the collection so historical posture is durable. The console shows the latest three reports by default and can browse other archived reports. Archived reports can be downloaded as Markdown or PDF.

## Score calculation

Every applicable parsed policy statement starts at zero. Points are added for the policy verb, resource breadth/sensitivity, and scope; a policy condition reduces the score by 10, but does not eliminate the signal.

| Evidence | Points |
|---|---:|
| `manage` / `use` / `read` / `inspect` | 55 / 25 / 8 / 0 |
| `all-resources` | 45 |
| Sensitive resource | 30 |
| Tenancy / compartment scope | 25 / 8 |
| Condition present | -10 |

Sensitive resources are Identity, users, groups, policies, compartments, tag namespaces, Vaults, keys, secret families, and database families. Only statements scoring 25 or more become displayed signals. A user’s risk score is the highest score among that user’s applicable statements, not the sum of all statements.

| Score | Level |
|---|---|
| 85+ | Critical |
| 55–84 | High |
| 25–54 | Medium |
| Under 25 | Low |

For example, `manage all-resources in tenancy` scores 125 (55 + 45 + 25). `use vaults in a compartment` scores 63 (25 + 30 + 8).

## Administrator handling

Membership is matched only to the exact standard OCI group names. A member of `Administrators` receives the **Administrator** badge; a member of `Domain Administrators` receives the **Domain administrator** badge. The badge is evidence, not a blanket risk exemption.

For a standard tenancy administrator, only the expected `manage all-resources in tenancy` statement is excluded and recorded as an expected grant. Any other powerful statement remains scored. Domain administrators are labeled but their policy statements are not automatically excluded.

## Generative AI summary

After collection, medium-, high-, and critical-risk users can receive a concise OCI Generative AI summary grounded in the matching policy evidence. If the model is unavailable, the application uses a deterministic summary from the same evidence. The model does not change scoring, policy matches, or stored IAM data.

## Auditability

Each displayed signal includes its parsed permission, score, reasons, statement identifier, and original policy text when available. Report outputs retain the snapshot context and evidence so reviewers can reproduce the conclusion from the selected collection.
