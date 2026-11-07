# PLAN: Agent bulk actions v2, make #2226 work well (AGENT-BULK-V2)

Status: Plan (STEP 1 done; behaviour card posted as crew-ask on PR #2241, 8 Nov; build waits on the owner's
answers). Track: named after the card (expected full: writes + permissions).

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

## STEP 1b: what the owner's sessions show (crew evidence, 8 Nov 01:18-01:22 MYT, masked, not committed)

4 bulk tries, 12 rows, 0 proposed, no Confirm card, nothing written. The model parsed every table right (one
`crm_batch_propose` call, access words and companies mapped correctly), so L1, L2, L3, L5 did NOT bite. What bit:

| Case | What went wrong | Root cause |
|---|---|---|
| Short dealer name ("Dealer H", Mocha; "Dealer F", Sorento) | row skipped "No customer with the name X in your companies" although 3 (H, MCH) and 6 (F, SRT) active accounts carry that name | `_customers` matches a name only by full equality (`contact_grant.py:101-104`); real dealers have several accounts per company ([A/C I], [CERAMIC], (PROJECT)) |
| Same | the message says "no customer" when there are 3-6, lists none, asks nothing | 0 exact rows -> "No customer with the name" (`contact_grant.py:86-87`); the model is told only "tell the user why, row by row" (`batch.py:127`) |
| Every row skipped | no code-built table at all, only the model's prose "please correct and submit again" | the preview block is appended only when a proposal is stored (`loop.py:1809-1819`, `if ... steps`) |
| Row with a bad phone AND an unknown code | only the phone is reported | `plan` raises at the first problem (`contact_grant.py:140-160`: phone, role, companies, then customers) |
| 2 of 4 turns | an extra model round | the reply's "not found" wording is checked against `crm_resolve` terms (`loop.py:695-709`), and a batch skip is not one |

## Behaviour card (crew-ask on PR #2241)

Target: the owner pastes the table the way he writes it (dealer short names allowed); nothing is guessed, but a name
that fits several accounts becomes a pick, not a dead end.

1. Customer cell resolution, in order: exact code -> exact full account name (one match) -> otherwise LIST the active
   accounts of the row's company whose name contains what was written (up to 10, code + full name), and the row
   waits for the owner's pick. Never linked without the pick. 0 candidates in the row's company but some in the other
   company = say so ("X is a Sorento account here, the row says Mocha"). 0 anywhere = "no customer named X".
2. The preview is ALWAYS the code-built table, even when no row is ready, in three parts: Ready (goes on Confirm),
   Needs your choice (numbered accounts per row), Not changed (every reason for that row, not only the first).
3. The owner answers in chat ("row 2: H001 and H003", "row 1 all", "row 3 skip"); the agent re-proposes the whole
   table with those codes, replacing the card. "all" = every listed account of that row, an explicit choice.
4. A batch skip reason backs the reply's not-found wording, so no repair round.

Example (masked: dealer names and account codes replaced, from B3/B4):

| # | Phone | Name | Status | Detail |
|---|---|---|---|---|
| 1 | PHONE-3 | Person A | Needs your choice | "Dealer F" (Sorento): F-1 DEALER F SANITARYWARE [A/C I]; F-2 (PROJECT); F-3 [A/C II]; F-4 [A/C III]; F-5 [A/C IV]; F-6 DEALER F BATH CONCEPT (PROJECT). Reply with codes, "all", or "skip" |
| 2 | PHONE-1 | Person B | Needs your choice | "Dealer H" (Mocha): H-1 [A/C I]; H-2 [CERAMIC]; H-3 [IBORN] |
| 3 | PHONE-2 | Person C | Not changed | no customer named "No Such Shop Sdn Bhd" in Sorento or Mocha |
| (B1 r1) | P1 | Person A | Not changed | "P1" is not a Malaysian mobile number; no customer with code C1 |

Owner replies "row 1: F-1, row 2 all" -> card: row 1 Business owner (Sorento) + link F-1; row 2 Employee
(Mocha) + link H-1/H-2/H-3; row 3 not changed; Confirm 2 changes.

Edge cases: more than 10 accounts contain the name (list 10, "give a longer name or the code"); a written name that
is an exact full name of one account (linked, as today); inactive accounts never listed; the pick names a code not
in the list (row stays waiting, said why); the owner confirms the ready rows first, then picks (the re-proposal
shows confirmed rows as "already has this access"); a candidate outside the user's companies is never listed.

Questions (each with a recommendation):

- Q1 Short name fitting several accounts: (a) list and let the owner pick, with "all" as one choice; (b) link every
  account of that dealer in the row's company automatically. Rec (a): standing rule "explicit links only"; (b) is
  name matching by another name, and [A/C I] vs (PROJECT) accounts are not always the same person's business.
- Q2 How the owner picks: (a) reply in chat, the agent re-proposes the table; (b) pick buttons on the card (new UI).
  Rec (a): no new component, uses the existing replace-the-proposal path (`batch.py:116-117`).
- Q3 Rows that are ready while others wait: (a) Confirm card now for the ready rows, waiting rows listed and left
  out; (b) no Confirm until every row is ready or skipped. Rec (a): the owner is not blocked by one unclear row.
- Q4 Candidates: active accounts of the row's company whose name contains the written words, at most 10. Rec yes;
  also offer an office customer group with exactly that name as one candidate ("group DEALER F, 6 accounts") ONLY if
  the dev DB shows such groups exist (asked below), else not built.
- Q5 Next wave after this one: Rec wave 2 = contact tags from a table (below), because the apply engine with preview
  and not-applied facets already exists (`contact_tag_apply.py`).

## Next waves (owner addition 8 Nov; one wave per PR, each a `batchable` WriteDef + Confirm card + slug + audit)

Wave 1 = this lane (access grants solid). Candidates, ordered by how much existing engine each reuses:

| Wave | Chore from a pasted table | Reuses | Slug (to confirm per wave) |
|---|---|---|---|
| 2 | Contact tags: set / clear tags per phone | `contact_tag_apply.py` (preview, not_applied, per-contact savepoint) | contacts edit |
| 3 | Assign a sales agent to customers (code -> agent) | `POST /sales-agents/{id}/customers` (`api/v1/master_data/sales_agents.py:181`) | sales agents edit |
| 4 | Contact edits: AI replies on/off, unlink a customer, rename | `crm_contact_access_update` (`writes.py:920`) keyed by phone instead of id | contacts edit |
| 5 | Product field updates (barcode first) | `product_barcode_import_service.py` resolve/apply | products edit |
| 6 | Supplier field updates | `bulk_update_registry.py` (`suppliers`) | suppliers edit |

The batch tool, preview table, needs-a-choice part and per-row confirm built in wave 1 are shared; a wave adds one
WriteDef with `batchable=True`, its preview cells, its batch key, and its tests.
