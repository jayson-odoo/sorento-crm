# PLAN: agent bulk wave 4, edit contacts from a pasted table keyed by phone (AGENT-BULK-W4-CONTACTS)

Status: Plan (behaviour card first; no code until the owner answers the crew-ask). Track: full (agent write path to contacts).

Wave 4 after AGENT-BULK-W3-AGENTS (#2253). Pattern: `crm_customer_agent` (`app/services/chatbot/agent/customer_agent.py`)
through `crm_batch_propose` (`batch.py`) and one confirm card.

Also in this lane: a not-changed row re-sent with fewer cells on a follow-up keeps its earlier reason (crew W3 live check).

Sections to follow: Step 1 (the contact edit path today, file:line), behaviour card, decisions, tests, slices.
