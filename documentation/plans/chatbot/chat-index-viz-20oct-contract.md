# CHAT-INDEX-VIZ build contract (owner approved mock v2, 21 Oct; simplicity is the bar)

Owner, on mock v2: "Ok, make sure it is simpler and easy to understand and visualize". The bar:

- fewer panels;
- plain words on screen, never internal names (no `hidden_keys`, `grounding`, `SYSTEM_BLANKS`,
  `closed_lists_index`, `hint` on screen);
- one left-to-right flow: **message words -> matched list entries -> what the parser got -> what it
  understood -> kept / dropped**;
- numbers only where they help (tokens per section).

Base: this lane carries the explore build (merge of c899b3ec5); index mode lives there.

## Wording (the only on-screen words for the internals)

| Internal | On screen |
|---|---|
| index mode / block mode | "Only the matching entries are sent" / "Full lists are sent" |
| parser | "the parser" |
| grounding drop, finish short form on a warehouse hint | "Dropped: a finish code ending, not on the warehouse list" |
| grounding "dropped: not on the closed lists" / "not a listed document type" | "Dropped: not on the file type list" |
| grounding "unknown product type" | "Dropped: not a known product type" |
| grounding "on the <list> list: <code>" | "Kept: on the <plain list> list (<code>)" (`attachment_type` -> "file type", `cert_kind` -> "certificate", `cert_scheme` -> "certificate scheme") |
| grounding "canonical dropped: not on the candidate block" | "Changed: product code not among the matches, removed" |
| grounding "canonical refused: ..." | "Changed: several product codes fit, the bot asks which" |
| grounding `to` = list of spec dicts | "Changed: read as " + "; ".join("<label or key> = <value>") |
| grounding `to` = other string | "Changed: read as <to>" |
| no grounding note for the entity | "Kept" |
| entity hint | product -> "a product", category -> "a product type", specification / spec -> "a specification", attachment_type -> "a file", warehouse -> "a warehouse", brand -> "a brand", customer -> "a customer", anything else -> the hint itself |

## BE-1 per-turn trace event (index mode only)

File `app/services/chatbot/head/closed_lists_index.py`:

- NEW `block_with_matches(db, entries, message, held_ids, hidden=frozenset()) -> tuple[list[str], list[dict]]`.
  `entries` is the `candidates.shortlist` result (`list[WordCandidates]`). It returns exactly the
  lines `block(db, candidates.candidate_lines(entries), message, held_ids, hidden)` returns, and one
  match dict per entry it sent:
  `{"word": str | None, "list": str, "entry": str, "close_spelling": bool, "held": bool, "line": str}`
  - candidate items (from each `WordCandidates`: `word` = `gram`, one dict per item):
    item starting `code ` -> list "Products"; `product type ` -> "Product types"; `spec ` or
    `flag` -> "Specifications"; `size ` -> "Sizes"; a leading `near ` sets `close_spelling` true and
    is stripped from `entry`; `line` = that word's candidate line.
  - code-suffix lines: `word` the folded suffix ("frg"), list "Specifications",
    entry = the spec item text, `close_spelling` false.
  - file type / certificate kind / scheme lines a word names: `word` = the gram that matched,
    list "File types" / "Certificates" / "Certificate schemes", entry = the line,
    `close_spelling` = matched only by near spelling.
  - held lines: `word` None, `held` true, list "On record for the held product", entry = line.
- `block()` keeps its signature and output (existing tests must stay green); it may delegate.
- `_named` keeps returning bool; add a helper that also says which gram matched and whether it
  was near.

File `app/services/chatbot/engine.py`:

- `_candidate_lines(...)` gains keyword `matches_out: list | None = None`. In index mode it calls
  `block_with_matches` and extends `matches_out`; on the index savepoint failure it appends
  nothing and the caller records `failed: true`. Return shape unchanged (3-tuple).
- After a SUCCESSFUL parse, beside `turn_trace.add("prompt_text", ...)`, when
  `parser_config.closed_lists_index` is true:
  `turn_trace.add("closed_lists_index", {"words": candidates._tokens(user_turn.own_text), "matches": matches, "failed": failed})`.
  Block mode: no such event (block-mode traces stay byte-identical).

## BE-2 turn detail: `trace_detail.index_match`

File `app/services/chatbot/trace_detail.py`: `compose_trace_detail` gains `"index_match": _index_match(records)`.
`None` when the turn has no `closed_lists_index` event. Else:

```json
{
  "words": [{"text": "stock", "matched": false}, {"text": "frg", "matched": true}],
  "rows": [
    {
      "word": "frg",
      "matched": [{"list": "Specifications", "entry": "spec finish = french_gold (French Gold)", "close_spelling": false}],
      "parser_got": ["- \"frg\": spec finish = french_gold (French Gold)"],
      "understood": [{"text": "\"frg\" as a specification: finish = french_gold"},
                     {"text": "\"frg\" as a warehouse"}],
      "result": [{"outcome": "kept", "text": "Kept"},
                 {"outcome": "dropped", "text": "Dropped: a finish code ending, not on the warehouse list"}]
    }
  ],
  "held": ["spec finish = chrome (Chrome)"],
  "not_from_lists": [{"text": "\"IB\" as a warehouse", "outcome": "kept", "result": "Kept"}],
  "failed": false
}
```

- `words`: the event's `words`; `matched` true when its fold (`candidates._phrase`) is a matched
  word or a word of a matched multi-word gram.
- `rows`: one per distinct non-held match `word`, in message order; `matched` the plain entries;
  `parser_got` the distinct `line`s for that word in order.
- `understood`: the `understood` stage's `raw.parser_raw.entities` whose folded `raw` equals the
  row word or contains it as a whole word. Text: `"<raw>" as <plain hint>` plus `: <value>` where a
  value exists (`spec_key = spec_value`, else `canonical_code`, else `listed_item`).
- `result`: per understood entity, in the same order, from the `grounding` event's `changes`
  (note with `from` == entity hint and folded `raw` == folded entity raw), worded per the table.
- `held`: lines of held matches. `not_from_lists`: entities matching no row, same text + result.
- `failed`: the event's `failed`.

## BE-3 prompt architecture endpoint

`GET /api/v1/system/ai-assistant/prompts/{name}/versions/{version}/architecture`
(same router + permission as `.../versions/{version}`: `system.ai_assistant_settings.view`).
404 for an unknown key or version; for any key other than `chatbot_semantic_parser`, 404 with
detail "No architecture view for this prompt". Service function in a new module
`app/services/chatbot/prompt_architecture.py` (`describe(db, version) -> dict`).

```json
{
  "version": 77,
  "mode": "index",
  "uses_closed_lists": true,
  "total_tokens": 35700,
  "sections": [
    {"title": "PRICE TERMINOLOGY", "tokens": 177, "kind": "text"},
    {"title": "ACCESS LEVELS", "tokens": 356, "kind": "text"},
    {"title": "CLOSED LISTS", "tokens": 893, "kind": "closed_lists"}
  ],
  "lists": [
    {"key": "specs", "name": "Specifications", "source": "Product Specifications", "href": "/master-data-management/product-specifications",
     "entries": 42, "sent_each_message_tokens": 36, "full_list_tokens": 5120},
    {"key": "attachment_types", "name": "File types", "...": "..."},
    {"key": "certification_types", "name": "Certificates", "...": "..."},
    {"key": "warehouses", "name": "Warehouses", "source": "Warehouses", "href": "/inventory-management/warehouses",
     "entries": 9, "sent_each_message_tokens": 0, "full_list_tokens": 0, "checked_only": true}
  ]
}
```

- Sections: the RAW template split at lines matching `^== .+ ==$` (title = text between the `==`,
  stripped); text before the first heading is a section titled "Opening" (omitted when blank).
  Each section is rendered (variables substituted the way `render_resolved` does, with
  `current_date` = today's date text and, when `mode` is index AND `uses_closed_lists`, the
  `SYSTEM_BLANKS` values for the three closed lists) and `tokens = round(len(rendered) / 4)`.
- `kind`: "closed_lists" when the raw section holds `{{specs}}`, `{{attachment_types}}` or
  `{{certification_types}}`; "filled_from_data" when it holds any other `{{var}}`; else "text".
- `total_tokens` = sum of section tokens.
- `mode` = `closed_lists_index.read_mode(db)`; `uses_closed_lists` = `closed_lists_prompt.gate_on(raw)`.
  When not `uses_closed_lists`, the three closed lists report `sent_each_message_tokens` =
  `full_list_tokens` (the version sends them whole).
- `lists`: name / source / href / entries from `chatbot_prompt_vars.VARIABLES[key]` (label,
  source, href, count). `sent_each_message_tokens` = `round(len(SYSTEM_BLANKS[key]) / 4)`;
  `full_list_tokens` = `round(len(render_value(db, key)) / 4)`. Warehouses: `entries` = count of
  `warehouses` rows the session sees, tokens 0, `checked_only` true.

## FE-1 per-turn "Index match" section

- Types: `chat-history/types/chatbotTurn.types.ts` add `IndexMatch` (shape above) and
  `TurnDetail.index_match?: IndexMatch | null`.
- `chat-history/components/IndexMatchSection.tsx` exports `IndexMatchSection({ indexMatch })`.
- `TurnDetailDrawer.tsx` renders `<Section title="Index match" testId="section-index-match">` right
  after Parse.
- Null -> `Empty`: "This turn sent the full lists, so nothing was matched."
- `failed` -> one line "The matching step failed on this turn; the parser ran without it."
- Top: the message words as chips, matched ones filled (`Badge`), others plain.
- Then a 5-column flow, header labels exactly: "Word", "Matched list entry", "What the parser got",
  "What it understood", "Kept or dropped". One row per `rows[]` item
  (`data-testid="index-row-<word>"`). Close spelling shows "close spelling" next to the entry.
  Outcome uses `Badge` variant success (kept), destructive (dropped), warning (changed).
  At < 640px each row becomes a stacked card with the same five labels.
- `not_from_lists` rows render after, with the word cell "(not from the lists)".
- `held` (when any): a closed `Collapsible` "Also sent: N lines on record for the held product".
- No UUIDs, no internal names.

## FE-2 prompt "Architecture" tab

- Service `ai-assistant/services/aiPromptsService.ts`: `getPromptArchitecture(name, version)`,
  type `PromptArchitecture`. Hook in `ai-assistant/hooks/useAIAssistantPrompts.ts`:
  `usePromptArchitecture(name, version, enabled)`.
- `PromptDetail.tsx`: a third `TabsTrigger value="architecture"` labelled "Architecture"
  (`data-testid="editor-mode-architecture"`) ONLY when `name === 'chatbot_semantic_parser'`;
  chip editor stays mounted hidden as under Preview.
- `prompts/components/PromptArchitecture.tsx` (`data-testid="prompt-architecture"`), three
  blocks, no more:
  1. Summary line: "v<version> sends about <total> tokens to the parser on every message." and a
     `Badge`: "Only the matching entries are sent" (index + uses_closed_lists) or "Full lists are
     sent".
  2. The flow, left to right, 5 boxes with arrows (stack at < 640px), labels exactly:
     "Customer's message" -> "Matched list entries" -> "What the parser got" -> "What it
     understood" -> "Kept or dropped". Under "Matched list entries" the list names (from
     `lists`, minus checked_only ones); under "Kept or dropped": "Checked against the same lists
     and the warehouse list".
  3. Table "Lists": columns "List", "Comes from" (link to `href`), "Entries", "Sent each message"
     (tokens), "Full list" (tokens; "-" for checked_only). Then table "Sections": "Section",
     "Kind" ("Text" / "Filled from data" / "Closed lists"), "Tokens" with a thin bar scaled to
     the largest section.
- Loading: `SectionSkeleton`; error: one line "Could not load the architecture for this version."

## Tests (red first)

- `tests/chatbot/test_chat_index_viz_trace.py`: block_with_matches (code-suffix, file type exact,
  near spelling, held lines, block() unchanged); engine adds the event in index mode only.
- `tests/chatbot/test_chat_index_viz_detail.py`: `_index_match` composition + every wording row.
- `tests/test_prompt_architecture_api.py`: endpoint shape, sections split + kinds, index vs block
  tokens, 404s, permission.
- vitest: `IndexMatchSection.test.tsx`, `PromptArchitecture.test.tsx`, PromptDetail tab visible
  only for the parser key.
