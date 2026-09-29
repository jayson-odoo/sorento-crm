# UAC: assign a sales agent to a customer (#1170 slice 1)

Plan: `PLAN-customer-sales-agent-assignment-24sep.md`. Small fix track.

- AC-1 On the customer edit page a clearable "Sales agent" `SearchableSelect` lists sales agents as `code - name`, searchable by either, no result cap that hides agents.
- AC-2 Saving persists `customers.sales_agent_id`; clearing persists null. Unknown or out-of-company agent returns 422 with a readable message.
- AC-3 The customer detail page shows "Sales agent: code - name" in the same section and position as the edit field, with an explicit empty state when unset.
- AC-4 The customers list has a "Sales agent" column (explicit size, truncate + title), sortable if the grid sorts other joined columns, hidden or shown per the existing column preferences.
- AC-5 GET customer and the list endpoint return `sales_agent_id`, `sales_agent_code`, `sales_agent_name`; no UUID is rendered anywhere in the UI.
- AC-6 Import and document ingest paths that already set `sales_agent_id` are unchanged and their tests still pass.
- AC-7 pytest and vitest for the cases in the plan; browser evidence at 1280 and 375 via agent-browser through sidebar navigation.
