# OCI IAM Plotter walkthrough narration

## 1. OCI IAM Plotter
Welcome to OCI IAM Plotter. This walkthrough follows a typical security and audit journey: collect a tenancy snapshot, investigate identities and policy relationships, compare change, export evidence, and ask focused questions.

## 2. 1. Start in a protected workspace
After sign in, the workspace opens with a professional Redwood-inspired interface. Choose the tenancy you want to review. Each tenancy keeps its own history, and the newest snapshot is selected by default, keeping separate environments safely isolated.

## 3. 2. Collect a read-only snapshot
Use the compact Collect action when you need current evidence. Paste the OCI config and select API-signing authentication with its private key, or security-token authentication with the token and its matching signing key. Credentials exist only in owner-only temporary files and are deleted when collection ends. Each completed collection is also archived to Object Storage.

## 4. 3. Review collection coverage
The collector gathers classic IAM and Identity Domains data through read-only OCI APIs. It includes compartments and subcompartments, users, groups and memberships, policies and statements, dynamic group rules, domains, applications and grants where access allows. Any inaccessible optional source is shown as a collection warning rather than hidden.

## 5. 4. Access Map with multiple subjects
Open Access Map to select one or more users, groups, policies, domains, or other subjects. Type to search each multi-select list, then choose evidence categories and matching subjects. The default depth is one hop for a fast focused answer, while deeper analysis remains available when needed.

## 6. 5. Read the connection map
The map is built for evidence, not decoration. Solid links show direct or parsed relationships. Dashed links indicate cautious rule-derived possibilities. Switch between clustered, hierarchical, and expandable tree views. Drag the canvas, zoom in or out, fit the view, and click tree branches to collapse or expand connected detail.

## 7. 6. Maximize and export the map
For a larger investigation, choose Maximize map. The new tab contains the map alone rather than the full application, so it works well in a review meeting. Export the current filtered view as an image or PDF for presentation, or JSON for downstream evidence handling.

## 8. 7. Inventory and active users
Use Inventory for a structured view of collected entities. The overview includes an active-user count. Click a count to turn it into a filter, refine it, or remove it when finished. Every applicable inventory and filtered report can be downloaded as a formatted Excel workbook for audit or operational follow-up.

## 9. 8. Analyze users and policies
Select one or multiple users to see their group memberships and the policy statements associated with those groups. OCI IAM Plotter makes the evidence explicit: parsed statements, inferred permissions, ambiguity, confidence, and limitations stay visible. It is an audit aid, not a claim of runtime authorization.

## 10. 9. Detect duplicate candidates
The Duplicates view finds candidates with exact names, normalized policy text, or cautious near-name similarity. The table shows the name and similarity. Select the view icon to inspect OCIDs, policy statements, and the evidence behind the candidate. Findings are never merged or deleted by the application.

## 11. 10. Compare IAM drift
IAM drift compares two saved collections without querying OCI again. Select two snapshots from the same tenancy to identify added, removed, and changed entities, relationships, memberships, and policy statements. Export the full review so change evidence can be shared with control owners.

## 12. 11. Produce audit-ready reports
The Reports workspace accepts no users for an inventory report, or multiple users for an access comparison. Download in Markdown, PDF, JSON, CSV, or formatted multi-sheet Excel. OCI Generative AI summaries are enabled by default for selected users and safely fall back to deterministic local summaries if the model is unavailable.

## 13. 12. Review collection logs
Open Collection logs to review each collection run. Logs provide a transparent record of progress, completed sources, coverage warnings, and failures. This makes it easier to distinguish an incomplete data source from an application issue and to plan a targeted recollection.

## 14. 13. Ask IAM
Ask IAM is the multi-turn chat window in the lower right. Ask focused questions about identities, memberships, policies, relationships, duplicates, or changes. It retrieves relevant cached evidence first, then uses OCI Generative AI for a concise narrative when configured. Each answer keeps its evidence available for verification.

## 15. A complete, evidence-first IAM journey
That is the OCI IAM Plotter journey. Use read-only collection for trustworthy snapshots, follow relationships in focused maps, review change and duplicate candidates, export the exact filtered evidence you need, and use Ask IAM to accelerate informed conversations.
