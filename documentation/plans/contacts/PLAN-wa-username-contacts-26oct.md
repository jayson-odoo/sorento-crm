# PLAN: WhatsApp username-only contacts get a verified phone and join the contact that holds their access (WA-USERNAME-CONTACTS)

Status: Build (owner answered card section 9, 27 Oct ~00:55; rule 3 confirmed on the tap + hand-shared payloads). Phase 2 tester-first. Track: L (new chat flow, contact
merge across Respond.io and CRM, ownership proof = auth-adjacent, security-reviewer required). LEAD pattern.
UAC: `wa-username-contacts-26oct-acceptance-criteria.md` (written after the card is answered).

## Owner's words (26 Oct ~22:35, verbatim)
"for whatsapp, they allow user to share username only and not contact number, so when they first contact our
respond io, they respond io would not store the contact number, which causes the syncing to fail as phone number is
mandatory, and this also doens't link to our respond contact which control the access by contact number, so we need
a process to react to this kind of scenario to ask for their phone number, fill it in, identify any merge possibiity
(respond io will suggest the merge), do the merging to the contact that has access configured, so the user can start
using"

## Journey (draft, to confirm in the card)
detect username-only contact -> ask for phone -> prove the user owns that phone -> fill the phone -> find the
merge candidate -> merge (or hand to staff) -> access works on the next message.

## Security constraint (binding)
A username-only user who types a phone could claim someone else's number (a dealer's) and inherit that contact's
access after a merge. Nothing links or merges until ownership of the number is proven.

## Scout findings
In `CARD-wa-username-contacts-26oct.md` sections 1-2 (file:line and doc URLs there). Short form:
- Sync drops phoneless contacts silently (`sorento_crm_backend/app/services/respond_sync_handler.py:213-215`);
  `respond_contacts.phone_number` is unique NOT NULL (`app/models/access.py:268`).
- Unknown Respond.io id -> `access_denied` reply (`app/services/chatbot/engine.py:6352-6353`).
- Sync already re-points a CRM row's `respond_io_id` by phone (`respond_sync_handler.py:241-257`).
- Respond.io merge API exists: `POST /v2/contact/merge`, older contact primary (card section 8; round 1 said UI-only, corrected). Owner test: the contact with the phone survives.
- n8n: no contact-create flow; the spine posts the whole Respond.io message to `/external/chat/turn`.

## Open questions (card)
Final: card section 9 (Q1 proof (c) only, Q2 auto-merge, Q3 template text, Q4 card from a linked
contact, Q5 direct-ingress prerequisite). Rounds 1-2 (sections 6, 8) are history.

## Correction found while building
Card section 1 said an unknown contact reads "Sorry, you are not allowed to access {team}". Wrong for a contact with
NO CRM row: the turn closes silently before any stage, `_ai_allowed` at `app/services/chatbot/engine.py:2900`
(`chatbot_allowed_service.is_allowed`, `app/services/chatbot_allowed_service.py:28-36`, False with no row) ->
`_ai_not_allowed_turn` (`engine.py:2766`). The "not allowed" line is for linked contacts refused an agent. Owner
rulings are unaffected; the gate must sit before `:2900`.

Lead decision (from the repo, no owner ask): a newly created CRM contact has `chatbot_allowed = false`
(`app/models/access.py:337`; owner ruling 5 Oct, the CRM decides who the AI answers). So the verified line goes out
only when the linked CRM row has `chatbot_allowed = true`; otherwise staff get a comment ("phone verified, AI off
for this contact") and the customer gets nothing, as any not-allowed contact today.

## ARCHITECTURE
- **Layer.** Core service `sorento_crm_backend/app/services/wa_phone_link.py` (never imports `app.services.chatbot`;
  `tests/chatbot/test_import_boundary.py`) holds rule 3, the phone match and the Respond.io + CRM writes. The engine
  owns only the gate and the turn row, beside the AI-allowed gate.
- **Shared mechanisms reused, not copied.** Turn row + trace + close: `_ai_not_allowed_turn` pattern
  (`engine.py:2766-2853`: `_existing_turn` dedup, `_insert_turn`, `turn_trace.record`, `_close_turn`). Template send:
  `respond_messaging_service.send_template_for_use_case` (`:468`), `TemplateSendSkipped` = not mapped. Use-case
  registry: `TEMPLATE_DEFAULT_USE_CASES` (`app/models/respond_template.py:37`) + the FE list
  (`sorento_crm_frontend/services/whatsappTemplateService.ts:60-80` type, `:255+` `USE_CASES` entry) so the owner maps
  it on the existing WhatsApp Templates screen; no migration (`use_case` is a free String(32)). Phone normalise:
  `phone_utils.normalize_msisdn` (`:22`); CRM match `phone_number IN (num, '+num')` with `.limit(2)`, two rows =
  refuse (precedent `phone_signin_service.find_eligible`, `:93-125`). Respond.io: `RespondClient`
  (`app/services/integration_service.py:233`) `get_contact_by_phone` (`:384`, raises `httpx.HTTPStatusError`; 404 =
  no contact), `update_contact` (`:738`), NEW `merge_contacts`. CRM create: `ContactService.create_contact`
  (`app/services/contact_service.py:397`, default workspace + default agents). Reply copy: the `chatbot_reply_copy`
  registry (`app/services/chatbot_reply_copy.py:104`, `:449` pattern) for "Phone number verified, you may start
  using the AI". Actions: `send_message`, `add_comment` (`app/services/chatbot/lanes/escalation.py:1448-1462` shapes).
- **Classes fixed.** All cards (any sender) and all unknown-phoneless messages; not one payload shape.

## Contract (what the tester codes against)
`app/services/wa_phone_link.py`:
- `is_contact_card(body: dict) -> bool`: `body` = the Respond.io message event (`envelope.message`); true when
  `body["message"]["message"]["type"] == "contact"`.
- `accepted_card_phone(body: dict) -> str | None`: UAC "Accepted card"; returns E.164 digits without `+`
  (`normalize_msisdn`), else None. `channel.meta.wa_id` is read from `body["channel"]["meta"]["wa_id"]`.
- `@dataclass LinkOutcome: status: str  # "merged" | "phone_set" | "failed"`; `survivor_respond_id: str | None`;
  `contact_pk: str | None`; `chatbot_allowed: bool`; `reason: str | None`.
- `link_phone(db, client, *, contact_respond_id: str, phone: str) -> LinkOutcome`: UAC WU12, WU14, WU16. `client` is
  a `RespondClient` (tests pass a fake with `get_contact_by_phone`, `merge_contacts`, `update_contact`).
- `RespondClient.merge_contacts(contact_ids: list[int | str]) -> dict`: `POST {base}/v2/contact/merge`
  `{"contactIds": [int, int]}`, primary first.
- `respond_client(db) -> RespondClient`: the default-workspace client (the ONE seam engine tests monkeypatch to a fake).
- `send_ask(db, *, contact_respond_id: str) -> bool`: calls
  `respond_messaging_service.send_template_for_use_case(db, identifier=contact_respond_id, use_case="wa_phone_share",
  context_vars={})` through the module attribute (so tests patch `respond_messaging_service.send_template_for_use_case`);
  False on `TemplateSendSkipped`, any other error propagates to the gate as a failure (hand-off).
- **Output channel (lead ruling, 27 Oct):** every Respond.io output of this flow goes through the client seam
  directly: the ask (`send_ask`), the verified line (`client.send_message(<survivor id>, text)`,
  `integration_service.py:409`) and the staff comment (`client.create_comment(<survivor or turn id>, text)`, `:472`).
  The turn returns `actions == []` (its `reply` may carry the text for the trace). Reason: the sender addresses every
  action to the turn's own contact id (`direct_ingress.send_outcome`, `:355-392`; `documentation/n8n/chatbot-sender.md`
  table), and after a merge that id is the merged-away contact, so an action could not reach the survivor.
- Risk for the coder: the template carries a static Share Contact Info button; check `build_template_request`
  (`respond_messaging_service.py`) sends a template whose button has no parameter without error.

Engine: a gate in `engine._run_turn` right after the scope (`:2891`) and BEFORE `_ai_allowed` (`:2900`), closing the
turn with one of four new `BRANCH_KINDS` (`app/services/chatbot/contracts.py:354-372`): `phone_ask` (ask sent),
`phone_linked` (link ok), `phone_ignored` (card from a linked contact; or nothing to do inside the cap), `phone_handoff`
(staff comment). Ask cap counts `phone_ask` rows, hand-off-once counts `phone_handoff` rows, both non-test turns of
the same `contact_respond_id` in the last 24 h (`chatbot.turns.created_at`). Linked = a `respond_contacts` row with
`respond_io_id == contact_respond_id` (the `is_allowed` query, any flag value). Phoneless = `envelope.contact` has no
`phone` / `phoneNumber`. Test/dry-run turns make no Respond.io call.

## Test list (tester writes these red first)
Core (`tests/test_wa_phone_link.py`, Postgres via `tests/_pg_fixture.py`, fake client):
1. `accepted_card_phone`: tap fixture -> phone; hand-shared fixture (origin `other`, wa_id = sender) -> None; origin
   missing -> None; wa_id absent + origin ok -> phone; empty phone -> None; non-contact type -> None; `+60 10-000 0001`
   vs `60100000001` equal.
2. `link_phone`: phone contact exists + CRM row -> merge `[phone id, turn id]`, row unchanged, status merged; phone
   contact exists, no CRM row -> merge + row created (default workspace, default agents); no Respond.io contact (404)
   -> PUT `{phone: "+<e164>"}` on `id:<turn id>` + row created or existing row re-pointed, status phone_set; merge
   error / PUT error / lookup 500 -> failed, no CRM write; two CRM rows (`num`, `+num`) -> failed, no Respond.io write;
   phone contact id == turn id -> no merge.
3. `merge_contacts` builds the right request (httpx mocked, no network).
4. Logs: no full phone in caplog (WU18).
Engine (`tests/chatbot/test_wa_phone_link_gate.py`, harness `tests/chatbot/test_engine.py` `_envelope`, `seeded`,
`stub_parser` with a never-called hook; asserts modelled on `tests/chatbot/test_ai_allowed_gate.py:84-104`):
5. card from a linked contact -> `phone_ignored`, actions [], parser never called, no Respond.io call (WU1, WU2).
6. text from unknown phoneless -> `phone_ask`, template sent for `wa_phone_share` to the turn contact, parser never
   called (WU3, WU6); a typed phone number is the same (WU9).
7. 3 asks in 24 h, 4th -> `phone_handoff` with one `add_comment`; 5th -> `phone_ignored`, nothing sent (WU7).
8. not mapped (`TemplateSendSkipped`) -> `phone_handoff`; second message in 24 h -> `phone_ignored` (WU8).
9. hand-shared card from unknown -> `phone_ask`, no merge / PUT (WU10).
10. accepted tap from unknown: link ok + `chatbot_allowed` true -> `phone_linked` + `send_message` with the verified
   line; link ok + false -> `phone_linked`, `add_comment` only; link failed -> `phone_handoff`, no `send_message` (WU15,
   WU16, lead decision).
11. unknown WITH phone in envelope -> not a phone kind (today's `ai_not_allowed`) (WU4).
12. same envelope twice -> one merge (WU17).
13. test / dry-run turn -> no Respond.io call.
14. `wa_phone_share` is in `TEMPLATE_DEFAULT_USE_CASES`; FE vitest: the WhatsApp Templates use-case list has it.

## Hand test on the crew copy (crew audit 27 Oct: never a live Respond.io merge)
The copy routes every Respond.io call to a dead proxy (`crew.toml` egress block) and its Respond.io settings live in
the shared dev DB, so no stub can be wired in safely. The hand test is therefore decision-level, on the copy's own
data (`sorento_prod_1020`), with no LLM call (every phone decision is taken before the parser).

Replay tool (outside the repo: `crew/state/handtest/1888/replay_wa_username.py`; no real data in git). Run with the
copy's backend venv and `.env` (so DB = the copy's, egress = blackholed). Args: `--dealer-respond-id`,
`--dealer-phone` (a real dealer contact crew picks: access configured, AI on), `--api` (the copy's API base URL).
Each step uses a FRESH fake username contact id (`9000xxxxx`, random per run) so the 24 h hand-off silence of one
step never hides the next. A step = the webhook's own store step (`map_webhook_message` + `upsert_message_row`,
so Chat History shows the message) then the turn the drain runs (`engine.run_turn(direct_ingress.envelope_for(...))`),
printing branch kind + trace summary. Steps:
1. username contact texts "hi" -> phone flow, ask attempted; Respond.io unreachable -> `phone_handoff`.
2. username contact hand-shares a card with the dealer's number (origin `other`, wa_id = sender) -> not accepted,
   no link attempted -> `phone_handoff` (ask attempted).
3. username contact taps (origin `contact_request`, wa_id = card phone = the dealer's number, signed ingress) ->
   accepted, link attempted, Respond.io unreachable -> `phone_handoff`; the dealer's CRM row is unchanged.
4. the dealer's own (linked) contact sends a card -> `phone_ignored`, no reply, no business answer (the side bug).
5. the step-3 tap with ingress `webhook` (the n8n path) -> not accepted -> `phone_handoff` (ask attempted).
6. `POST {api}/api/v1/external/chat/turn` with ingress `respond_webhook` and the copy's integration key -> 422.
Every attempted send leaves a failed Respond outbox row (WU24), visible in Integration Logs. The merge and the
CRM re-point are proven by the pytest suites (fake client), not on the copy.
