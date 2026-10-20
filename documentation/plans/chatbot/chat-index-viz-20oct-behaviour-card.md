# Behaviour card: CHAT-INDEX-VIZ (Chatbot Console "Index match" view)

Status: ask (owner approval of this card + the mock before any build).
Code read: explore build `crew/eval-bench-explore1020` at c899b3ec5d (index mode is not on main yet).
Mock: `documentation/plans/chatbot/chat-index-viz-20oct-mock.html`.

## What the owner sees

In the Chatbot Console, every bot turn's trace gets one more panel, **Index match**, shown only when
the turn ran with `chatbot_closed_lists_mode = index`. It reads left to right (top to bottom on a
phone) as five linked columns, one row per message word:

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
   (the arrows). Held-product lines have no word: they hang off the held product chip instead.
4. **Parser returned.** The parser's entities (`raw`, `hint`, `canonical_code` / spec key=value),
   each linked back to the line it used, or marked "not from the index" when no line carried it.
5. **Grounding kept / dropped -> tool call.** Each entity's grounding outcome (kept, rewritten,
   dropped + the reason string grounding already writes, e.g. "dropped: a finish short form, no
   warehouse on file"), and the tool call the turn made with the arguments that came from those
   entities.

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
| 3 | "send the CE cert and drawing" (held product) | `ce` -> `certificates.scheme` CE (exact); `drawing` -> `attachment_types` (name, exact); held product -> its own file types + schemes | `File type ...`, `Certificate scheme CE ...` under candidates; held file types under "On record ..." | attachment entities | each checked against the closed list: "on the attachment_type list: <code>" | file send for the held product |
| 4 | "gambar for this one" (alias) | `gambar` -> `lookup_option_keywords` alias of a drawing type (exact) | `File type <drawing>: ...` | attachment hint | kept on the list | file send |
| 5 | "price for the wh one" | `wh` -> finish suffix `-WH` (white) AND (at grounding) warehouses whose suffix is WH | `- "wh": spec finish = white (White)` | spec or warehouse hint | a resolvable warehouse code always wins (IW-10) | depends on the hint: shows the collision |

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
- **375px**: the five columns stack vertically; the links become numbered badges instead of arrows.

## What the trace already records (no change)

- `prompt_text` event: the full parser user block, so the exact injected lines (engine.py:4904).
- `understood` stage: `raw.parser_raw` (what the parser returned) and `raw.derived` (engine.py:4863-4902).
- `grounding` event: `changes` = grounding notes `{from, raw, to}` (engine.py:5194).
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

1. **Where does it live?** (a) a new "Index" tab in the console turn trace drawer, (b) inline under
   the `understood` stage. Recommendation: **(a)**, because it spans parser input, parser output,
   grounding and tool, not one stage.
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
