# UAC: AI tools standard

Plan: `PLAN-ai-tools-standard-5nov.md`. Each line is checked by a test or a hand step named in the lane.

- AC-1 A staff user on the agent path (panel, or WhatsApp with `chatbot_agent_enabled` and a linked active user) can
  ask for rows, filters, totals and group-by over any registered entity and gets figures equal to the screen's.
- AC-2 A user never sees a row, field or entity their screen would not show them: company, own-row, field slug,
  module enablement.
- AC-3 A contact with no linked user is never offered `crm_query`, `crm_describe`, `crm_act` or `tools_search`.
- AC-4 Every change made through `crm_act` waits for the user's Confirm (button on panel, typed yes on WhatsApp), runs
  the screen's own route function as that user, and writes an audit row naming that user and the action.
- AC-5 Cancel, or anything that is not a yes, changes nothing.
- AC-6 Input tokens per model call for a full-permission user are no higher than before phase 1, measured on the same
  eval set.
- AC-7 A PR that adds a paged list route with neither a registration nor the opt-out comment fails the PR gate.
- AC-8 A failed ask the agent flags as `no_tool` shows on the Wishlist screen within the same day.
- AC-9 Contacts' `chatbot_agent_enabled` stays false unless someone switches it on; nothing in this plan changes it.
