# CHAT-INDEX-VIZ browser pass (Phase 3)

Branch `claude/chat-index-viz-3ladv2`, 21 Oct 2026. Cloud sandbox, empty bootstrapped CI schema, local backend
(:8000) and `npm run dev` frontend (:3000). Driven with agent-browser 0.27.0 headless, using the sandbox Chromium
(`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`, via `AGENT_BROWSER_EXECUTABLE_PATH`; agent-browser has no
Chrome of its own here). One session named `viz`, closed at the end.

Seed (ZZ-prefixed, synthetic, scripts not committed): Super Admin user, `chatbot_closed_lists_mode = 'index'`, all
modules enabled for the default tenant (an empty schema has none, which hides the whole sidebar), `chatbot_semantic_parser`
v1004 with the production label (template = PRICE TERMINOLOGY, ACCESS LEVELS, ATTACHMENT TYPE EXTRACTION and the
`closed_lists_prompt.SECTION`), and one `chatbot.turns` row whose trace holds an `understood` stage, a `grounding`
event, a `prompt_text` event and a `closed_lists_index` event (words stock / zzkt71ss / frg).

Navigation: sidebar clicks from `/` for the prompts page (System > AI Assistant > Prompts > chatbot_semantic_parser)
and for reaching Chat History. **One deep URL was needed:** the Chat History list is the WhatsApp message table and a
turn row never appears in it, so the drawer was opened with `/system-management/chat-history?turn=<id>` (the page's
documented entry used by the Chatbot Console trace link).

## Result table

| Check | 1280x900 | 375x812 |
|---|---|---|
| A. Chat History drawer, Index match | PASS | PASS |
| B. Prompts, Architecture tab | PASS | PARTIAL (defect D1) |
| C. Console errors | PASS (none) | PASS (none) |
| C. Horizontal page scroll | PASS | PASS |

Horizontal scroll (`documentElement.scrollWidth` vs `innerWidth`): A 1280/1280, A 375/375, B 1280/1265 (vertical
scrollbar width, no overflow), B 375/360. No page-level horizontal scroll anywhere.

Console: no `[error]` entries and `errors` empty on both pages at both widths. Only warning seen:
`Warning: Missing Description or aria-describedby={undefined} for {DialogContent}` (Radix, from the drawer shell; not
introduced by this lane's components as far as seen, noted for completeness).

## A. Chat History turn drawer (screenshots `A-1280.png`, `A-375.png`, `A-375-frg.png`)

Network: `GET /api/v1/system/chatbot/turns/<id>` fired and returned the section.

On-screen text of the "Index match" section (innerText):

```
stock  zzkt71ss  frg
Word | Matched list entry | What the parser got | What it understood | Kept or dropped
zzkt71ss | Products: code ZZKT71SS (ZZ Basin Mixer) | - "zzkt71ss": code ZZKT71SS (ZZ Basin Mixer) | "zzkt71ss" as a product: ZZKT71SS | Kept
frg | Specifications: spec finish = french_gold (French Gold) | - "frg": spec finish = french_gold (French Gold) | "frg" as a specification: finish = french_gold / "frg" as a warehouse | Kept / Dropped: a finish code ending, not on the warehouse list
```

- Chips: zzkt71ss and frg filled (blue), stock plain outlined. PASS.
- Five headers exactly as specified, in order. PASS (at 1280 as a column header row; at 375 each row is a stacked
  card repeating the five labels).
- frg row: "Dropped: a finish code ending, not on the warehouse list" in a red (destructive) badge, next to a green
  "Kept". PASS.
- Forbidden words (grounding, hidden_keys, index mode, closed_lists, SYSTEM_BLANKS) not present in the section text.
  Elements with `scrollWidth > clientWidth`: 0 at both widths (nothing clipped).
- 375: rows are cards, the drawer fits the viewport.
- Cosmetic note (not a defect): the Dropped badge wraps onto 2-4 lines inside a pill with rounded ends (1280:
  4 lines in a narrow column; 375: 2 lines). Readable and unclipped.

## B. Prompts, `chatbot_semantic_parser` Architecture tab (screenshots `B-1280.png`, `B-375-top.png`, `B-375-tables.png`)

Network: `GET /api/v1/system/ai-assistant/prompts/chatbot_semantic_parser/versions/1004/architecture` returned 200.

On-screen text:

```
v1004 sends about 891 tokens to the parser on every message.
[badge] Only the matching entries are sent
Customer's message -> Matched list entries (Specifications, File types, Certification types) -> What the parser got -> What it understood -> Kept or dropped (Checked against the same lists and the warehouse list)
Lists
List | Comes from | Entries | Sent each message | Full list
Specifications | Product Specifications | 0 | 36 | 0
File types | Attachment Types | 0 | 30 | 0
Certification types | Certificates | 0 | 36 | 0
Warehouses | Warehouses | 0 | 0 | -
Sections
Section | Kind | Tokens
Opening | Filled from data | 15
PRICE TERMINOLOGY | Text | 13
ACCESS LEVELS | Filled from data | 6
ATTACHMENT TYPE EXTRACTION | Text | 17
CLOSED LISTS | Closed lists | 840
```

- 1280: summary line, badge, five boxes left to right with arrows, Lists table (source names are links), Sections
  table with bars scaled to CLOSED LISTS (840). Warehouses "Full list" is "-". PASS.
- Tab is the third tab ("Architecture") on `chatbot_semantic_parser`. Other prompts: `chatbot_clarifier` and
  `semantic_parser` render no tab bar at all, so no Architecture tab (`B-other-prompt-1280.png`,
  `B-other-prompt-semantic_parser-1280.png`). PASS.
- 375: the five boxes stack vertically with down arrows. PASS.
- Entries 0 and "Full list" 0 for the three lists are an artefact of the empty sandbox DB (no specs, file types or
  certificate rows), not of the view.

### D1 (375px, minor): table columns hidden until the table is scrolled sideways

At 375 both tables sit in their own `overflow-x-auto` box, and the page does not scroll, but the rightmost columns are
off-screen on first view: the Lists table cuts off "Full list" (and partly "Sent each message"), and the Sections table
cuts off the "Tokens" column, i.e. the numbers and the bars, which is the point of that table. CLAUDE.md asks for usable
and non-clipped at 375px. Repro: log in, open Prompts > chatbot_semantic_parser > Architecture at a 375px viewport,
scroll to Sections, see `B-375-tables.png`. Suggested fix (not applied, no app code changes in this pass): at < 640px let
the Section/Kind cells shrink (smaller Kind text or stack Kind under Section) so Tokens stays in view.

## Environment notes

- The sandbox DB is empty: a user, role grants (from migrations), all modules enabled, the prompt version and the turn
  were seeded; `.test` e-mail addresses are rejected by login validation so the seed user uses `example.com`.
- Servers started for this pass were stopped; the agent-browser session `viz` was closed.

---

# Round 2 (after fix round 1, commit 19d66735a)

Same sandbox and seed, backend and `npm run dev` rebooted, logged in again (the new dev server invalidated the old
cookie), agent-browser session `viz`. Two more turns seeded: one whose `closed_lists_index` event has `matches: []`
(words hello, there) and one with no `closed_lists_index` event. Turn drawers opened by `?turn=<id>` as in round 1
(one deep URL per turn, after reaching Chat History via the sidebar); the prompts page by sidebar clicks.

| Check | 1280x900 | 375x812 |
|---|---|---|
| A. Index match, understood line beside its result, badge = word only | PASS | PASS |
| A. Empty matches: "No word of this message matched a list entry." and no header row | PASS | PASS |
| A. No event: "No list matching was recorded on this turn." | PASS | PASS |
| B. Architecture, table at 1280 / stacked label: value blocks at 375, no inner sideways scroll | PASS | PASS |
| B. List names Specifications, File types, Certificates, Warehouses | PASS | PASS |
| C. Console errors | PASS (none) | PASS (none) |
| C. Horizontal page scroll (scrollWidth / innerWidth) | PASS (1280/1280 drawer, 1265/1280 prompts) | PASS (375/375 drawer, 360/375 prompts) |

D1 from round 1 is fixed.

## A (screenshots `A-1280-r2.png`, `A-375-r2.png`, `A-empty-r2.png`, `A-empty-375-r2.png`, `A-none-r2.png`, `A-none-375-r2.png`)

frg row text now (innerText): `"frg" as a specification: finish = french_gold` -> badge `Kept`; `"frg" as a warehouse` -> badge
`Dropped` with muted `a finish code ending, not on the warehouse list` beside it (1280: in the Kept or dropped column on
the same row as its understood line; 375: each understood line is followed by its own "Kept or dropped" label and result,
so a line and its result stay together). zzkt71ss row: `"zzkt71ss" as a product: ZZKT71SS` -> `Kept`.
Headers unchanged. Chips unchanged. Elements wider than their box: none visible (only a `sr-only` ": " separator
between the badge and the reason, which is by design).

Empty-matches turn: chips `hello` `there`, then the single muted line "No word of this message matched a list entry.";
no "Word / Matched list entry / ..." header text anywhere on the page. No-event turn: the section holds only "No list
matching was recorded on this turn.".

## B (screenshots `B-1280-r2.png`, `B-375-lists-r2.png`, `B-375-tables-r2.png`)

1280: still two real tables (Lists, Sections) with the token bars; the flow lists "Specifications, File types,
Certificates" under "Matched list entries"; Lists rows are Specifications, File types, Certificates, Warehouses
(Warehouses full list "-").

375: both tables render as `display: block` stacks; each row is a block of `Label  value` lines (List, Comes from,
Entries, Sent each message, Full list; Section, Kind, Tokens), every column visible, no element inside the card
scrolls sideways. Observation (not a failure): the Sections token bars are not drawn at 375, only the number.

## C

Console: no `[error]` entries, `errors` empty. Page scroll widths as in the table.

Servers stopped and session `viz` closed at the end of the round.
