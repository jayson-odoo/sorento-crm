# PLAN: retire n8n, reuse its box as the HA standby (N8N-DECOM-HA)

Status: plan filed for owner review (lane N8N-DECOM-HA, 1 Nov 2026). Plan only: nothing in
production changes from this lane. Track: L (cross-repo, prod infra), LEAD pattern; each build step
in section 4 and section 5 is its own lane with its own track.

Owner, 1 Nov 2026: retire n8n now and make the n8n box serve as the HA standby.

Builds on HA plan v2, `documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md` (PR #1915), which
kept n8n on node B "unchanged, for Tier 1" (its section 6, lines 393-440). This plan replaces that
section and lists every other v2 line that changes (section 5). It also supersedes the 25 Oct owner
ruling Q1 (a) "replies keep going out through the thin n8n `chatbot-sender`"
(`documentation/plans/chatbot/PLAN-chat-inbox-queue.md:11`): replies move into the CRM.

Rules: no addresses, hostnames, keys or staff names here; prod details live outside the repo.
UNVERIFIED marks every fact this lane could not check from the repo. The live n8n state comes from
read-only owner checks (screenshots); until they arrive, section 1 rests on local exports.

---

## 0. Summary

- n8n still does real work: every customer-facing bot reply is sent by n8n, and n8n alone runs the
  missed-message poller, the bot-pause release timer, the conversation-SLA escalation schedule, the
  conversation-SLA tracker writes for human chats, attachment AI extraction and a few webhooks.
  The CRM already owns ingress (respond.io webhook, inbox queue, turn engine).
- Seven CRM PRs move the rest (section 4). Each lands behind a switch that is read per turn or per
  tick, so cutover and rollback are a settings flip, not a deploy. n8n stays running, warm, until
  every switch has soaked; then it is stopped (not deleted) for 14 days, then removed.
- HA: with n8n gone node B becomes a plain CRM node, a mirror of node A. HAProxy, the n8n
  container firewall, the n8n private path and drill 9 drop out of plan v2; the bot path becomes
  highly available too (v2 listed n8n as the bot's single point of failure, v2 line 760). Steps that
  touch only node A and the witness can start now (section 5).

## 1. Inventory: n8n workflows

Source: local exports only. Crew has no n8n API access (crew config points every n8n URL at
`.invalid`). Newest export of any workflow is 3 Oct 2026; the export repo's HEAD is 2 Sep with a
large uncommitted tree; the producers are newest in a drafts branch of 8 Sep. So about 4 weeks of
live edits are not captured. Live list, active state and 14-day run counts: owner read-only check
filed 1 Nov (results go to the private crew folder, not here).

49 exported workflow ids, all exported `active: true`; about 20 are test clones, forks or
harnesses, so roughly 16 are reachable from live traffic (the private-path runbook counted "about
29 live", `documentation/runbooks/n8n-private-path.md:15`). By job:

| # | Group | Workflows (export names) | Trigger | CRM-native today? |
|---|---|---|---|---|
| W1 | Producer / dispatcher / spine | `sorento-main`, `sorento-main-INJECT`, `sorento-dispatcher` (1 s tick, Redis fan-out), spines incl. the S7 thin spine (`POST /api/v1/external/chat/turn`, then executes the returned actions) | respond.io trigger, 1 s schedule | YES: respond.io webhook to the CRM (`sorento_crm_backend/app/api/v1/public/respond_webhook.py:335`), CRM inbox queue (`app/services/chatbot/inbox_queue.py`), switch `chatbot_direct_ingress_mode` (`app/models/user.py:781-783`, default `off`). Which spine is live: UNVERIFIED |
| W2 | Pre-S7 chatbot brain | 13 `sub-*` lane workflows (parser, answer, get-results, get-rag on the CRM DB credential, media intake, ...) | sub-workflow | YES: the CRM turn engine replaced them (`app/services/chatbot/engine.py`); `sub-media-intake` still called by the S7 spine (UNVERIFIED live) |
| W3 | Customer sender | `sorento-sub-respond-sendmsg-respond` (text, chunking, quick replies), `sub-send-attachments`, `respond-send-user` | sub-workflow, respond.io trigger | NO (section 2, J1) |
| W4 | Error reply | `sub-error-logger` (composes the customer error text, sends via the sender) | sub-workflow | NO (J1) |
| W5 | Missed-message failover | `failover-poller-LIVE` (every 5 s, reads respond.io message list, re-injects misses) | schedule | PARTLY: `chat_history_reconcile` stores missed rows but starts no turn (J3) |
| W6 | Bot-pause timer | `ht-sweeper` (every 30 s, releases the bot-pause flag, sends a message, clears a contact field), `ht-config-form` (timeout in n8n's Redis) | schedule, n8n form | NO: the CRM only reads the flag (`app/services/chatbot/direct_ingress.py:113`, `inbox_queue.py:849`) (J5) |
| W7 | SLA and hand-off | `sub-human-intervention` (assign + comment), `respond-close-convo`, SLA escalation (1-minute schedule, `documentation/n8n/sla-scheduled-escalation.workflow.json:6-19`) | sub-workflow, CRM webhook, schedule | PARTLY: logic in `app/services/sla_service.py:2694` and `:3349`, no scheduler job (J6, J7) |
| W8 | Attachment extraction | `system-upload-attachments` (Gemini / PDF extraction, posts results to `/api/v1/external/*`) | CRM webhook | PARTLY: CRM RQ queues `flyer_read` / `knowledge` / `media` cover some types (J9) |
| W9 | Liveness | `system-healthcheck-ping` (no export), heartbeat template (`documentation/runbooks/n8n-heartbeat-workflow.json`, exported inactive) | CRM ping, schedule | n/a: deleted, monitoring moves to the CRM (J11, J13) |
| W10 | Unknown | one id with no export; a stock-inquiry-revise handler may not exist | ? | owner check decides (J8) |

Four workflows use a direct CRM database credential (`documentation/runbooks/n8n-private-path.md:209`):
the sender, `respond-send-user`, `respond-close-convo`, `sub-get-rag`. All four retire with their jobs.

## 2. Inventory: CRM and MCP paths that touch n8n

Paths under `sorento_crm_backend/` unless marked. Size: S under 300 changed lines, M 300-1500, L more.

| Job | n8n today | CRM path (file:line) | Native already | Missing | Size | PR |
|---|---|---|---|---|---|---|
| J1 Bot replies | sender sends the turn's actions to respond.io | `app/services/chatbot/direct_ingress.py:355-446` POSTs actions to the workspace's `chatbot_sender_url` (`:225`, `:373`, `:410`); "the CRM never sends on the turn path" (`app/services/chatbot/engine.py:9292`, `:12359`; `contracts.py:429`) | client calls exist: `app/services/integration_service.py:443` send_message, `:448` attachment, `:506` comment, `:617` assignee, `:772` contact; all staff/system sends already native (`app/tasks/respond_io_tasks.py:446`, `:482`, `:554`, ...) | an executor for the five action kinds (message + quick replies with chunking, attachments, assign, comment, contact fields), 24 h window template fallback, the failure reply (W4), Retry into the inbox queue instead of n8n (`app/services/chatbot/dispatch.py:456`); `sender_configured` (`direct_ingress.py:215`) must count the native sender as configured | L | A |
| J2 Ingress | producer / dispatcher / spine | `app/api/v1/public/respond_webhook.py:335`, `inbox_queue.py`, `direct_ingress.py:133` | YES (#1848) | owner flip `chatbot_direct_ingress_mode` to `all` (prod value UNVERIFIED) | 0 | - |
| J3 Missed messages | failover poller | reconcile `app/scheduler/task_scheduler.py:347` stores rows only | rows yes, turns no | start a turn for a reconciled inbound with no turn (gap plan slice 4, `documentation/plans/chatbot/PLAN-n8n-to-direct-ingress-gap.md`) | M | B |
| J4 Comments mirror | forwards `comment.created` to `POST /external/chat-history/comments` (`app/api/v1/external/chat_history.py:199`) | webhook maps message events only (`respond_webhook.py:61`, `:297`) | no | handle comment events in the webhook (subscription UNVERIFIED) | S | C |
| J5 Bot pause | `respond-send-user` / `sub-human-intervention` set it, `ht-sweeper` releases it | CRM POSTs every CRM-side staff send to n8n (`app/services/crm_chat_outbound_webhook.py:241`, callers `app/tasks/respond_io_tasks.py:125`, `app/services/sla_service.py:6176`, `:6737`, `:7085`, `app/services/price_tag_notify.py:190`) | reads only | set the pause on a human send (CRM-side sends and `message.sent` webhook events from respond.io), release on timeout from a scheduler tick, timeout as one system setting | M | C |
| J6 Conversation SLA | 1-minute escalation schedule; tracker create / agent-replied on respond.io events | `app/api/v1/sla/sla_tracking.py:983` due-escalations, `:1018` escalate, `:1574` / `:1926` tracker writes; `app/api/v1/external/conversation_sla_tracking.py:103` agent-replied | logic yes (`app/services/sla_service.py:3349`, `:2694`, `:4008`); form SLA has a job (`task_scheduler.py:417-420`), conversation SLA none | scheduler handler (rollback = `scheduled_tasks.enabled`, `app/models/scheduled_task.py:18`); tracker writes from the webhook; escalate must stay single-fire while both run for one minute (UNVERIFIED, test it) | M | D |
| J7 Close conversation | `respond-close-convo` | `app/services/crm_close_convo_webhook.py:150` | RQ tasks `app/tasks/respond_io_tasks.py:745` close, `:554` resolved message | call the tasks instead of the webhook; keep n8n's wording (UNVERIFIED) | S | D |
| J8 Portal revise | unknown workflow (no export) | `app/services/procurement_service.py:6563`, `:8090`; empty URL = hard error (`:6574`) | WhatsApp sends exist (`app/tasks/respond_io_tasks.py:367`) | depends on the owner check: if the URL is unset, only the error path changes | S-M | E |
| J9 Attachment extraction | `system-upload-attachments` | `app/services/attachment_webhook_helper.py:40`; per-type switch `attachment_types.triggers_n8n_webhook` (`app/models/resources.py:68`); results land on `/api/v1/external/promotions`, `product_attachments`, `forms`, ... | some types (`app/tasks/media_tasks.py:81`, flyer / knowledge queues) | per-type audit, then a native RQ task per type still used | L | F |
| J10 Inbound business writes | flows call `/api/v1/external/*` (stock inquiries, purchase requests, contacts, ...) | mounted `app/api/v1/__init__.py:256` | chatbot lanes call services in-process | nothing to build; routes with no caller left are deleted in G. Keep the 5 the MCP server uses (`sorento_crm_mcp/sorento_crm_mcp/catalog.py:883`, `:902`, `:1253`, `:1384`, `:1801`) and the AutoCount ingest | S | G |
| J11 Liveness + n8n timeouts | ping workflow | `app/services/n8n_liveness_service.py:36`, job `task_scheduler.py:823`; delegated sweep `:684`; callback timeout `app/services/integration_service.py:1202` | n/a | delete | S | G |
| J12 Settings | - | 4 n8n URLs on Settings > Integrations (`app/models/user.py:541-545`, `sorento_crm_frontend/app/(protected)/user-management/settings/integrations/page.tsx`); workspace sender / retry URLs (`app/models/respond_workspace.py:66-72`) | n/a | drop after soak (migration) | S | G |
| J13 Monitoring | heartbeat through n8n + MCP; uptime check on n8n's health URL | `documentation/runbooks/monitoring.md` | scheduler heartbeat exists (`task_scheduler.py:753`, `:972`) | a bot-path check that does not need n8n | S | G |
| J14 Shared API key | n8n and the MCP server send the same legacy key, seeded as the "n8n" integration (`app/services/integration_seed.py:54`) | `app/services/integration_auth.py` | per-integration keys exist | give the MCP server its own key FIRST, then revoke the n8n one | S | G |

MCP: the server stays (the staff AI assistant reaches it, `app/config.py:361`); only n8n's MCP
client nodes go. No n8n service exists in the repo's compose or deploy script.

## 3. Inventory: what else runs on the n8n box

Nothing in the repo or crew notes measures it; the owner check (filed 1 Nov) returns containers,
memory, disk, volumes, ports, cron and timers. What the runbooks describe (applied state
UNVERIFIED): the n8n compose project (main container, possibly workers), n8n's own Postgres or
sqlite (`documentation/runbooks/backups.md:327-343`), a separate Redis holding n8n's chat queue,
locks and the bot-pause timers, a reverse proxy with TLS for the editor and webhooks, Tailscale for
the private path to the CRM (`documentation/runbooks/n8n-private-path.md`), a nightly n8n DB dump to
Drive at 03:20 with Healthchecks (`backups.md:349-355`), uptime checks (`monitoring.md:112-115`).
Box size per plan v2: 8 vCPU / 32 GB / 400 GB (v2 lines 180-184, not measured).

What node B needs as a CRM node (v2 lines 186-198): about 9 GB steady, plus 5.4 GB during a
blue/green deploy, plus about 0.3 GB of workers after promotion: about 15 GB of 32 GB. Disk: about
30 GB plus the database size. Everything n8n uses today is freed.

## 4. Decommission order (zero chat downtime, rollback per step)

Principle: the CRM path is switched on BESIDE n8n, never instead of it. Every switch is read per
turn or per tick (no deploy, no restart). The n8n counterpart is deactivated by the owner only after
48 h clean on the CRM path, and n8n stays installed until the end. Two paths never send the same
message: the n8n spine's copy of a message already started by the CRM is dropped as a duplicate
(D15, `app/models/user.py:777-780`); for timers and schedules the owner deactivates the n8n
workflow and turns the CRM job on in the same minute.

| Stage | What | Who | Needs | Rollback |
|---|---|---|---|---|
| 0 | Read-only checks + full export archived privately; deactivate test clones the 14-day counts show unused | owner | - | reactivate |
| 1 | `chatbot_direct_ingress_mode` to `all` (if not already): the CRM starts every turn, n8n only sends | owner, Settings | respond.io webhook to the CRM live (`RESPOND_WEBHOOK_SECRET` set) AND the n8n `chatbot-sender` live with its URL + key on the workspace: without them a covered contact silently keeps the n8n path (`sender_configured`, `app/services/chatbot/direct_ingress.py:215-227`). The exports hold the sender only as an inactive template (UNVERIFIED live). If it is not live, skip stage 1: stage 2 turns on both switches together | set `off` |
| 2 | PR A ships; switch "CRM sends replies" on (and direct ingress `all`, if stage 1 was skipped) after a test on the owner's own number | lane A, owner | stage 1, or PR A alone | switch off: back to the n8n path |
| 3 | PRs B, C, D, E ship in parallel lanes; each switched on with its n8n twin off (poller, ht-sweeper + forms, SLA schedule + hand-off + close, revise) | lanes B-E, owner | stage 2 for B and C | per PR: CRM switch off, n8n workflow back on |
| 4 | PR F ships per attachment type (`triggers_n8n_webhook` off per type as each native task lands) | lane F | audit | per type: flag back on |
| 5 | Deactivate producer, dispatcher, spine (gap slice 6); remove n8n's respond.io webhook / trigger subscription | owner | stages 2-3 soaked 48 h | reactivate |
| 6 | Stop the n8n containers (do not delete) for 14 days; then final export + n8n DB dump to the private backup; MCP server on its own key | owner | stage 5 | start the containers |
| 7 | PR G cleanup (dead code, settings columns, routes, runbooks); revoke n8n's key; close the n8n private path and its firewall openings into the CRM box | lane G, owner | stage 6 ended | revert PR (columns dropped last) |
| 8 | Node B rebuilt as a CRM node, joins HA (section 5) | crew + owner | stage 6 ended | n/a |

Order of CRM PRs: A first (largest, gates stage 5); B and C next (both need A's sender for the
messages they send); D, E, F independent of A and can run in parallel; G last. Estimated
lane-days: A 2.5-3, B 1, C 1, D 1.5, E 0.5-1, F 2-4 (depends on the audit), G 1; about 10-13 in
all, 3 lanes at a time, so about 2-3 weeks to stage 5, plus the 14-day stop.

## 5. HA Tier 1 on the freed box: changes to plan v2

What changes in plan v2 (line numbers in `PLAN-ha-tier1-n8n-box-27oct.md`):

| v2 part | Change |
|---|---|
| Diagram and node B (83-91), "Where each client connects" (163-171) | Node B runs exactly node A's stack. The n8n bullet, the HAProxy, the one-time `CRM_PRIVATE_IP` move and node B's special nginx bind all go |
| Resources (186-200), disk (462-475) | n8n rows removed; node B about 15 GB of 32 GB peak (section 3) |
| Network (203-226) | container firewall only on the witness (shared-service apps), not on node B; no n8n openings into node A |
| Section 6 (393-440) | replaced by this plan |
| Failback O3 (247-259, 603-605) | its reason ("CRM and n8n on separate boxes again") is gone: owner question Q4 |
| Effort (702-707) | minus "HAProxy for n8n"; plus "rebuild node B" if Q3 (a) |
| Risks (760-761) | "n8n is a single point of failure for bot sends" removed: after stage 5 the bot path fails over with the CRM, since respond.io posts to the CRM's public host behind the LB |
| Drills (765-778) | drill 9 runs on the witness only; drill 2 adds "the CRM sends the reply from node B" |
| Templates | delete `infra/templates/haproxy/`; trim the n8n parts of `infra/templates/host/docker-user.nft`, `infra/templates/patroni/patroni.yml` (lines 14, 96, 106), `infra/templates/wireguard/wg0.conf.template`, `infra/README.md`, `infra/scripts/switchback.sh` comment; retire `documentation/runbooks/n8n-private-path.md` and the n8n parts of `backups.md`, `monitoring.md`, `prod-edge-lockdown.md` |

Unchanged: active-passive (D1), all in Malaysia for now (D2), no webhook buffer (D3), Cloudflare LB
+ R2 (D4), automatic promotion with a witness on the shared-service box (D5, O1), 15 s checks (O2).

PR-sized steps:

| # | Step | Who | Can start | Size |
|---|---|---|---|---|
| H1 | Amend plan v2 + trim the templates and runbooks above | lane | after this plan is approved | S |
| H2 | Private infra repo with prod compose, nginx, `.deploy.env` shape captured (v2 step 9.1) | crew + owner | now | 0.5 d |
| H3 | Witness etcd + WireGuard between node A and the witness; R2 bucket + scoped token | crew | now | 1 d |
| H4 | Adopt prod Postgres into Patroni on node A as a one-member cluster, WAL-G archiving on (one 1-2 minute window, v2 step 6). Gives point-in-time restore (RPO 24 h to about 60 s) before node B exists | crew with owner at the box | after H2-H3 (Q2) | 1.5-2 d |
| H5 | Release deploys both nodes, migrations only on the leader (v2 step 7) | lane | now (code) | 1-1.5 d |
| H6 | Node B: fresh OS (Q3), edge rules, WireGuard, etcd member, CRM compose with `SKIP_MIGRATIONS=1`, role watcher; Patroni seeds the replica | crew + owner | after stage 6 ends, H5 merged | 1 d |
| H7 | Allowlists for node B's egress address (OpenAI and any other provider with one; v2 step 8) | owner | with H6 | - |
| H8 | Cloudflare LB + monitor on `/api/v1/health/role` (v2 section 5) | owner + crew | after H6 | 0.5 d |
| H9 | Drills 1-8 and 10 (v2 section 12) | owner + crew | after H8 | 1 d |

## 6. Owner questions

Q1 Pace. (a) Staged: each CRM PR switched on alone, 48 h watch, n8n warm until stage 6, about 2-3
weeks to stage 5 (recommended: zero chat downtime and a one-flip rollback at every step). (b) Build
all, switch everything in one quiet night, about 2 weeks; one bad switch means hunting across six.

Q2 HA start. (a) Start H2-H5 now (node A + witness, with point-in-time restore from H4); node B
joins after n8n is stopped (recommended: PITR is the biggest risk cut and needs no node B). (b) All
HA work after n8n is gone. (c) Node B joins now beside n8n with v2's HAProxy, removed later
(throwaway work).

Q3 Node B. (a) Rebuild from a fresh OS after the 14-day stop and the final n8n dump (recommended:
no n8n leftovers such as Tailscale entries, host mappings, cron, firewall rules; and it proves the
infra repo can build a node, which the disaster restore needs anyway). (b) Remove n8n in place.

Q4 Primary placement (revisits O3, whose reason was keeping the CRM and n8n on separate boxes).
(a) No preferred node: the primary stays where a failover leaves it; `switchback.sh` and drill 8 are
dropped (recommended: both boxes carry today's load, and every switchback is a 5-15 s write pause
for no gain). (b) Keep O3: back to node A at 04:00 after 24 h healthy. (c) Make node B, the larger
box, the preferred primary and switch back to it instead.

Q5 Attachment extraction. (a) Port only the attachment types the CRM's own integration log shows
in use in the last 60 days; other types lose automatic extraction (recommended: smallest PR F, and
the audit is a read on the CRM's own data). (b) Port every type the n8n workflow handles.

## 7. Risks

- Live n8n edits after 3 Oct are not in any export; the owner's export closes that before PR A's
  contract is fixed.
- The bot-pause timeout value lives in n8n's Redis (W6, UNVERIFIED); PR C reads it from the owner
  check or asks.
- Running the CRM and n8n twins side by side for a minute (SLA escalation, bot-pause release) can
  double-fire; each such PR carries a test that a second run is a no-op.
- The respond.io webhook to the CRM may not be subscribed to comment or contact events (J4);
  owner checks in respond.io.
- Stopping n8n removes the failover poller; PR B must be on first or missed messages get no
  answer during a respond.io webhook outage.
