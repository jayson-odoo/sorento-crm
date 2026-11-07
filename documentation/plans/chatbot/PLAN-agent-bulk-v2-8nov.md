# PLAN: Agent bulk actions v2, make #2226 work well (AGENT-BULK-V2)

Status: Plan (STEP 1 mapping done from code; behaviour card waits on the owner's masked failing sessions, then
crew-ask). Track: named after the card (expected full: writes + permissions).

Follow-up to merged #2226 (`PLAN-agent-bulk-actions-7nov.md`). Owner beta feedback 7-8 Nov: "it didn't really work
well". This lane maps today's flow, reads the owner's failing sessions as masked evidence, files ONE behaviour card,
and builds only after the owner answers. Owner addition 8 Nov ~02:30: the card carries a short "next waves" section;
wave 1 = access grants solid, one wave per PR after it.

## STEP 1a: today's flow (main @ 90d2de22, file:line)

Paths are under `sorento_crm_backend/app/services/`.

1. **Offer.** `batch.schema_for` (`chatbot/agent/batch.py:30`) offers `crm_batch_propose` only when a `batchable`
   write is permitted (`writes.permitted_writes`); the only batchable write is `crm_contact_grant`
   (`chatbot/agent/contact_grant.py:328`, slug `user_management.contacts.edit`). Added to the turn's schemas at
   `chatbot/agent/loop.py` (`batch_schema`, in `_run`). There is NO system-prompt guidance for tables: the model learns
   the flow only from the two tool descriptions (`batch.py:43`, `contact_grant.py:335`).
2. **Parse.** The MODEL parses the pasted table: one `crm_batch_propose` call holding every row as JSON
   {`phone`, `name`, `role` enum owner/employee/unknown, `access_as_written`, `companies` [SRT|MCH],
   `customer_codes`, `customer_names`} (`contact_grant.py:343-368`). Code never sees the raw paste. Malay/English
   access words are mapped by the model from the enum description (`contact_grant.py:347-353`); the code only refuses
   a role outside owner/employee (`contact_grant.py:144-148`).
3. **Guards on the call.** `batch.propose` (`batch.py:91`): rows 1..50 (`MAX_ROWS`, `batch.py:19`, >50 = whole call
   refused, `batch.py:110`); a batch cannot share a turn with single writes (`batch.py:114`, `loop.py` `_propose`).
4. **Resolve each row.** `batch.propose_rows` (`batch.py:68`) -> `writes.propose_step` (`chatbot/agent/writes.py:549`)
   -> `_args_problem` (schema enum / maxItems 10 customers / 2 companies) -> `contact_grant._read_before`
   (`contact_grant.py:215`) -> `plan` (`contact_grant.py:128`) under `grants_scope`:
   - phone: `contact_setup_engine.normalise_phone` (`contact_setup_engine.py:54`): Malaysian MOBILE only
     (`+601` + 8-9 digits); a landline or foreign number refuses the row (`contact_grant.py:141`).
   - role: refused unless owner/employee (`contact_grant.py:145`).
   - companies: must be exactly `SRT`/`MCH` after upper-casing (`contact_grant.py:149-152`); the words "Sorento" /
     "Mocha" / "Sorento Sdn Bhd" refuse the row; an empty company refuses the row (no default).
   - customers: code exact (case/space-insensitive) or name exact with one match, inside the row's companies
     (`contact_grant._customers`, `contact_grant.py:71-105`); "ABC Trading (A123)" in one cell must be split by the
     model, else exact-name lookup fails.
   - contact: `_find_contact` by digits (`contact_grant.py:108`); two holders refuse the row; none = new contact.
   - plan: `contact_setup_engine._plan_contact` with `sheet.TEMPLATE`
     (`contact_access_sheet_service.py:42`), facets the user cannot set marked not applied
     (`contact_access_copy_service.facets_to_skip`); nothing to change refuses "Already has this access"
     (`contact_grant.py:186`). Each row re-reads `sheet._world` (`contact_grant.py:165`).
   - duplicate phone in the same table: "Same as row N" (`batch.py:76`).
5. **Preview.** `batch.preview_block` (`batch.py:153`) renders ONE table of proposed rows + a "Not changed" table of
   skipped rows with the refusal text, appended to the reply by code (`loop.py` `_run`, after `store_proposal`). The
   model is told to say only counts (`batch.py:132`). `verify_answer` accepts batch numbers (`loop.py:627`).
6. **Store.** `actions.store_proposal` (`chatbot/agent/actions.py:91`), no step cap for a batch (the 20-step
   `MAX_STEPS`, `actions.py:34`, applies only to single proposals, `loop.py:782`). Expires after `ACTION_TTL_MINUTES`.
7. **Confirm.** `actions.confirm` (`actions.py:~290`): a batch re-checks every row (`_recheck`, `actions.py:185`; a
   changed `before` fails that row only), then runs each row's `execute` in its own transaction; status
   executed / partial / rejected per row (`actions.py` batch branch).
8. **Write.** `contact_grant._execute` (`contact_grant.py:256`): re-plan, create `RespondContact` if new (default
   workspace), `engine._apply_contact`, `contact_customer_service.link_customer` (source `agent`), one commit;
   then `ContactService.assign_default_agents_to_contact` best effort for a new contact (`contact_grant.py:306`).
9. **Audit.** `audit_service.record` event `contact.access_agent` per row with before/after field words
   (`contact_grant.py:296`), actor = real user via `writes.run_as_user` (`writes.py:~160`, `auth_method` agent).

## STEP 1a: current limits / suspected weak points (to confirm against the owner's sessions)

| # | Limit | Where | Likely symptom |
|---|---|---|---|
| L1 | The whole table must come back as ONE model tool call with every row's JSON; turn deadline 45 s default (`loop.py:184` `Budgets.max_seconds`, per-call cap 60 s `loop.py:67`), Gemini flash | `loop.py` `chat` | a long table times out or the model truncates / drops rows silently |
| L2 | No prompt guidance; the model may call `crm_contact_grant` per row (single path: 20 cap, 4 calls per round, stop at first failure) or `crm_contacts_find` first | `contact_grant.py:335`, `loop.py:782`, `loop.py` `calls_per_round` | half the table proposed, or "At most 20 changes" |
| L3 | Company must be the literal code SRT/MCH; no default when the table has no company column | `contact_grant.py:149-152` | every row skipped "Name the company as SRT (Sorento) or MCH (Mocha)" |
| L4 | Customer by exact code / exact full name only; combined "Name (CODE)" cells depend on the model splitting them | `contact_grant.py:71-105` | rows skipped "No customer with the name ..." |
| L5 | Access word mapping is the model's; blank or unusual words -> `unknown` -> row skipped | `contact_grant.py:347-353`, `:145` | rows skipped "Unknown access" |
| L6 | 50 rows per Confirm, call refused whole above that | `batch.py:19`, `:110` | "ask the user to split the table" |
| L7 | Per-row plan re-reads the world and the contact snapshot (N x `sheet._world`) inside the turn deadline | `contact_grant.py:165` | slow previews for 30-50 rows, feeding L1 |
| L8 | A skipped row shows only the model's copy of phone + name and the refusal text; the user cannot fix it in place, must re-paste | `batch.py:62`, `contact_grant.py:234` | owner has to start over |
| L9 | Landline / non-MY numbers refuse the row | `contact_setup_engine.py:54` | rows skipped "not a Malaysian mobile" |

STEP 1b (owner's masked failing sessions) and the behaviour card follow; the card is posted as a `crew-ask` on the PR.

## Next waves (owner addition 8 Nov; one wave per PR, each a `batchable` WriteDef + Confirm + slug + audit)

Draft, finalised in the card: wave 1 access grants solid (this lane); then candidates grounded in what staff do by
hand today: contact tags (`contact_tag_apply.py`), customer sales-agent assignment, contact/customer field edits
(name, customer links removal), product barcode / field updates (`product_barcode_import_service.py`), supplier field
updates (`bulk_update_registry.py`, `suppliers`).
