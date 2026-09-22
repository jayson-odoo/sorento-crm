# Browser verification: chatbot media-into-turn (lane `feat/chatbot-media-into-turn`, DRAFT PR #1139)

Run 23 Sep 2026. agent-browser (`npx -y agent-browser@0.27.0`, session `media-into-turn-pass`),
headless, against the lane's own stack (FE :3000 `next dev`, BE :8000 uvicorn on
`sorento_ai_automation_0921`, worker on redis db 13 queue `media`). Driven through the
Chatbot Console (System > Messaging > Chatbot Console, reached by sidebar clicks) because the
`/external/chat/turn` API key is not available on this DB.

**Console contact used:** "Chua Chin Long" (`respond_io_id 477071885`), chosen because
`contact_media_limit` shows `is_allowed=true` for image and voice for this contact (the console's
default contact, Katherine Loo, has no `contact_media_limit` row at all - see AC-1810 below, that
turned out to be free coverage of the gate-denied path). Chua Chin Long is mapped to company
`00000000-0000-0000-0000-000000000001`, the same company that owns the three test product codes.

**Test image:** the pre-rendered PNG at the scratchpad path given in the brief, containing
"Product List / BRBC22293W-1 / SRTWT1506 / SRTWT1805" - all three confirmed to exist in
`products.product_code` on this DB before testing.

**Worker:** picked up every media job within 5-7s each time; no timeout was hit. Log lines
`INFO:rq.worker:media: app.tasks.media_tasks.process_media_extraction(...)` through
`Job OK` for every submitted photo/voice. No worker restart needed.

## Headline finding: a DEFECT, not an environment gap

**S3's `entities_only` arm (AC-1822-1832) never places a real product code.** Every turn the
parser routes into lane `entities_only` (bare codes/photo, no domain word, no carried focus)
comes back "Couldn't find" for ALL codes, even though the same codes resolve correctly one
call away. See "Defect 1" below - this blocks a clean pass on the whole of UAC Section C and,
by extension, J1's first turn and any bare-code entry point. J2/J3/J4 (a domain word already
present, or already carried) do NOT go through this arm and resolve correctly.

A second, separate, environment-only limitation: this lane's stack does not run the MCP tool
server the ordinary business/fetch lane calls for the actual stock number
(`crm_inventory_stock_balance_list`), so every turn that reaches the real fetch step answers
"I could not fetch stock just now, please try again." This is NOT a lane defect - resolution and
the reply prefix are the parts in scope here, and both are visible working right up to the point
of the tool call. Noted per AC below as SKIP (environment), not FAIL.

## Defect 1 - `entities_only` arm resolves nothing (blocks AC-1822/1823/1824/1825, J1, part of J2)

**Steps (photo, no caption):** Chatbot Console, contact Chua Chin Long, Reset, attach the test
PNG with no caption, no prior focus/domain. **Expected** (AC-1824): "I read A, B and C from that
photo. Couldn't find D. What would you like me to do with it?" - listing only tokens that truly
did not resolve; since all three codes are real, no "Couldn't find" sentence should appear at all.
**Observed:** "I read BRBC22293W-1, SRTWT1506 and SRTWT1805 from that photo. Couldn't find
BRBC22293W-1, SRTWT1506 and SRTWT1805. What would you like me to do with it?" - every code is
named as unfound, including the ones just listed as read. Screenshot
`browser-pass-J1-turn1-photo-only-DEFECT.png`. Turn id `8a40702f-13f9-4718-b9ca-cde2547471a1`.

The trace (`browser-pass-turnpanel-stages.png`, `browser-pass-turnpanel-apply-statediff-DEFECT.png`)
confirms: `lane: entities_only` (routing is correct - AC-1822 itself passes, this is NOT the
`casual` LLM clarifier), parser verdict has all three entities with `hint: "product"`,
`confident: true`, but `canonical_code: null` for every one, and the state diff shows
`focus.products` written with the SAME unresolved raw rows (`canonical_code: null`) rather than
enriched with a `uuid` - i.e. `focus_settles_product` (AC-1823's own trace rule) did not fire.
"Focus" tab: "No focus rule fired this turn."

**Reproduced a second way**, ruling out anything photo-specific: typed "BRBC22293W-1, SRTWT1506,
SRTWT1805" with no domain word, fresh conversation, same contact -> "I have . Couldn't find
BRBC22293W-1, SRTWT1506 and SRTWT1805. What would you like me to know?" (screenshot
`browser-pass-typed-bare-codes-DEFECT.png`) - same failure, plus a second, smaller defect: "I
have ." with a stray space before the period when the placed list is empty (AC-1825's wording
does not cover the placed-list-empty case).

**Isolated to this one arm, not a general resolver regression:** the SAME contact, SAME session,
immediately afterward:
- Typed "check stock" after the failed bare-codes turn correctly CARRIED the three raw codes into
  the fetch (`*stock* for BRBC22293W-1, SRTWT1506, SRTWT1805:`, no "Couldn't find") - domain carry
  itself works, screenshot `browser-pass-J1turn1typed-then-checkstock-carry.png`.
- Typed "check stock for SRTWT1506" (domain word up front) resolved SRTWT1506 immediately, no
  "Couldn't find" (screenshot `browser-pass-domain-first-resolves-ok.png`).
- Two more attempts at the identical bare "photo, no caption" turn had the parser LLM
  independently tag `domain_hint: inventory` on its own (skipping `entities_only` entirely, an
  expected LLM non-determinism on an ambiguous bare-code message) - both times resolution
  succeeded (`*stock* for BRBC22293W-1, SRTWT1506, SRTWT1805:`).
- A standalone script (`business_services.production_services(db, ...).resolve_entity(...)`, the
  exact call `_run_entities_only_arm` makes) against the same three tokens returns `matches: []`
  for all three on a **bare, unscoped session** (company scope `UNSET`), and resolves all three
  correctly the moment `set_company_scope(db, frozenset({"00000000-0000-0000-0000-000000000001"}))`
  is applied first - which is the exact failure mode `engine.py`'s own H56 comment names ("An
  unstamped session reads UNSET ... the turn answers 'Couldn't find: <code>' for a product that
  exists in the contact's own company"). This strongly suggests the `db` session
  `_run_entities_only_arm` calls `resolve_entity` on is not carrying the scope the rest of the
  turn's `db` carries, though I did not chase the exact seam further - that is the coder's
  diagnosis, not mine to fix.

**Net effect on the journeys:**
- **J1 FAIL** (first turn): photo-only reply is "Couldn't find" for all three real codes instead
  of a clean read; the SECOND turn ("check stock") does carry the codes through and answers with
  the right product list, but AC-1824/1827's first-turn wording is wrong.
- **J2 PASS** for routing/prefix (domain was said first, "check stock" needs-scope reply, then
  photo answers directly with the carried domain, prefix "I read BRBC22293W-1, SRTWT1506 and
  SRTWT1805 from that photo." exactly as specified) - never touches `entities_only`, so unaffected
  by Defect 1. Final stock number blocked by the MCP gap (below).
- **J3 PASS** for routing/prefix/resolution (caption "Check stock" + photo, one turn,
  `rendered_text` = "Check stock: BRBC22293W-1, SRTWT1506, SRTWT1805" exactly per AC-1807, prefix
  correct, all three codes resolved) - domain given up front, never touches `entities_only`.
  Final stock number blocked by the MCP gap.
- **J4 PASS** for routing/prefix/resolution/transcript (voice "stock for SRTWT1506" synthesized
  via macOS `say`, Whisper transcript "Stok for SRTW-T1506", reply opens "I heard: Stok for
  SRTW-T1506." then correctly resolves to `*stock* for SRTWT1506:`) - domain word present, never
  touches `entities_only`. Final stock number blocked by the MCP gap.

## Environment limitation - stock fetch needs the MCP tool server

Every turn that reaches an actual fetch (J2/J3/J4, and the carried J1 second turn) answers
"I could not fetch stock just now, please try again." Backend log:
`chatbot: MCP tool crm_inventory_stock_balance_list failed` ->
`httpx.ConnectError: [Errno 61] Connection refused` in `ai_assistant_service.py::_rpc`, i.e. the
business lane's stock fetch is itself an MCP tool call, and this lane's stack (FE/BE/worker only,
per the brief) does not run an MCP server on the port `AI_ASSISTANT`/`ai_assistant_service`
targets. Not a lane defect - noted so the coder/captain don't misread the "please try again" text
as new breakage. Reproduced identically on a plain domain-first stock question with no media
involved at all, so it predates and is unrelated to this PR.

## AC-by-AC (Section A/B/C reachable via console; D/E where possible; F/G/H not attempted here)

| AC | Result | Evidence |
|---|---|---|
| AC-1800/1801 media_intake stage present, modality/decision/status/job id/elapsed_ms | PASS | Stages tab shows `media_intake 6225ms "Read the photo."`; voice turn's Stages tab (not screenshotted individually) showed the equivalent for voice |
| AC-1802 turn_id / contact_media_usage share the turn id | SKIP (would need a DB read tied to a specific job row; not done from the browser) | - |
| AC-1803 no open DB session during the wait; bounded by media_sync_wait_seconds | SKIP (pytest-only assertion) | - |
| AC-1804 document/video/sticker-without-url skip intake | SKIP (not exercised - no such fixture attached) | - |
| AC-1805 no double-intake on the transition-window shape | SKIP (n8n-only shape, cannot construct from console) | - |
| AC-1806 AUDIO_NOT_PATCHED_ERROR gone | PASS (indirect) - voice turn transcribed and answered normally, no such error text anywhere | `browser-pass-J4-voice-audio-bubble.png` |
| AC-1807 caption + image -> `"Check stock: <raws>"` | PASS | J3 trace: `Read from image: Check stock: BRBC22293W-1, SRTWT1506, SRTWT1805` |
| AC-1808 no caption -> rendered_text is the raws, needs_clarification still true in the result | PASS (rendered_text non-null; reply reads "I read ... from that photo." not a bare re-ask) | `browser-pass-J1-turn1-photo-only-DEFECT.png` |
| AC-1809 voice -> parser gets the transcript verbatim | PASS | reply opens "I heard: Stok for SRTW-T1506." then acts on "SRTWT1506" |
| AC-1810 denied_gate -> not_enabled wording, branch_kind media_denied, no parser call | PASS | contact Katherine Loo (no `contact_media_limit` row): "I cannot read photos on this number yet. Type the codes instead and I will look them up straight away." chip `media_denied`. `browser-pass-AC1810-denied-gate.png` |
| AC-1811/1812 denied_quota/denied_duration/denied_burst | SKIP (would need to exhaust the monthly limit or burst window; not attempted, out of scope for one pass) | - |
| AC-1813/1814 failed extraction / timeout wording | SKIP (worker never failed or timed out in this run) | - |
| AC-1815 quota warn notice appended once | SKIP (contact was nowhere near the warn threshold) | - |
| AC-1816 console builds the same envelope as WhatsApp, one path | PASS (by construction/code read - `_run_console_media_turn` calls the same `run_turn`; not independently re-verified beyond what the trace shows) | - |
| AC-1817/1818 reply prefix lists every code, truncation note | PASS for the listing (never a count, every code named); truncation not exercised (only 3 codes, cap is 10) | all screenshots above |
| AC-1819 voice prefix "I heard: ..." capped at 160 chars | PASS (short transcript, cap not exercised) | `browser-pass-J4-voice-audio-bubble.png` |
| AC-1820 prefix appears once, never on a text turn | PASS (typed-only turns like "check stock for SRTWT1506" carry no such prefix) | `browser-pass-domain-first-resolves-ok.png` |
| AC-1821 media_max_entities as the cap | SKIP (not changed/exercised) | - |
| AC-1822 entities_only lane selected, LLM clarifier not called | PASS (trace shows `lane: entities_only`, reply is deterministic, not an LLM "are you asking about..." clarifier) | `browser-pass-turnpanel-apply-statediff-DEFECT.png` |
| AC-1823 placed rows land on focus.products WITH a uuid | **FAIL - Defect 1** | same |
| AC-1824 photo-source reply wording | **FAIL - Defect 1** (format right, content wrong: everything reported unfound) | `browser-pass-J1-turn1-photo-only-DEFECT.png` |
| AC-1825 typed-source reply wording | **FAIL - Defect 1**, plus the "I have ." empty-list wording gap | `browser-pass-typed-bare-codes-DEFECT.png` |
| AC-1826 open_question stays null, domains stays empty | PASS (Apply/Focus tabs show no open_question, no domains) | `browser-pass-turnpanel-apply-statediff-DEFECT.png` |
| AC-1827 J1 | **FAIL** first turn (Defect 1); domain carry into turn two works | `browser-pass-J1turn1typed-then-checkstock-carry.png` |
| AC-1828 J2 | PASS (routing/prefix/resolution); final number blocked by MCP gap | screenshots above |
| AC-1829 J3 | PASS (routing/prefix/resolution, one turn); final number blocked by MCP gap | screenshots above |
| AC-1830 J4 | PASS (routing/prefix/transcript/resolution); final number blocked by MCP gap | `browser-pass-J4-voice-audio-bubble.png` |
| AC-1831/1832 | SKIP (not attempted - would need a promotion focus pre-set) | - |
| AC-1833-1838 stored media / migration | SKIP (DB/pytest-level, not browser-observable) | - |
| AC-1839/1840 `media` block on turn GET/list | SKIP (could not extract the raw JSON from the browser session - the FE's bearer token is not reachable from page JS/HAR body capture in this setup; this needs a pytest/API-level check, not browser) | - |
| AC-1841 signed url is company-scoped | SKIP (same reason) | - |
| AC-1842-1846, 1848 Chat History LIST row media bubble (thumbnail/lightbox/audio/chip/plain-on-denial) | **SKIP - cannot reach.** Chat History's list is populated ONLY by the n8n WhatsApp ingest (`chat_histories` table); a console turn is `is_test=True`/dry-run and writes nothing there. The list page confirmed empty throughout this run ("No messages in this range ... chat history is written by the n8n WhatsApp flow"). Without the `/external/chat/turn` API key (not available on this DB, per the brief) there is no way to create a real `chat_histories` row from this environment. This is an environment gap, not a verdict on the feature; the vitest component tests are the authority for this rendering logic. | `browser-pass-escape-closes-drawer.png` (list state) |
| AC-1847 TurnPanel stage for a media turn, entities/attributes/notes/decision, absent on text turns | PARTIAL PASS - the Stages tab clearly shows a distinct `media_intake` "Read the photo." row (absent on the ordinary text-only turns seen elsewhere in this run), but the entities/attributes/notes/decision are NOT shown inline against that stage in this build - they only surface via the separate "Apply" tab's state diff. Whether that satisfies "with entities, attributes, notes and the decision" is a judgement call for the reviewer/captain; flagging rather than failing outright since the data IS present in the drawer, just under a different tab. | `browser-pass-turnpanel-stages.png` |
| AC-1849 no explanatory copy on screen | PASS (chip/stage text is functional, no feature explainer visible anywhere in this run) | all screenshots |
| AC-1850-1853 (S5 partial-hit) | SKIP (not attempted - needs a specific miss-with-no-fuzzy-neighbour fixture; captain/coder said this AC is pending the owner's own trace per commit 1937d167e) | - |
| AC-1854-1857 (n8n cut-over) | SKIP (owner-run, not testable from here) | - |
| AC-1858/1859 hygiene | SKIP (code-review item, not browser) | - |

## Responsive / interaction checks done

- TurnPanel drawer at 375px: no horizontal clipping, all Stages readable, tabs stack cleanly.
  `browser-pass-turnpanel-375.png`.
- Escape closes the drawer (confirmed: drawer gone, underlying Chat History list visible after
  pressing Escape). `browser-pass-escape-closes-drawer.png`.
- Console UI itself (not in scope of the UAC's own Section E, which targets Chat History) renders
  the incoming photo as a re-typed TEXT reconstruction of the recognised content ("Product List /
  BRBC22293W-1 / SRTWT1506 / SRTWT1805"), not an actual image thumbnail - this looks intentional
  for a synchronous dry-run harness (no persisted attachment/signed url exists yet at the point
  the console renders the bubble) rather than a bug, but flagging since it means the console
  itself is NOT a stand-in for verifying AC-1842's thumbnail rendering either.

## Console/JS/network checks

No uncaught console errors during any turn. `network requests --filter /api/v1/` confirmed
`POST /api/v1/system/chatbot/console/turn` fired for every send/upload, and
`GET /api/v1/system/chatbot/turns/{id}` fired when opening the trace drawer.

## Summary

- **DEFECT (blocking a clean Section C / J1 pass):** `_run_entities_only_arm`'s call to
  `resolve_entity` returns zero matches for real, correctly-scoped product codes every time the
  arm actually runs, while the identical codes resolve fine one call away in the ordinary
  domain-first fetch path in the same turn/session. Reproduced 2/2 times the arm fired (once via
  photo, once via typed text), both with full trace evidence. Needs a coder fix + red test before
  this lane can claim AC-1822-1832/J1 green.
- **Everything else reachable from the console (J2, J3, J4, the reply-prefix rules, the
  `denied_gate` path, routing to `entities_only` itself, domain carry) checks out.**
- **Two things this pass could not reach at all, both environment limits stated up front in the
  brief or discovered here, not defects:** the Chat History LIST's media bubble (needs a real
  `chat_histories` row, which only n8n ingest writes, and the API key for that path is not on
  this DB), and the final stock NUMBER (needs the MCP tool server, not part of this lane's stack).
