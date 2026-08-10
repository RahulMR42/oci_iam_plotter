# OCI IAM Plotter report

- Tenancy: `ocid1.tenancy.oc1..sample`
- Collected: 2026-08-04T00:00:00+00:00

## Entity inventory

- group: 1
- policy: 1
- tenancy: 1
- user: 1

## User access analysis

User: **alice**

Groups: Auditors

Implied permissions:
- read all-resources (tenancy)

### Confidence and limitations

- This is a policy-text inference, not OCI's final authorization decision.
- Dynamic groups do not contain users and are not treated as user access.
- Conditions, service-specific permissions, policy inheritance, and runtime context can change effective access.

## Duplicate / overlap candidates

- Exact entity-name candidates: 0
- Exact policy-statement candidates: 0
- Near-name candidates: 0

## Next checks

- Validate candidate access with OCI policy evaluation and service-specific controls.
- Review conditional statements and policies outside the collected scope if needed.
