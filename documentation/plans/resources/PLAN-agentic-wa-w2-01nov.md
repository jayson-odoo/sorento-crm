# PLAN: AGENTIC-WA-W2 - safe dealer writes on WhatsApp, each with a confirm

Status: CARD v1 posted as crew-ask on #2072 (1 Nov), waiting on owner. No code before the answer. Track: L.
UAC: `agentic-wa-w2-acceptance-criteria.md` (written after the owner answers the card).

Parent: `PLAN-agentic-knowledge-p2-31oct.md` section "W2 - writes on WhatsApp". W1 merged in #2053
(`_archive/resources/PLAN-agentic-knowledge-w1-01nov.md`).

Owner rulings in force: W-Q1 (a) linked staff runs as its CRM user; W-Q2 (a) a miss follows the escalation
switch; W-Q3 (a) bot read tools + knowledge under the bot's reveal keys; W-Q4 = all safe dealer writes, each
with a confirm, least risk first; W-Q5 (a); router cut-off 0.70; customers never see "agent mode". Earlier
agent rulings: writes check permissions through P1 `tools.py`, confirm before write, steps + before/after,
audit, undo; general composable tools; semantic only.

## Behaviour card v1

### What exists today (measured, file:line on main 65d074f57c)

- A contact principal gets NO writes: `agent/writes.py:417` `permitted_writes` returns `[]` for
  `principal == "contact"`. Every agent write today runs through `writes.run_as_user` (`agent/writes.py:135`),
  which needs a CRM user, so it cannot serve an unlinked dealer as is.
- The dealer's own write surface already exists: the contact portal. Its form routes are ONE body shared by two
  surfaces (`api/v1/public/portal.py:1379` `register_submission_routes`); `api/v1/my_requests.py:236` already
  drives them with a transient, never-persisted `PortalToken` for a contact. The portal's checks ARE the
  dealer's permission model:
  - kind gate: `portal.py:821` `_check_kind` -> `portal_form_visibility_service.py:122` `require_form_visible`
    (403 `FORM_TYPE_NOT_VISIBLE`, per-contact form switches);
  - ownership: every read/write of a row goes through `PortalService.get_submission(token, ...)` (contact id +
    space id of the token);
  - completeness: `portal_required_fields.py:19` `REQUIRED_ON_SUBMIT`, enforced in
    `portal_service.py:1153` `submit_draft`.
- Confirm / audit machinery: `agent/actions.py:212` `confirm` (newest-only, expiry, not the same turn,
  re-check before write, claim row, per-step before/after), `agent/loop.py:540` the confirm block text.
- Router: `router.py:75` routes to the agent while an action is pending ONLY for a linked user
  (`user is not None`); `router.py:80` any open bot question keeps the message on the bot.
- Today's bot sends the dealer a portal link for complaint / stock inquiry / purchase request / sponsorship /
  price tag (`lanes/business/fetch.py:1638`, `crm_portal_link_get`), and runs escalation tickets on its own lane
  after the contact's "yes" (`lanes/escalation_services.py:143` -> conversation SLA tracking).

### Proposed mechanism (all writes below)

One general seam, not one flow per form: contact-principal write tools that run the PORTAL's own service calls
under a transient `PortalToken` for `ctx.contact_pk` + `ctx.space_id` (the `my_requests.py:236` pattern), so
the portal's kind gate + ownership + required fields are the permission check, and the audit actor is the
contact (`portal.py:94` `_portal_actor` shape, plus `auth_method="agent"`, `tool_name`). A linked staff contact
keeps its user writes AND gets the same portal writes through its linked contact, exactly as `/my-requests`
does. Proposals and confirms reuse `agent/actions.py` unchanged in shape; `router.py:75` widens to a contact
principal's pending action. One new read: the contact's own submissions (`portal.py` `portal_list_submissions`,
`PortalService.list_submissions`), so the agent can name "my complaint last week" by its number.

### Every write a dealer could reasonably ask for, least risk first

| # | Write | Reuses (file:line) | Permission checked | Confirm says | Undo |
|---|---|---|---|---|---|
| 1 | Add a note to my own open request (complaint, stock inquiry, PR, sponsorship) | `portal.py:1796` add comment; `portal.py:1857` delete comment | `_check_comment_kind` + form visible + own row | "I will add this note to your stock inquiry SI-26-0xxx: "...". Reply yes to go ahead, or tell me what to change." | "undo" deletes the note (own comment, `portal.py:1857`) |
| 2 | Stock / lead-time inquiry ("can I get 40 of X by mid Dec") | `portal_service.py:1106` draft + `:1153` submit (kind `stock_inquiry`) | form visible + required `salesperson_contact_id` (`portal_required_fields.py:21`; the requestor list always holds the contact itself) | "I will send this stock inquiry to the project sales team: SRT5733, 40 pcs, needed by 15 Dec 2026, project <name>, requested by you." | Q2 |
| 3 | Warranty / complaint claim | same, kind `complaint` | form visible + 12 required fields incl. DO number and product lines (`portal_required_fields.py:22`) | "I will file this warranty claim: DO <no>, ELP3754 x1, leaking after 3 months, within warranty: yes, ..." | Q2 |
| 4 | Purchase request / sponsorship form | same, kinds `purchase_request`, `sponsorship_form` | form visible + requestor; sponsorship unit price (`portal_service.py:1718`) | lines with quantity and amounts | Q2 |
| 5 | Sample request / price tag request | own routers `portal_sample_request.py:175`, `portal_price_tag.py:142` | their own gates | lines | their own draft delete |
| - | Talk to a person | already the bot's escalation lane (W1 hands the miss to it) | - | - | not rebuilt |
| - | Idea / suggestion | already the bot's ideate lane on WhatsApp (#2038) | - | - | not rebuilt |
| - | Place a sales order, cancel an order, change my contact details | NO dealer route exists (`fetch.py:1456` keeps `crm_order_cancel` out on purpose) | - | - | out of W2: "Please refer to your salesman." or the escalation offer, per the contact's switch |

Risk order reasoning: 1 touches only the dealer's own record and is fully undoable; 2 notifies one team, reserves
no stock and quotes no price; 3 starts a team SLA and needs a DO and usually photos (WhatsApp photos go to the
bot's media lane today, `router.py:73`); 4 carries money and approvals; 5 has its own flows.

### Real-shaped examples (masked; shapes from the W1 crew data notes and repo fixtures, the sandbox cannot reach dev data)

1. "Boss, SRT5733 can get 40 pcs by mid Dec? For project at Taman <masked>" -> write 2. Confirm block, "yes" ->
   "Sent: stock inquiry SI-26-0xxx. The project sales team replies here."
2. "For my complaint last week on CB1506SS, customer only home on Tuesday" -> own-submissions read finds
   CP-26-0xxx -> write 1. Before: 2 notes. After: 3 notes.
3. "ELP3754 leaking after 3 months, DO2026xxxx, want to claim warranty" -> write 3 (slice 2). Slice 1 answer:
   today's portal link for the complaint form.
4. "Add 10 MHS1028 to my order" -> out of W2: no dealer order route; refer / escalation offer per switch.
5. "Cancel that, I typed the wrong qty" right after write 2 -> Q2 decides.

### Edge cases (become UAC rows)

- Duplicate contact rows sharing the respond.io id: no writes (W1 fail-closed rule extends).
- Form switched off for the contact: the portal's own 403 text, "Stock inquiry is not available for your
  account." plus "Please refer to your salesman."
- A "yes" in the same turn as the proposal, a stale "yes" after expiry, a "yes" to an older proposal: refused
  by `actions.confirm` (same_turn / expired / not_newest); the reply says nothing was sent.
- A photo while a proposal is pending goes to the bot (`router.py:73`); the proposal stays and expires.
- A new question while a proposal is pending: agent (after the `router.py:75` widening), proposal stays open.
- A document passage or a pasted message that "asks" for a write: proposals take values only from the
  dealer's own words; kill test as in W1.
- Product code outside the contact's brand scope: refused at proposal by the resolver scope, no write.
- Required field missing at confirm (e.g. a staff edit in between): the re-check fails, "Not sent: <field> is
  missing", nothing written.
- Linked staff contact: user writes unchanged; portal writes through its linked contact (same as /my-requests).

### Proposed W2 slice 1

Write 1 (note on own request, with undo) + write 2 (stock / lead-time inquiry) + the own-submissions read, on
the general portal seam above. Slice 2: write 3 with WhatsApp photos attached. Slice 3: writes 4-5.

### Questions (owner)

- **W2-Q1 Slice 1 scope.** (a) notes + stock inquiry; (b) warranty claim first (the earlier W-Q4 default);
  (c) all portal kinds at once. Recommendation (a): least risk first, fewest required fields, and the
  note gives the seam a fully undoable write; the claim needs a DO, 12 fields and photos, so it is slice 2.
- **W2-Q2 Undo of a submitted form.** (a) "undo" within 10 minutes withdraws (hard delete) a submission no
  staff member has touched yet, else "it is with the team now; I can add a note"; (b) no undo after submit,
  only the portal's existing revision; (c) "yes" saves a draft and sends the portal link to submit there.
  Recommendation (a): the agent ruling needs an undo and revision is not one; (c) moves the write back to
  the portal.
- **W2-Q3 Console turns.** (a) a console turn shows the proposal and, on confirm, says what it would send
  but writes nothing (console = test, as for ideas); (b) a console confirm writes for real, as staff writes
  do. Recommendation (a), consistent with the ideas ruling; live checks run on a test contact.
- **W2-Q4 (from #2038 R3) An open escalation offer.** (a) as today: any open bot question, the knowledge-miss
  offer included, keeps the next message on the bot; (b) the router is told the offer is open and decides
  per message: a reply to the offer goes to the bot, a new question goes to the agent and the offer lapses.
  Recommendation (b): W1 arms the offer after every miss, so under (a) the dealer's next new question
  silently loses the agent; the decision stays semantic (Jev), no word list.
- **W2-Q5 Extra write cap.** (a) none beyond the existing 30 turns / 10 min and daily turn cap; (b) at most 5
  confirmed submissions per contact per day. Recommendation (a): each write already needs its own "yes";
  name the trigger (first repeated-submission case) instead of building the cap now.
