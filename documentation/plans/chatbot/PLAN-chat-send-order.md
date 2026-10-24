# PLAN: answer an earlier-sent photo before a later text that reached the CRM first

Status: in progress (Plan). Track: small fix (backend only, no migration, no auth / RBAC change, no new ingest surface).
UAC: `chat-send-order-acceptance-criteria.md`.
Source: prod case 24 Oct ~08:15 MYT (image card SRTWC2350-P-RL, then "Pls check stock" seconds later; the text's turn
ran first and answered the product held from earlier). Owner ruling 24 Oct (option c): keep the 26 Sep rule "no timer,
no waiting window"; every message stays its own turn with its own reply. Fix ONLY the order.

Design: to follow in this file once the code is read.
