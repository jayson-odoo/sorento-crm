# PLAN: Agent bulk actions from a pasted table (AGENT-BULK-ACTIONS)

Status: Plan (lane opened 7 Nov 2026; behaviour card pending owner answers). Track: full (L, writes + permissions).

Goal (phase 1): the owner pastes a table of contacts (phone, name, access type, customer(s), company) into the
assistant side panel and says "grant access to these people"; the agent previews every row and applies the whole
batch on one Confirm, through the same service functions the UI uses, with per-row results and audit as the real user.

Details follow in the behaviour card and the sections below once the code read is done.
