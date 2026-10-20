# Behaviour card: CHAT-INDEX-VIZ (Chatbot Console "Index match" view)

Status: ask (owner approval of this card + the mock before any build).
Code read: explore build `crew/eval-bench-explore1020` at c899b3ec5d (index mode is not on main yet).
Mock: `documentation/plans/chatbot/chat-index-viz-20oct-mock.html`.

## What the owner sees

The console has no trace view of its own: each bot bubble's "trace" link
(`chatbot-console/components/ChatbotConsole.tsx:120-142`) opens Chat History
`?turn=<id>`, where `chat-history/components/TurnDetailDrawer.tsx` renders the turn as collapsible
sections (Order, Stages, Parse, Apply, ...). The drawer gets one more section, **Index match**,
placed right after Parse, shown only when the turn ran with `chatbot_closed_lists_mode = index`. It reads top to bottom as six steps; each
matched word gets one colour (and a number), and that colour runs through every step it reached.
Tap a chip or row to light up its thread and dim the rest:

1. **Message words.** The customer's own line (`UserTurn.own_text`; the quoted reply is greyed and
   marked "not read"), split the way the index splits it (`candidates._tokens` / `_phrase`, runs of
   up to 3 words, `candidates.MAX_PHRASE_WORDS`). A word that matched something is a chip with a
   colour; a word that matched nothing is plain grey.
2. **Index entries matched.** For each matched word: the DB entry it hit and HOW it hit:
   - source table + row: `product_spec_registry` key (e.g. `finish`), `attachment_types` code,
     certificate kind, `certificates.scheme`, `lookup_option_keywords` alias (set
     `attachment_type_alias`), a derivation rule's code suffix (`-FRG`), or a product code;
   - matched via: value / label / synonym / code / name / alias keyword / code suffix;
   - exact or near spelling (with the trigram score against the 0.55 phrase threshold,
     `candidates.NEAR_PHRASE`).
3. **Lines sent to the parser.** The exact CLOSED LISTS lines of the user block, in order, under
   their two headings ("Candidates for words of this message ..." and "On record for the held
   products ..."). Hovering / tapping a line highlights the word(s) and the entry that produced it
   (the shared colour). Held-product lines have no word: they hang off the held product row (cyan) instead.
4. **Parser returned.** The parser's entities (`raw`, `hint`, `canonical_code` / spec key=value),
   each linked back to the line it used, or marked "not from the index" when no line carried it.
5. **Grounding kept / dropped.** Each entity's grounding outcome (kept, rewritten,
   dropped + the reason string grounding already writes, e.g. "dropped: a finish short form, no
   warehouse on file").
6. **Tool call.** The tool the turn called, each argument coloured by the word it came from.

A collapsed footer shows the counts ("3 words matched, 5 lines sent, 2 used by the parser,
1 dropped by grounding") and the system-prompt pointer lines (`SYSTEM_BLANKS`), so the owner can
see that the full lists were NOT in the system prompt this turn.

Block-mode turns show one line instead: "Closed lists sent in full (block mode); no per-turn index."

## Example turns (masked; product codes and contact are synthetic, the mechanics are real)

These are the cases the 20-21 Oct index-mode rounds were built around
(`PLAN-closed-lists-index-warehouse-20oct.md` on the explore branch). I have no access to the
owner's console DB from this sandbox, so the rows below are rebuilt from the code paths, not
copied from the console; the build will render whatever the turn trace holds.

| # | Message | Index match (word -> entry) | Lines to parser | Parser | Grounding | Tool |
|---|---------|-----------------------------|-----------------|--------|-----------|------|
| 1 | "stock SRTKT7xSS frg" | `frg` -> derivation rule code suffix `-FRG` on registry key `finish` -> value `french_gold` (exact); `SRTKT7xSS` -> product code (candidates) | `- "frg": spec finish = french_gold (French Gold)` + the code line | product + spec finish=french_gold (or a warehouse hint "frg") | spec kept; a warehouse hint "frg" dropped: "a finish short form, no warehouse on file" (grounding.py:979-987) | stock lookup for the code filtered to French Gold |
| 2 | "any stock at IB" | no index line (warehouses are NOT indexed: round 2c, option B) | none for `IB` | warehouse hint "IB" | kept: resolves to BRW-IB and MWH-IB (`resolve_warehouse_token`) | stock lookup at both warehouses |
| 3 | "send the CE cert and drawing" (held product) | `ce` -> `certificates.scheme` CE (exact); `cert` -> certificate kind via a `lookup_option_keywords` alias (exact); `drawing` -> `attachment_types` (name, exact); held product -> its own file types, schemes and spec values | `File type ...`, `Certificate kind ...`, `Certificate scheme CE ...` under candidates; held lines under "On record ..." (collapsed) | attachment + scheme entities | "on the attachment_type list: <code>", "on the cert_scheme list: CE" | file send for the held product |
| 4 | "phtos for ZZBS40 pls" (quoting an earlier bot reply) | `phtos` -> `attachment_types` photos, NEAR spelling 0.61 (>= 0.55); `ZZBS40` -> product code; the quoted reply's words are not read | the photos file-type line + the code line | attachment zz_photos + product | kept on the list | file send |
| 5 | "stock ZZKT71SS" in block mode | none: the full lists were in the system prompt | n/a | n/a | n/a | the section shows a one-line notice |

## Edge cases the view must handle

- **Block mode turn**: one line, no panel body (see above).
- **Index failed** (`_candidate_lines` caught an exception, engine.py:1166-1171): the panel says
  "Index lines failed to build; the parser ran without them" and shows the candidate lines only.
- **No word matched and nothing held**: the panel shows the words all grey and "No index lines this
  turn"; the parser input carries no CLOSED LISTS block.
- **Caps hit**: held products > 5, keys > 20, values per key > 5, file lines > 12
  (`closed_lists_index.CAP_*`): show "+N not sent (cap)" under the column.
- **Contact-hidden spec keys**: a hidden key's line was never sent; the view must not reveal its
  value either (show "1 hidden key not indexed", no key name).
- **Quoted reply**: words of the quoted message are not indexed; shown greyed.
- **Near spelling**: a near match (e.g. "phtos" -> photos 0.61) adds a line but never binds by
  itself; the chip is outlined, not filled, with the score.
- **Old turns** recorded before the new trace event: the panel falls back to parsing the
  `prompt_text` event (lines only, no provenance) and says "match details not recorded for this
  turn".
- **"wh" collision** (IW-10): `wh` is both the finish suffix `-WH` (an index line) and a warehouse
  suffix (grounding only): the view shows the finish line AND the grounding note for the warehouse
  hint, so the owner sees why a resolvable warehouse wins.
- **375px**: the section is one column at every width (the drawer is 672px max); every row carries
  the word's number badge, so the link survives where colours are hard to tell apart.

## What the trace already records (no change)

- `prompt_text` event: the full parser user block, so the exact injected lines (engine.py:4904).
- `understood` stage: `raw.parser_raw` (what the parser returned) and `raw.derived` (engine.py:4863-4902).
- `grounding` event: `changes` = grounding notes `{from, raw, to}` (engine.py:5194). It is in the
  raw `chatbot.turns.trace` array but `compose_trace_detail` (`services/chatbot/trace_detail.py:415`)
  maps no grounding key and the FE never shows it, so the build adds a `grounding` key there too.
  `to` is a free string or a list of `Grounded` dicts (grounding.py:834-1012); the view classifies
  it: starts with "dropped" / "canonical dropped" / "canonical refused" -> dropped, "on the ... list"
  -> kept, a list or other text -> rewritten.
- `context` event, `held_family`, `scheme_index`, and the tool stages that follow.

## New trace fields needed (one new event, written only in index mode)

`turn_trace.add("closed_lists_index", {...})` from `engine._candidate_lines`, with:

- `mode`: `index`.
- `words`: the folded grams the index matched over (`closed_lists_index._grams`).
- `matches`: one entry per line sent, `{line, heading: "candidates" | "held", word | null,
  source: "spec_registry" | "code_suffix" | "attachment_type" | "cert_kind" | "cert_scheme" |
  "alias_keyword" | "product_code" | "held_spec" | "held_file", ref: {table, key, value}, via:
  "value" | "label" | "synonym" | "code" | "name" | "alias" | "suffix", exact: bool, score: float | null}`.
- `capped`: per cap, how many were left out.
- `hidden_count`: number of hidden keys skipped (count only).
- `failed`: true when the index savepoint failed.

Today `block()` returns only strings; `_named()` returns only a bool and `code_suffix_lines()`
drops which rule matched, so provenance has to be returned alongside the lines (a parallel list,
same order). The candidate-lines half needs the same from `WordCandidates` (`gram`, `items`,
`pairs`, `scores` already exist; the phrase kind - value / label / synonym - is lost in
`_vocabulary` and must be kept on `_Value`). No migration: the trace is stored as JSON records.

## Questions (each with a recommendation)

1. **Where does it live?** (a) a new collapsible "Index match" section in Chat History's
   `TurnDetailDrawer`, right after Parse (the console's "trace" link already opens it), (b) inline in
   the console bubble. Recommendation: **(a)**, because the drawer is where every other trace
   section lives and the bubble is 85% of a phone width.
2. **Record provenance, or rebuild it at view time?** (a) record the new `closed_lists_index` event
   per turn, (b) re-run the matcher when the panel opens. Recommendation: **(a)**, because the
   vocabulary changes (a synonym added later would show a match that did not happen on that turn).
3. **Show the candidate-line (product code) matches too, or only the closed lists?** (a) both,
   (b) closed lists only. Recommendation: **(a)**, because the parser reads them as one block and
   case 1 shows both on one word row.
4. **Show held-product lines expanded or collapsed?** Up to 20 keys x 5 values. Recommendation:
   **collapsed with a count**, expanded on tap, because they are not words of the message.
5. **Also for block-mode turns?** (a) one-line notice, (b) the same panel over the full lists.
   Recommendation: **(a)**, because block mode has no per-turn index to show; the parser saw everything.
