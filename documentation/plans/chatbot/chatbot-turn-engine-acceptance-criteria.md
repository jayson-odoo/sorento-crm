# UAC - Chatbot Turn Engine (n8n business logic moves into the CRM)

Plan: `documentation/plans/chatbot/PLAN-chatbot-turn-engine.md`
Predecessors: `documentation/plans/ideation/PLAN-ideation-ideate-intent.md` (the one lane that
already runs this way), n8n repo `sorento_crm_n8n/n8n-workflows-init/plans/spine-decomposition-plan.md`
(RS-0 to RS-9, the decomposition this port consumes).

## Journey

Four actors. The customer's journey is the contract that must NOT change. The other three are
the reason the work exists.

### A. Customer on WhatsApp (behaviour byte-identical to today)

Actor: a dealer or end user messaging Sorento on WhatsApp, arriving from respond.io.

1. They send a message (text, voice, photo, or a numbered reply to a list the bot showed).
2. Within the same few seconds as today, the bot answers: a product / stock / order / promotion /
   incoming / document answer, a numbered picker, a tier question, a did-you-mean offer, a
   clarification, an escalation offer, or a canned refusal. The wording, the numbering, the quick
   replies and the attachments are the ones today's n8n graph produces.
3. A bare digit or a tier word on the next turn resolves against the SAME list the bot showed,
   because the bot remembered what it offered.
4. Accepting an escalation assigns a real staff member, posts the PIC comment, and starts the SLA
   clock, exactly as today. Declining says "Escalation declined." and stops.
5. Two messages sent quickly are answered in the order sent, never interleaved.
6. If the bot fails mid-turn, the customer gets today's error reply, and the failed turn is now
   RECORDED, not dropped (the only visible delta, and it is invisible to the customer).

Derived, never asked: nothing changes for the customer. No new question, no new menu.

### B. Owner edits bot copy without touching n8n

Actor: the owner, in Settings > AI Prompts (existing screen).

1. They open the prompt registry and see new keys for the bot's canned replies (clarify menu,
   not-supported, escalation offer, demand quantity, access denied) and the two bot prompts
   (semantic parser, small-talk clarifier).
2. They edit the not-supported reply, publish it. The next WhatsApp turn uses it. No n8n change,
   no deploy.

### C. Developer changes bot behaviour

Actor: a developer (or Claude) asked to change a routing rule or a reply.

1. They open one Python package (`app/services/chatbot/`), find the rule by name (`route.py`,
   `compile_state.py`, ...), edit it.
2. They run `pytest tests/chatbot -q`. The replay suite (real captured n8n executions) tells them
   in under a minute which turns changed behaviour and how.
3. They open a PR. CI runs the same suite. Review, merge, deploy. n8n is not opened.

Derived, never asked: which n8n node to edit, which by-name reads it breaks, which sub-workflow
fork to promote. All gone.

### D. Operator troubleshooting a turn (owner ask, 4 Sep review: "human friendly, simple")

Actor: the owner or a technical staff member, in System > Chat History (existing page), after a
customer says "the bot did not answer" or "the bot answered wrongly".

1. They open the contact's thread. Every incoming message now carries a **Turn** line under it:
   a status word (Answered, Escalated, Asked to clarify, Failed at understanding), the lane in
   plain words ("Business query: product"), and the total time. Failed turns are red and the
   list can be filtered to "Failed turns only".
2. They expand the turn and read a timeline in sentences, one row per stage: Received,
   Understood, Access, Routed, Looked up, Replied, Remembered, Sent. Each row says what
   happened in words ("Understood as a business query about product SRTWC8517, dealer tier"),
   why ("Routed to the business lane because access is allowed and no escalation was asked"),
   and how long it took.
3. A failed stage shows the reason in one sentence, a Retry button (when R4 allows), and a
   "Technical details" collapsible with the raw payloads for the engineer, searchable, the same
   viewer the AI-assistant trace already uses.
4. "Remembered" shows what the bot will carry into the next turn (kept, new, cleared), so a
   wrong follow-up answer can be traced to the memory, not guessed.

Derived, never asked: nothing to configure. The trace is written by the engine on every turn.

## Decisions (locked with the owner, 4 Sep 2026)

- D1 **Cut line = transport only.** n8n keeps: respond.io webhook in, contact lookup, media
  fetch + media intake (the existing `sub-media-intake`, already CRM-backed), respond.io send,
  conversation assign, PIC comment, contact-field update. Everything between the inbound envelope
  and the outbound actions is the CRM.
- D2 **State owner moves with logic.** The CRM reads and writes `respond_contacts.session_vars`
  itself. n8n's `save-session-vars` PUT is deleted at S2 and never returns. One writer.
- D3 **Module, not core.** `chatbot` is an installable module (`MODULE_KEY = "chatbot"`,
  `require_module_enabled_with_api_key("chatbot")`), one package, one public entry point. Core
  never imports it. Per-client behaviour = per-tenant data, never code branches. Not a separate
  service now; the lift trigger is named in the plan.
- D4 **Synchronous turn, caller sends** (revised at review round 3, owner: "can't we just
  return the data and n8n process?"). `POST /chat/turn` runs the whole turn and returns
  `{reply, actions}`; the CALLER executes them. Egress therefore stays with whoever called:
  the live spine sends, the fail-closed test clone (`Hnd4S8SVH6pftjxs`) records to
  `test:egress` and never sends. No outbound webhook, no callback URL. n8n already waits the
  whole turn today (`call-spine` `waitForSubWorkflow: true`), so this is no slower for n8n.
  Worker offload is OPTIONAL: the request runs the turn in-process like the ideation endpoint;
  if p95 turn latency or API CPU crosses the named trigger, the request enqueues on the `chat`
  queue and waits for the result (the `/external/media` enqueue-and-wait pattern). Not built
  until measured.
- D5 **Configurable = existing stores, not a rule engine.** Canned copy and the two prompts live
  in the prompt registry (versioned, has an admin UI). The respond.io `space_id` (hard-coded
  `364817` in n8n) comes from the default respond workspace row. One new `system_settings` column:
  `chatbot_unsupported_domains`. Nothing else gets a knob until the owner changes it twice.
- D6 **Ideation is an MCP tool** (owner, twice: "ideation should be at the MCP side"). A new
  write tool `crm_ideation_turn` in `sorento_crm_mcp/catalog.py` wraps
  `POST /external/ideation/turn`, is synced into `mcp_tools`, and the engine's `ideate` branch
  calls it through the same in-process MCP client as every other tool (D10). Ideation is not
  special-cased anywhere: not an n8n lane, not a direct service call. The n8n
  `ideate-turn-http` node is deleted at S3.
- D7 **Strangler by turn stage, then by lane.** Head (parse + route) first, tail (compose +
  persist) second, then lanes one at a time, ingress/dispatch last. Every slice leaves production
  working and is independently revertible by re-wiring n8n.
- D8 **Parity before improvement.** Each ported function is proven against the captured n8n
  fixtures BEFORE any hazard is fixed. A fix is a separate, named, tested divergence.
- D9 **n8n sends.** The CRM can send WhatsApp today (`send_text_or_template`), but the owner
  wants sending to stay in n8n. The engine returns `actions[]`; the caller executes them.
- D15 **Ingress-agnostic and idempotent per message** (round 5, owner: the respond.io webhook
  fallback poller). Both injectors (`sorento-main` webhook producer and the failover poller's
  `sorento-main-INJECT`) post the same envelope shape; the engine never knows or cares which.
  `chatbot.turns` is unique on `(contact_respond_id, message_id)`; a duplicate delivery
  returns 200 `{duplicate: true}` with the original turn's reply and actions and the caller
  sends nothing. The envelope carries `ingress: webhook | poller | retry | console`.
- D16 **LLM for language understanding and reasoning only** (owner, round 6). The parser prompt
  carries no deterministic logic: no arithmetic, no enum-to-team mapping, no date maths, no
  positional resolution rules, no state carry rules. Those live in `output_exchange.py` and the
  lanes (D11's other half). S1 ships parity first, then S1b slims the prompt by moving every
  rule that is not language understanding into code, proven by the same replay corpus and the
  live parity script: same outputs, smaller prompt, no overfitting to sample phrasings.
- D14 **Dry run is a first-class input.** An envelope with `is_test = true` (or a
  `test_run_id`) makes the engine do ZERO writes: no session-vars write, no next-assignee, no
  SLA row, no chat-history ingest. The response carries the would-be `session_patch` and every
  action flagged `dry_run: true`. Console and clone turns are safe by construction, not by
  which URL they hit.
- D10 **MCP reads stay MCP-shaped.** The business lane calls the MCP server through the existing
  in-process `MCPRuntimeClient` (precedent: `ai_assistant_service`), so tool output keeps the
  presenter shape `output-structurer` was written against. No re-shaping.
- D11 **Semantic in, deterministic processing** (owner, 4 Sep review). Understanding the
  customer's text is the parser's job (LLM). Everything after the parser is deterministic and
  works on structured state, never on raw text: no regex or fuzzy match over the customer's
  message or over a previous reply. That is why the frozen string contracts (H13) become a
  persisted `pending` marker. Existing text-sniffing sites in the ported code are reproduced
  for parity, inventoried during S1, and listed as divergence candidates to move into the
  parser prompt after parity (see plan "Text-sniffing inventory").
- D12 **Own schema.** The module owns Postgres schema `chatbot` (`chatbot.turns`, cross-schema
  FKs to `public` where needed), per PRINCIPLES "dedicated schema for namespace and clean
  uninstall". `respond_contacts.session_vars` stays in `public` (shared with ideation).
- D13 **A turn trace screen is in scope.** Every turn writes a human-readable stage trace; the
  Chat History thread drawer shows it (journey D). FE mock first (Phase 1), then backend.

## Rulings (plan review, 4 Sep 2026)

- R1 **RESOLVED**: port with the correct vocabulary (`check_stock`) and gate the
  `stock_denied` / `demand_qty` lanes behind `system_settings.chatbot_stock_denial_enabled`
  (boolean, default off). Turning them on is a data change with a test.
- R2 **RESOLVED (owner overruled the recommendation)**: keep every session key, including the
  nine with no reader today ("all these have purpose, don't drop"). `SessionVars` allowlist =
  every key `compile-current-state` writes. Nothing is dropped, at S2 or S8.
- R3 **RESOLVED by principle D11**: the two frozen string contracts become the persisted
  `pending` marker. S1 reader accepts both forms, S2 writes the marker, S8 removes the regex.
- R4 **RESOLVED (round 2)**: no automatic retry. A failed turn is recorded as `failed` with its
  stage and reason, the customer gets today's error reply, and the trace screen offers a manual
  Retry button (S2b). Fact recorded for the file: n8n does NOT retry today either; the
  dispatcher pops the message and drops it on error (`plans/concurrency-plan.md` locked
  decision 6, accepted risk 2). The only retries are node-level `retryOnFail` on two single HTTP
  calls.
- R5 **RESOLVED (round 2)**: "the parser shouldn't output invalid JSON". Enforced at the source:
  the parser call uses the provider's strict structured output (`json_schema` on
  `llm_provider.chat`, the same mechanism `ai_semantic_parser` uses), so a well-formed object
  is guaranteed whenever the provider answers. Anything else (provider error, timeout, refusal,
  or a validation failure that strict mode cannot prevent) is a failed `understood` stage:
  error reply, `failed` turn, visible on the trace screen. No soft default (H44 closed).
- R6 **RESOLVED**: `live-respond-send-user`, `live-respond-close-convo` and the
  human-intervened sweeper are out of scope; backlog item with its own plan.

## Acceptance criteria

Tags: `[BE]` backend code, `[T]` test, `[N8N]` n8n transport edit, `[E2E]` real turn on the test
clone or live. Each AC traces to a journey step (A1 to D1).

### S0 - Module scaffold, inbox, replay harness (journey C, D)

- AC-001 `[BE]` Given the backend, when it boots, then `app/modules/chatbot/bootstrap.py` declares
  `MODULE_KEY = "chatbot"`, `MODULE_MANIFEST` carries the `chatbot` entry with its dependencies,
  and `app_modules_catalog` is seeded with it on first run. (C1)
- AC-002 `[BE][T]` Given the package `app/services/chatbot/`, when any module outside
  `app/api/v1/external/chat.py`, `app/tasks/chat_turns.py`, `app/modules/chatbot/` or
  `tests/chatbot/` imports from it, then `tests/chatbot/test_import_boundary.py` fails naming the
  importer. (C1)
- AC-003 `[BE]` Given the `chatbot` migration, when applied, then schema `chatbot` exists and
  table `chatbot.turns` exists with `id, contact_respond_id, envelope (jsonb), status
  (queued|processing|delegated|done|failed), stage, branch_kind, error, attempt (int, default
  1), message_id text, ingress text, trace (jsonb: ordered stage records `{stage, status, started_at, ms, summary, why,
  facts, error, raw}`), response (jsonb), created_at, started_at, finished_at`, indexed on
  `(contact_respond_id, status, created_at)` and UNIQUE on `(contact_respond_id, message_id)`
  (D15); the model pins
  `__table_args__ = {"schema": "chatbot"}` (D12). (D1, D13)

  `response` was added at implementation (4 Sep 2026) and is listed here so the written AC
  matches the migration. It holds the answer the turn returned, `{ctx, item, actions}`
  today and `{reply, actions}` from S3. D15 needs it - "a duplicate delivery returns the
  ORIGINAL reply" is not implementable without persisting one - and S2b's Retry reads the
  same column. **Bounded on purpose:** it is written when the turn CLOSES, so a duplicate
  that arrives while the first turn is still `processing` (the likely timing, since the two
  injectors are seconds apart and a turn takes seconds) replays `duplicate: true` with a
  null `ctx` and `status: processing`. Waiting for the first turn would buy nothing - the
  caller must not answer twice either way - so what guarantees no null is dereferenced is
  n8n's Switch on `duplicate` sitting BEFORE the `build-ctx` / `route-turn` re-emitters
  (AC-110, and the plan's S1 n8n section).
- AC-007 `[BE][T]` Given any stage of a turn, when it completes or fails, then the engine
  appends one trace record with a plain-language `summary` and `why` (no JSON in either), and
  `raw` holds the technical payload; a test asserts every stage name in
  `contracts.TurnStage` appears in a full happy-path trace. (D1)
- AC-004 `[T]` Given `CHATBOT_FIXTURES_DIR` points at the sibling n8n checkout
  (`sorento_crm_n8n/n8n-workflows-init/tests/fixtures`), when `pytest tests/chatbot` runs, then
  every fixture under `nodes/<slug>/<node>/` for a ported node is replayed through its Python
  port and `expected` is compared after a JSON round trip; when the directory is absent the
  corpus tests SKIP with a message and the vendored subset under `tests/fixtures/chatbot/` still
  runs. (C2)
- AC-005 `[T]` Given a ported node with an intentional divergence (a hazard fix), when its
  fixture disagrees, then the test passes only if the case is listed in
  `tests/chatbot/divergences.py` with the hazard id and a one-line reason; an unlisted
  divergence fails. (C2)
- AC-008 `[T]` Given a slice PR, when it opens, then `tests/chatbot/COVERAGE.md` (generated by
  `scripts/chatbot_fixture_coverage.py`) shows at least 5 real captures per branch of every
  node the slice ports; fresh captures come from the n8n repo's `scripts/capture-fixtures.py`
  recipe, never hand-written. The 1,535 starting corpus is a floor. `COVERAGE.md` is kept
  honest by `tests/chatbot/test_coverage_fresh.py`, which fails when it drifts from the
  corpus. (C2)

  **Two states are under the bar and do NOT block** (amended 4 Sep 2026, after the first
  capture run):

  - `exhausted (n)` - the branch has fewer than 5 real captures AND the capture agent's
    report says the live pool for the CURRENT workflow version was scanned end to end. The
    traffic does not exist, so no further capturing produces it and blocking would block
    forever. The scanned counts are recorded at the top of `COVERAGE.md` with their capture
    date and workflow version, so the claim is auditable rather than asserted: spine
    `51f7b0d2` 567 of 946 executions, parser `ab3ec985` 239 of 3,901 (the remainder in each
    pool ran on older versions and cannot be graded against the body the export ships).
  - `dead by vocabulary` - live cannot reach the branch at all. `demand_qty` and
    `stock_denied` are the two: the spine tests `intent_hint === 'stock_check'` while the
    parser emits `check_stock` (H1), so 0 captures is the CORRECT number, not a gap. These
    are covered by unit tests behind `chatbot_stock_denial_enabled` (AC-306, R1).

  A cell short in a pool that was NOT fully scanned still blocks, and the report says which.
- AC-009 `[T]` Given the world corpus, when S2 opens, then it holds 100+ worlds including
  multi-turn worlds (3 to 5 turns of one contact) covering picker, did-you-mean, tier ask,
  escalation, offer-hold and media shapes; each later slice tops up its own lanes. (C2)

  **Measured at S2, not S1** (amended 4 Sep 2026). The n8n repo has no worlds tooling and
  exactly ONE hand-built world (`worlds/exec-14855423-live-casual`), so "100+ by S1" was a
  target against a capability that does not exist. It does not need to: a spine capture
  already carries every node output of its execution in `ctx`, so a world is DERIVED from
  one rather than captured separately. The S2 harness builds them from the spine captures
  the S1 corpus already holds (116 route-turn / 114 build-ctx today), which is also when the
  tail exists to replay them end to end. S1's gate is node replay (AC-102, AC-103); world
  replay is S2's.

  **MET at S2 (5 Sep 2026), after the tail capture batch.** `tests/chatbot/worlds.py`
  derives **166 worlds** and **26 multi-turn chains** (114 turns) and
  `tests/chatbot/test_worlds.py` replays each through `run_turn` + `complete_turn` with
  the parser, the access check and the CS roster read stubbed from that execution's own
  node outputs. 86 single-turn worlds and 6 chains grade today; the rest carry a NAMED
  body difference or are spine-only captures whose resolver and entity gate ran inside a
  sub the fixture never recorded.

  A world is either GRADED or SKIPPED BY NAME. Nothing is partly excused: the only two
  allowed value differences anywhere are the `pending` marker and `dym_offer.id`, which
  is `$execution.id` becoming the CRM turn id.

  Per shape: `plain` 81, `escalation` 37, `did_you_mean` 25, `picker` 10, `tier_ask` 9,
  `media` 4, **`offer_hold` 0**. The last one is EXHAUSTED, not short: 0 of 556
  `route-turn` runs in the scanned pool took that arm, so no further capturing produces
  one and it is covered by unit tests instead. `media` is bounded the same way - the pool
  held 2 voice, 1 video and 8 already-handled images, so the head never runs on more.

  **The source changed, and that is why the number moved.** A world used to need seven
  named head nodes; it needs TWO - `build-ctx` and `crossdomain-compose` - because every
  input is a producer's output VERBATIM on the `build-ctx` hub, which is what that node
  is for. That is what lets the `sub-output-live` captures (the tail's own workflow,
  running the body the port implements) make worlds at all, and they are the best source
  in the corpus: the hub plus the thirteen trigger fields is a complete world by
  construction.

- AC-006 `[BE][T]` Given a caller with a valid integration key but without the slug
  `integration.chat_turn.submit`, when it calls any `/api/v1/external/chat/*` route, then 403
  `permission_denied` naming the slug; with the slug and the module disabled under strict mode,
  then 403 `Module not enabled: chatbot`. (C1)

### S1 - Head: parse + access + route (journey A2, A3, C1)

- AC-101 `[BE]` Given `POST /api/v1/external/chat/turn` with body `{ envelope }` (the redis queue
  item `A` shape: `{message: B, contact, test_run_id?, scope?, mode?}`), when the contact exists,
  then the engine (a) inserts a `chatbot_turns` row, (b) reads session vars (with
  `referenced_result_set` / `referenced_state` when `message.replyTo` is present), (c) runs the
  semantic parser, (d) runs the contact-to-agent access check (the service behind `POST /external/access-agent/check`), (e) routes, and responds
  `{ turn_id, ctx, item, branch_kind, delegate }` where `ctx` is the six-key hub shape and `item`
  is byte-equal to what `route-turn` emits today (tag-only arms get `{branch_kind}` only). (A2)
- AC-102 `[T]` Given every `route-turn` fixture in the corpus, when replayed through
  `chatbot.head.route.decide`, then `branch_kind` and the stamped item are equal to `expected`. (A2)
- AC-103 `[T]` Given every `output_exchange` and `suggest-follow-up` fixture (parser
  post-processing, input = `_parser_raw` + previous state), when replayed, then the derived
  `output` is equal to `expected`, including the 69 derived keys and the unicode-dash
  normalisation. (A2, A3)
- AC-104 `[BE]` Given the parser prompt, when the engine calls the LLM, then it renders prompt key
  `chatbot_semantic_parser` from the registry (fallback = the live n8n system message, verbatim),
  temperature 0, JSON output validated by a Pydantic model whose keys are exactly the 27 declared
  output keys, and the model/provider come from `ai_prompt_registry.agent_model` with the
  AI-assistant config as fallback. (A2)
- AC-105 `[BE][T]` Given the parser call, when it runs, then it passes the strict
  `ParseOutput` JSON schema to the provider (structured output, R5); given a provider error,
  timeout, or a response that still fails `ParseOutput` validation, when routing would run,
  then the turn is marked `failed` with `stage = understood`, the response carries
  `delegate = null` and `reply = <today's parser-error reply>`, and no default routing
  happens. (A6)
- AC-106 `[BE][T]` Given a session whose `response` string carries the legacy escalation-offer
  prefix OR whose `pending.kind == 'escalation_offer'`, when the parser post-processing computes
  `offeredEscalation`, then both forms are recognised (R3, migration window). (A4)
- AC-107 `[BE][T]` Given an envelope whose attachment type is still `audio` (media intake did
  not patch it), when the head runs, then the turn is `failed` at `stage = intake` with an
  explicit error and today's error reply, never a silent empty run (H5). (A6)
- AC-108 `[BE][T]` Given the contact's `is_human_intervened` custom field is true, when the head
  runs, then the response `actions` contains `{kind: update_contact_fields, fields:
  {is_human_intervened: false}}` and the turn continues, matching today's `set-human-intervened`
  path. (A1)
- AC-109 `[T]` Given every enum the parser emits (`message_type`, `intent_hint`, `domain_hint`,
  `suggested_team`, `suggested_agent`, `entities[].hint`, `selection_context`), when any Python
  module declares one, then it imports the single `Literal` in `contracts.py`; a contract test
  greps for duplicated string sets and fails on a second copy (H28). (C1)
- AC-110 `[N8N]` Given the live spine, when S1 is promoted, then the nodes `get-session-vars`,
  `Call 'sub-query-reformulator'`, `check-access`, `build-ctx`, `route-turn` are replaced by one
  `httpRequest` to `/chat/turn` plus two one-line Code nodes named `build-ctx` and `route-turn`
  that re-emit `response.ctx` and `response.item`, so every by-name reader downstream is
  unchanged; the old nodes stay in the workflow disabled for one release. (A2)
- AC-111 `[E2E]` Given the fail-closed test clone, when the 15-turn smoke set
  (`tests/uac/RS.md` clone smoke) runs against the S1 build, then every turn reaches the same
  lane and the same reply text as the pre-S1 run. (A2 to A4)

### S1b - Parser prompt slim-down (journey A2, C1; D11, D16)

Runs after S1 parity is green and before S1 promotes, in the same lane.

- AC-151 `[T]` Given the 48 KB parser system message, when S1b starts, then
  `documentation/plans/chatbot/parser-prompt-inventory.md` classifies every section as
  `understanding` (stays), `rule` (moves to `output_exchange.py`), `example` (kept only if it
  covers a phrasing class the corpus shows, never a single sample), or `dead` (no fixture
  exercises it), with the fixture ids that justify each row. (D16)
- AC-152 `[BE][T]` Given a `rule` section (enum-to-team map, date maths, positional resolution,
  carry rules, quantity parsing), when it moves to code, then a unit test covers it and the
  prompt no longer mentions it; the combined parser + post-processor output equals `expected`
  on every parser fixture (parity unchanged). (D16)
- AC-153 `[T]` Given the slimmed prompt, when the live parity script runs on the
  regression-guard inputs plus a 200-turn fresh sample, then agreement with the pre-slim
  parser on the 27 declared keys is 99%+ and every disagreement is triaged as
  `improvement | regression`, with zero untriaged regressions before promote. (D16)
- AC-154 `[BE]` Given prompt size, when S1b lands, then the system message is at least 40%
  smaller by characters, the number is recorded in the PR, and the prompt is published as a
  new registry version (rollback = move the label). (B2, D16)
- AC-155 `[T]` Given an input in Malay or mixed Malay-English from the corpus, when parsed,
  then the slimmed prompt's output equals the pre-slim output (language coverage is an
  understanding property, not an example table). (A1, D11)

### S2 - Tail: outcome, compose, persist (journey A3, A4, D2)

- AC-201 `[BE]` Given `POST /api/v1/external/chat/turn/{turn_id}/complete` with body = the
  `sub-output` trigger contract (`item, result, resolved, gate, offer_hold, suggest_offer,
  not_found, incoming_picker, access_choice, crossdomain_render, answer, clarify`, all nullable
  except `item`), when called, then the engine runs build-outcome, the CS member offer (team
  members in-process), compile-current-state and crossdomain-compose, writes session vars
  in-process, marks the turn `done`, and responds `{ reply: {text, quick_replies, result_set,
  attachments_src}, actions: [] }`. (A2, A3)
- AC-202 `[T]` Given every `compile-current-state`, `crossdomain-compose`, `build-outcome`,
  `escalate-catalog`, `cs-roster-plan`, `build-cs-member-offer` fixture, when replayed, then
  `reply.text`, `reply.quick_replies` and `session_patch.variables` equal `expected`, the only
  registered divergence being the added `pending` marker (R3). (A3)

  **MET, with one divergence more than this line predicted** (5 Sep 2026): 1,321
  fixtures replay green across the six tail nodes and S1's four. The `pending`
  divergence is FIELD-scoped, not blanket - the named path comes off both sides and
  every other byte is still compared, because a whole-node exemption for one added key
  would make that node's replay vacuous forever. The second entry is **H29 on
  `b56-roster-turn`**: that capture RECORDS the defect AC-205 fixes (the turn persisted
  the previous turn's picker under a roster it had just replaced), so it cannot be green
  and correct at once. Six further captures are registered STALE rather than divergent -
  they predate the RS-9 Fix 6 `tier_menu` block, which is a `>`-only hunk in the body the
  export ships, so nothing about the port disagrees with what ships.
- AC-203 `[BE][T]` Given `SessionVars` (Pydantic, `extra = "forbid"`), when compile-state
  produces a key not on the allowlist, then it raises before any write; the allowlist is every
  key `compile-current-state` writes today (R2: nothing dropped) plus `pending` (H15, H22). (A3)
- AC-204 `[T]` Given the `dym_offer` lifecycle fixtures, when replayed, then the eight rules
  (replace / null / domain switch / escalation committed / pick applied / answered / ttl / decay)
  fire in that order, first match wins. (A3)
- AC-205 `[T]` Given a roster born this turn AND a carried picker, when compile-state runs, then
  the born roster wins (H29). (A3)
- AC-206 `[BE]` Given the tail wrote session vars, when the write happens, then it is one
  `overwrite_for_contact` call with `FOR UPDATE`, and an `integration_log` row is written with
  `business_table = respond_contacts.session_vars` as today. (D2)
- AC-207 `[N8N]` Given `sub-output`, when S2 is promoted, then its body from `item-restore` to
  `crossdomain-compose` and the `save-session-vars` PUT are replaced by one `httpRequest` to
  `/complete`; `sub-sendmsg` and `send-attachments` read `response.reply`. n8n no longer holds a
  session-vars writer anywhere on the turn path (grep of every exported workflow). (D2)
- AC-208 `[E2E]` Given a multi-turn clone conversation (picker, digit reply, escalation offer,
  decline), when run on the S2 build, then each turn's persisted `session_vars` equals the
  pre-S2 run's except the R2 / R3 deltas. (A3, A4)

### S2b - Turn trace in Chat History (journey D1 to D4)

Phase 1 = FE against a mock (this is the one FE surface of the program); Phase 2 = the read
endpoint over `chatbot.turns.trace`. Lands after S2 so the head and tail both write stages.

- AC-251 `[FE]` Given the Chat History thread drawer, when an incoming message has a turn,
  then a **Turn** line renders under it: status word (Answered / Escalated / Asked to clarify /
  Failed at <stage>), lane in words, total time, attempt count when > 1; failed turns use the
  destructive tone. (D1)
- AC-252 `[FE]` Given the Turn line, when expanded, then a vertical stage timeline renders:
  Received, Understood, Access, Routed, Looked up, Replied, Remembered, Sent; each row has a
  status icon, `summary` and `why` sentences, and duration; a stage that did not run for that
  lane is omitted, not greyed. (D2)
- AC-253 `[FE]` Given a failed stage, when rendered, then the row shows the reason sentence, a
  Retry button (enabled when the turn is `failed`; the only retry path, R4), and a "Technical
  details" collapsible using the existing `SearchableCode` viewer over `raw`. (D3)
- AC-254 `[FE]` Given the Remembered stage, when expanded, then it lists Kept / New / Cleared
  memory keys in words (labels, not key names, with the raw key in a tooltip). (D4)
- AC-255 `[FE]` Given the Chat History list, when the filter "Failed turns only" is on, then only
  contacts with a `failed` turn in the range are listed, and the row shows the last failed stage.
  (D1)
- AC-256 `[FE]` Usable and non-clipped at 375px and 1280px; the timeline stacks, the drawer
  scrolls, no horizontal page scroll. (D2)
- AC-257 `[BE]` Given `GET /api/v1/system/chatbot/turns?contact_respond_id=&from=&to=&status=`,
  when called with `system.chat_history.view`, then it returns the turn rows with `trace`,
  paged, newest first; `POST /api/v1/system/chatbot/turns/{id}/retry` requeues a `failed` turn
  (403 without `system.chat_history.manage`, 409 unless `failed`). (D1, D3)
- AC-258 `[T]` vitest for the timeline (happy, failed, delegated, retry disabled) and the
  Kept/New/Cleared derivation; pytest for the list filters and the retry guards. (D1 to D4)
- AC-259 `[E2E]` agent-browser: from `/`, System > Chat History, open a thread, expand a turn,
  read the Understood row, open Technical details; screenshot at 375 and 1280. (D1 to D3)

### S3 - Canned lanes, ideation, offer-hold inside the head (journey A2, B2, D6)

- AC-301 `[BE]` Given `branch_kind` in `{access_denied, escalate_offer, escalation_declined,
  clarify_menu, not_supported, demand_qty, offer_hold, ideate}`, when `/chat/turn` runs, then it
  completes the turn itself and responds `delegate = null` with `reply` and `actions`; n8n sends
  and does nothing else. (A2)
- AC-302 `[BE]` Given the canned copy, when rendered, then each string comes from a prompt
  registry key (`chatbot_reply_access_denied`, `chatbot_reply_clarify_menu`,
  `chatbot_reply_not_supported`, `chatbot_reply_demand_qty`, `chatbot_reply_escalate_offer`,
  `chatbot_reply_escalation_declined`, `chatbot_reply_offer_hold`) whose fallback is today's text
  verbatim, with `{{team}}`, `{{user_goal}}`, `{{companies}}` variables. (B1, B2)

  **Landed early, at S2, because the catalog IS the tail** (5 Sep 2026), with the key
  list amended against what `escalate-catalog.js` actually holds:

  - **Eight keys ship**, not seven. `escalate_offer` and `out_of_scope` each have a
    with-team AND a no-team SENTENCE in the JS ("escalate to X team?" vs "escalate this
    to our team?"), so each ships as a pair (`*_no_team`); substituting an empty
    `{{team}}` would send "escalate to  team?" to a customer. `chatbot_reply_out_of_scope`
    is added because the catalog has that arm and this list did not name it.
  - **Two of the seven named keys are NOT registered here.** `access_denied` has no
    `escalate-catalog` case at all (it falls through the switch to an empty response, and
    the port reproduces that), and `offer_hold`'s text is COMPUTED upstream by
    `offer-hold-reply` rather than canned. Registering copy for either would be inventing
    behaviour, so they land with their lanes at S3 and S5.
  - `{{companies}}` is not used by any catalog template: the multi-company sentence is
    built by `build-cs-member-offer` from the roster plan, not interpolated into canned
    copy. Only `{{team}}` and `{{user_goal}}` are declared.
  - Migration `473_chatbot_reply_copy` seeds them; the engine falls back to the same
    strings when a row is missing or the DB is unreachable, so the bot answers either way.
- AC-303 `[BE][T]` Given `domain_hint == 'ideate'`, when the head runs, then the engine calls
  MCP tool `crm_ideation_turn` (via `MCPRuntimeClient`) with the same arguments
  `ideate-turn-http` sends today (including `media_selection` derivation from
  `reference_positions` / `select_all_expanded`), and the reply equals `build-ideate-reply`'s
  output for every ideation fixture; the tool's returned `session_vars.ideation` is folded into
  the turn's `SessionVars` by the tail. (D6)
- AC-307 `[BE][T]` Given `sorento_crm_mcp/catalog.py`, when `sync_catalog` runs, then
  `mcp_tools` has an active `crm_ideation_turn` row (`http_method = POST`, `http_path =
  /api/v1/external/ideation/turn`, `external = True`); a pytest asserts the catalog entry and
  the sync, and the MCP server's tests cover the tool's argument schema. (D6)
- AC-304 `[BE]` Given `not_supported`, when the domain list is consulted, then it is
  `system_settings.chatbot_unsupported_domains` (JSON array, default
  `["goods_receive", "spo_allocation"]`), exposed in BOTH settings GET dict builders and the
  `SystemSettingUpdate` schema. (B2)
- AC-306 `[BE][T]` Given `system_settings.chatbot_stock_denial_enabled` (boolean, default
  false, both dict builders), when false, then `isStockCheckDenied` is never evaluated and no
  turn routes to `stock_denied` / `demand_qty`; when true, then a contact without
  `is_allowed_stock` asking `check_stock` with entities routes to `stock_denied` (R1). (A2)
- AC-305 `[N8N]` Given the spine, when S3 is promoted, then the `route` Switch outputs for the
  eight branch kinds above are removed and a single `if delegate == null` node after the head
  call goes straight to `sub-sendmsg`; the `ideate-turn-http`, `build-ideate-reply`,
  `offer-hold-reply`, `tag-*` and `Edit Fields2` nodes are deleted. (A2)

### S4 - low_signal lane (journey A2)

- AC-401 `[BE]` Given `branch_kind == low_signal`, when the head runs, then the engine resolves
  entities for the prompt (the service behind `POST /system/references/resolve`, `match_mode =
  or`, `fallback_to_all_types = true`), builds the user prompt with the same six fields
  `construct-user-prompt` builds (session vars blanked for `casual` / `unknown`), calls the LLM
  with prompt key `chatbot_clarifier` (fallback = the inline n8n system prompt verbatim), parses
  `{response}` through `central-exchange`'s fence-stripping rule, and completes the turn. (A2)
- AC-402 `[T]` Given every `construct-user-prompt` and `central-exchange` fixture, when
  replayed, then output equals `expected`. (A2)
- AC-403 `[BE][T]` Given the LLM call fails, when the lane runs, then the turn is `failed` at
  `stage = casual_llm` and the reply is today's `sub-error-logger2` text; nothing else is sent
  (`_casual_error` path). (A6)
- AC-404 `[N8N]` `Call 'sub-casual-llm'`, `casual-gate`, `Call 'sub-answer'1` removed from the
  spine. (A2)

### S5 - Escalation lane (journey A4)

- AC-501 `[BE]` Given `branch_kind == out_of_scope`, when the head runs, then the engine runs
  `escalation-input`, `fresh-entity-gate` (resolve + gate in-process when a fresh entity is
  present), `escalation-context` (the six-rank precedence ladder, never a hard team default,
  H27), `clarify-team-gate`, `clarify-company-gate`, and either completes with the clarify ask
  (`pending.kind = team_clarify | company_clarify`) or produces the assignment. (A4)
- AC-502 `[BE]` Given the assignment path, when it runs, then the engine calls the next-assignee
  service and SLA-tracking create in-process and returns `actions = [send_message(routed-to-PIC
  1), assign_conversation, add_comment, send_message(routed-to-PIC 2)]` in that order, plus the
  out-of-scope state text with `includeResponse = false` (state only). (A4)
- AC-503 `[BE][T]` Given a test envelope (`mode != live` or `test_run_id` present), when the
  assignment path runs, then the next-assignee call is NEVER reached (D14 dry-run evaluated
  before any side-effecting service), and the would-send actions are returned with
  `dry_run = true` (H37). (A4)
- AC-504 `[T]` Given every `escalation-context`, `clarify-team-reply`, `clarify-company-reply`
  fixture, when replayed, then output equals `expected`. (A4)
- AC-505 `[BE][T]` Given the multi-company unpicked case, when the clarify ask is produced, then
  it is ALWAYS in the reply (the H2 race cannot exist: one synchronous function). (A4)
- AC-506 `[N8N]` `escalation`, `escalation-arm`, `clarify-company-reply`, `tag-out-of-scope`
  removed from the spine; `sub-escalation` and `sub-human-intervention` unpublished; the n8n
  outbound executes `assign_conversation` / `add_comment` via the existing respond.io nodes. (A4)
- AC-507 `[E2E]` Given the clone with `is_test`, when an escalation turn runs, then
  `test:egress:{run}` records the four would-send actions in order and no real assignment
  happens. (A4)

### S6 - Business lane (journey A2, A3)

Sub-sliced: S6a resolve + gate, S6b fetch, S6c answer + miss. S6a and S6b may ship before S6c
only with the tail still accepting `delegate` fragments (they do: the `/complete` contract is
the seam).

- AC-601 `[BE]` (S6a) Given `entry in {resolve, access_check}`, when the lane runs, then
  `get-access-types` (contact access types service), `resolve-entity` (references resolve
  service, with `entity_pins` and the 400 `ENTITY_PIN_MISMATCH` behaviour, H38), `tier-gate`,
  `disallowed-entity-gate`, `build-ctx-resolved`, the incoming / customer pickers and the four
  `resolve-exit-*` arms run in-process and produce `_exit_kind` with the same payload. (A2)
- AC-602 `[T]` (S6a) Given every `disallowed-entity-gate`, `tier-gate`, `annotate-*-picker`,
  `resolve-exit-*` fixture, when replayed, then output equals `expected`; the `_isTimeline`
  contains-sentinel semantic is reproduced exactly (H46). (A2)
- AC-603 `[BE]` (S6a) Given `resolved.by_entity_type`, when rendered to the customer, then only
  entity-type keys are iterated; a contract test adds a metadata key and asserts it never reaches
  the reply (H16). (A2)
- AC-604 `[BE]` (S6b) Given `_exit_kind == continue`, when fetch runs, then tool selection uses
  `EmbeddingReadService` tool search in-process (no direct pgvector SQL from outside the service
  layer, H53), `tool-filter` picks max similarity with name tiebreak, and zero tools yields a
  distinguishable `not_found` outcome instead of an empty turn (H11). (A2)
- AC-605 `[BE]` (S6b) Given the chosen tool, when the read runs, then `entity-ids-transformer`
  builds the arguments, `MCPRuntimeClient` calls the MCP server at the CONFIGURED URL (never a
  raw IP, H52), and `output-structurer` renders the deterministic answer text. (A2, D10)
- AC-606 `[T]` (S6b) Given every `entity-ids-transformer`, `output-structurer`, `tool-filter`,
  `fetch-result`, `tier-probe-*` fixture, when replayed, then output equals `expected`. (A2)
- AC-607 `[BE]` (S6c) Given a fetched result, when answer runs, then `validator`, `promo-picker`,
  `crossdomain-zeroset`, `crossdomain-probe` (second MCP call), `crossdomain-render`,
  `build-result`, and either `sub-answer` (central-exchange, miss roster, partial did-you-mean
  with its probe) or the miss lane (`not-found-error-message`, `dym-transform`, the three
  probes, `family-fetch` via the products service in-process, `build-suggest-offer`) run and
  hand the `sub-output` fragments to the tail in-process. (A2, A3)
- AC-608 `[T]` (S6c) Given every fixture for the nodes in AC-607, when replayed, then output
  equals `expected`. (A2, A3)
- AC-609 `[BE][T]` (S6c) Given the answer already contains a candidate row, when did-you-mean is
  computed, then that row is not offered again (H45, one outcome-level predicate). (A3)
- AC-610 `[N8N]` `Call 'sub-main-processing'`, `tag-entry-*`, `Edit Fields2` removed; the
  sub-workflows `sub-main-processing`, `sub-resolve-and-gate`, `sub-fetch-results`,
  `sub-get-rag`, `sub-get-results`, `sub-answer`, `sub-miss-suggest` unpublished. (A2)
- AC-611 `[E2E]` The full clone smoke set plus the `tests/cases/*.json` canaries run green on the
  S6c build with reply text equal to the pre-S1 baseline, divergences listed. (A2, A3)

### S7 - Thin spine + CRM per-contact ordering (journey A5, A6, D1)

Owner's target (round 4): 50 dealers sending 2 questions each at the same moment. The n8n
dispatcher serves one contact per second, so it is retired at S7 and the CRM orders turns per
contact inside the synchronous request. Different contacts run in parallel.

- AC-701 `[BE]` Given `POST /chat/turn` after S6c, when called, then it runs the whole turn
  in-process and returns `{turn_id, reply, actions, delegate: null}`; p95 under the
  `chat_latency_p99_target_seconds` setting on the pilot contact. (A5, D4)
- AC-702 `[BE][T]` Given an envelope with `is_test = true` or a `test_run_id`, when any stage
  runs, then no row outside `chatbot.turns` is written (session vars, SLA, round-robin cursor,
  chat history all untouched, asserted by row counts), the response carries `session_patch`
  and every action has `dry_run: true`. (D14)
- AC-703 `[BE][T]` Given the optional worker offload flag `CHATBOT_TURN_ON_WORKER = true`,
  when set, then the request enqueues `run_turn_job` on queue `chat` and waits up to
  `CHATBOT_TURN_WAIT_SECONDS` (default 60) for the result, returning the same body; when
  unset (default), the turn runs in the request. `chat` is in `DEFAULT_QUEUES` and pinned by
  `tests/test_worker_queue_defaults.py`; the server compose `WORKER_QUEUES` change is called
  out in the PR for the owner. (D4)
- AC-704 `[BE][T]` Given an exception at any stage, when the turn runs, then the row is
  `failed` with `stage` and `error`, an `integration_log` row is written, the response still
  carries the error reply as a `send_message` action, and NO automatic retry happens (R4). (A6)
- AC-705 `[BE]` Given a `failed` turn, when Retry is pressed on the trace screen (AC-257), then
  the CRM re-posts the original envelope to the n8n ingress webhook with `attempt + 1`, so the
  normal path (ordering, engine, caller sends) runs; the CRM never sends itself. (D3, R4)
- AC-706 `[N8N]` Given the n8n side, when S7 is promoted, then the ingress is webhook >
  `sub-media-intake` > `POST /chat/turn` > a Switch on `action.kind` feeding the existing
  `sub-sendmsg` / `send-attachments` / assign / comment / update-contact nodes; the
  `sorento-dispatcher`, the redis `q:*` / `ready-contacts` / `lock:*` keys and the old monolith
  `9qVyfUxmRQqrpGRMDLRuz` are retired; `N8N_CONCURRENCY_PRODUCTION_LIMIT` (or worker count) is
  raised so 100 concurrent executions are not throttled. The test clone `Hnd4S8SVH6pftjxs`
  calls the same endpoint with `is_test: true` and its `test-guard` records the actions to
  `test:egress:{run}`. (A5, D1, D14)
- AC-709 `[BE][T]` Given two requests for one contact arriving 50 ms apart, when both call
  `/chat/turn`, then the second runs only after the first finished, in arrival order (redis
  ticket `chatbot:seq:{contact}` + `chatbot:done:{contact}`), and two requests for two
  different contacts run concurrently (measured overlap in the test). (A5, H30)
- AC-710 `[BE][T]` Given a predecessor request that died without advancing the done counter,
  when the next waiter sees no `chatbot:running:{contact}` key for more than 2 s, then it
  repairs the counter and proceeds; given the wait exceeds `CHATBOT_QUEUE_WAIT_SECONDS`, then
  the turn is `failed` at `stage = queued` with today's error reply. (A6)
- AC-712 `[BE][T]` Given the same respond `message_id` for one contact posted twice (webhook
  and poller, or a watermark re-list), when the second arrives, then no second turn runs, the
  response is 200 `{duplicate: true, turn_id: <original>, reply, actions}` and the n8n Switch
  on `duplicate` sends nothing; a third post with a different `message_id` runs normally. (A5,
  D15)
- AC-713 `[BE][T]` Given a poller batch of 5 buffered messages for one contact posted in
  respond timestamp order while a live webhook message for the same contact arrives mid-batch,
  when all six run, then replies are in ticket (arrival) order and no two turns for that
  contact overlap; the trace rows carry `ingress = poller` / `webhook`. (A5, D15)
- AC-714 `[N8N][E2E]` Given the webhook-to-polling switchover (carve state in
  `failover_watermark`, gate `in-failover?` in the producer, poller `CYNq34WZx83POLQ5` >
  `sorento-main-INJECT`), when S7 is promoted, then BOTH injectors call the thin spine (the
  concurrency plan's own lesson: flip both or one strands messages), and on the clone: (a) a
  contact carved to polling gets its reply through poller > INJECT > `/chat/turn` > send;
  (b) un-carving it moves the same contact back to the webhook path; (c) a message that
  arrives via both during the switch runs once (AC-712). Recorded as an agent-driven clone run
  in the n8n repo. (A5, D15)
- AC-711 `[E2E]` Given `scripts/chatbot_load.py` against the S7 backend with 50 contacts x 2
  messages fired at once (dry run), when it completes, then p95 turn time is under 12 s, zero
  errors, DB pool usage below 60%, and every contact's two replies are in order; repeated at
  300 turns. (A5)
- AC-707 `[E2E]` Given live traffic for one pilot contact routed through S7, when they send
  three messages quickly, then the three replies arrive in order and `chatbot.turns` shows
  three `done` rows with `finished_at` ascending. (A5)
- AC-708 `[E2E]` Given the chat console (`scope: chat-ui`) drives a turn on the clone, when
  the turn completes, then `test:egress` holds the would-send actions and no WhatsApp message
  reaches any contact, and `respond_contacts.session_vars` for that contact is unchanged. (D14)

### S8 - Retire and harden (journey C1)

- AC-801 `[BE][T]` The legacy regex readers for the two frozen prefixes (R3) are removed; a
  session with only the legacy string is treated as no pending offer, and the fixture divergence
  entries are retired. (A4)
- AC-802 `[N8N]` Disabled nodes left behind by S1 to S6 are deleted; `export-workflows.py` is
  re-run and the n8n repo's `TOPOLOGY.md` for the two remaining workflows shows zero by-name reads
  into deleted nodes. (C1)
- AC-803 `[BE]` The plan's hazard table has every row marked `fixed (AC-x)`, `reproduced (AC-x)`,
  or `backlog (#issue)`. (C1)
