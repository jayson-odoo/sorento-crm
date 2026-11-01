# UAC: retire n8n, reuse its box as the HA standby (N8N-DECOM-HA)

Plan: `PLAN-n8n-decom-ha-01nov.md` (same folder). Each build lane named in the plan copies the
criteria it owns into its own UAC and adds its examples there.

## Chat stays up through the whole retirement

1. At every stage of plan section 4, a customer message sent to the bot gets exactly one reply:
   none lost, none sent twice. Proof per switch: the inbound message count and the bot-turn count
   for the 48 h after the switch match the 48 h before it, minus messages a human took over.
2. Every switch in plan section 4 is undone by one settings change or one workflow re-activation,
   in under a minute, with no deploy and no restart.
3. A message whose respond.io webhook never reached the CRM still gets a reply once the CRM's
   reconcile finds it (PR B), before the n8n failover poller is turned off.
4. When a staff member replies to a customer (in the CRM or in respond.io), the bot stays quiet for
   that contact until the configured pause ends, then answers again; the release happens once.
5. A conversation past its SLA is escalated once per tier by the CRM scheduler, with the same
   assignment and comment n8n made, and never twice while both ran for a minute.
6. Resolving a customer's last open ticket closes the conversation with the same customer-facing
   wording n8n sent.
7. A bot turn that fails sends the customer the failure reply n8n's error workflow sent today.

## n8n is gone

8. With every n8n container stopped for 14 days, nothing in the CRM logs an n8n call, waits on an
   n8n callback, or shows an n8n setting, and the staff AI assistant still reaches the MCP server
   with its own key.
9. The n8n API key is revoked and the CRM box accepts no traffic from the old n8n box outside the
   HA tunnel.

## The freed box is the HA standby

10. Node B runs the same CRM stack as node A and nothing else; it serves no traffic while its
    database is a replica (`GET /api/v1/health/role` answers 503 there).
11. Drills 1-8 and 10 of HA plan v2 section 12 pass with the drill 2 addition: during a node A
    outage the bot answers a test WhatsApp message, sent by the CRM from node B.
12. Point-in-time restore from the WAL archive works to a chosen minute (drill 6) before node B
    joins.
