# UAC: retire n8n, reuse its box as the HA standby (N8N-DECOM-HA)

Plan: `PLAN-n8n-decom-ha-01nov.md` (same folder), owner rulings 1 Nov in its section 6. Each build
lane named in the plan copies the criteria it owns into its own UAC and adds its examples there.

## Chat stays up through the whole retirement

1. At every stage of plan section 4, a customer message sent to the bot gets exactly one reply:
   none lost, none sent twice. Proof per switch: within each 48 h window (before and after the
   switch), inbound customer messages, bot turns and replies sent match one to one, apart from
   messages a human took over; the after window has no more gaps than the before window.
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
8. Every attachment type the n8n upload workflow extracts today is extracted by the CRM, with the
   same fields filled, before n8n is stopped (Q5 b).

## n8n is gone

9. With every n8n container stopped (stage 6), nothing in the CRM logs an n8n call or waits on an
   n8n callback (the liveness ping task is off), and the staff AI assistant still reaches the MCP
   server with its own key. After PR G (stage 7), no screen shows an n8n setting.
10. The n8n API key is revoked and the CRM box accepts no traffic from the old n8n box outside the
    HA tunnel.

## HA, phase A: node A and the witness (before node B)

11. A point-in-time restore from the WAL archive to a chosen minute finishes on a throwaway
    container and its row counts match (v2 drill 6), before node B joins.
12. With node A's etcd or the witness stopped, node A stays primary and keeps taking writes
    (rehearsed in H4a, then checked once on prod in a quiet window).
13. Adopting prod Postgres into Patroni takes one window of at most 2 minutes of downtime, and the
    database afterwards is the same database (row counts and the alembic head match before/after).

13b. (H4b) The first release after H4 deploys cleanly on the Patroni node: the HA compose file is loaded, the
    pre-migrate snapshot and alembic preflight work, workers start on the released image, and the
    role watcher never fights the deploy. A deploy on a box whose HA setup is half-configured stops at
    the preflight with a message naming what is missing, before it changes anything.

## HA, phase B: the freed box is the standby

14. Node B runs the same CRM stack as node A and nothing else; it serves no traffic while its
    database is a replica (`GET /api/v1/health/role` answers 503 there).
15. Routing follows the primary with no preferred node (Q4): after a failover, Cloudflare sends
    traffic to the new primary within about 30 s and never moves it back on its own; at no moment do
    two nodes accept writes (drills 1, 2 and 4).
16. Drills 1-7, 9 (witness) and 10 of HA plan v2 section 12 pass with the drill 2 addition: during a
    node A outage the bot answers a test WhatsApp message, sent by the CRM from node B.
