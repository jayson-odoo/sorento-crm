# PLAN: WA-MSG-TRIM - fewer outgoing WhatsApp messages

Status: in progress (small fix track: data migration only, no auth/RBAC, no new ingest surface)

## Why

Since 1 Oct 2026 Meta charges every outgoing WhatsApp message, service replies inside the 24h
window included (about US$0.014 each in Malaysia, passed through by Respond.io). The dev
snapshot (to 18 Sep) shows about 9,459 outgoing messages per 30 days. Owner (3 Oct 2026) wants
fewer of them. All three changes below are owner decisions; no behaviour card is needed.

## Changes

1. Compact stock view for every contact.
   - Global default stock visibility mode: detailed -> compact (code floor + seeded row).
   - Contact policy rows with mode=detailed -> compact. mode=availability rows untouched.
   - Additive, idempotent alembic data migration with a working downgrade.
2. n8n `sub-sendmsg` chunk limit 1800 -> 3900 chars (text), buttons body 1000 -> 1024
   (WhatsApp interactive body text limit). Split at line/paragraph boundaries only, as today.
   Lives in the separate `sorento-crm-n8n` repo; prod n8n is not deployed by this lane.
3. Out-of-scope escalation sends ONE message instead of two ("please wait" + "routed to PIC"):
   "Routed to your PIC, they will reply shortly."

Rejected by the owner (not in scope): debouncing / merging inbound messages, moving
complaint/SLA notices off WhatsApp, removing Respond.io auto messages.

## Tests

Red-first: a pytest commit that fails on main, then the fix.
