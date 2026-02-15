# Regression Tests for Product Standards

Per [ADR-PRODUCT-STANDARDS.md](./ADR-PRODUCT-STANDARDS.md), these flows should be covered by regression tests when a test framework is in place.

## Standardized flows

1. **Create (modal)**  
   - Open create modal from list → submit valid form → list refreshes, modal closes.

2. **Edit (modal)**  
   - Open edit modal from list or detail → submit changes → data refreshes, modal closes.

3. **Delete (confirmation)**  
   - Click delete → confirmation dialog appears → confirm → entity removed, list/detail updates.

4. **Detail empty states**  
   - Navigate to detail with no related data (e.g. access agent with no team assignments) → all sections visible with explicit empty states.

## Manual verification

Until automated tests exist, use the PR checklist and manual verification:

- Access Agents: list → create modal → detail → edit modal → delete confirmation.
- Teams: list → create modal → detail (members) → edit modal → delete confirmation.
- Attachments: archive (move to trash) vs permanent delete from trash.
