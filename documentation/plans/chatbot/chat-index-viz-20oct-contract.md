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
- Null -> `Empty`: "No list matching was recorded on this turn."
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

## v2 amendment (crew audit of 727d0ae23, 21 Oct): plainer, and the tool step back

Audit: the Sections table showed 79 raw prompt headings ("entities[].quantity", "SELF_REFERENCE"
labelled Closed lists at 6,175 because `{{specs}}` sits under it); per-turn values were raw
(`spec finish = french_gold`); "parser" / "tokens" were on screen; the mock's last step (the tool
call) was missing. This amendment replaces the parts it names; everything else above stands.

### On-screen words (additions to the wording table)

- Never on screen: "parser", "token(s)", "grounding", any `snake_case` key. Say "the bot",
  "what the bot understood", "size".
- The failed line becomes: "The matching step failed on this turn; the bot ran without it."

### BE-1 (match dicts gain two plain fields, written at trace time)

Every match dict also carries `"plain"` and `"source"` (computed in `block_with_matches`, which has
the registry rows):

| Match | plain | source |
|---|---|---|
| spec value (candidate, code suffix, held) | "<Label>: <display>" e.g. "Finish: French Gold" | "from the product <label lower> list" (code suffix adds " (code ending -FRG)") |
| numeric spec | "<Label>: <number>" | same |
| flag spec | "<Label>: yes" / "<Label>: no" | same |
| product type | "Product type: <display>" | "from the product type list" |
| product code | "<CODE> (<name>)" as the item shows it, without the leading "code " | "from the product codes" |
| set code | "<CODE> (<name>)" | "from the product sets" |
| size | "Size: <N> <unit>" | "from the product sizes" |
| file type | the type name | "from the file type list" |
| certificate kind | the kind name | "from the certificate list" |
| certificate scheme | the scheme name | "from the certificate scheme list" |
| held (any of the above) | as above | "on record for the held product" |

### BE-2 (`index_match`, plain values, tool step)

- `rows[].matched[]` = `{plain, source, close_spelling}` (fall back to `entry` / `list` for an older
  event without them). `parser_got` keeps the raw lines (shown only behind the toggle).
- `understood[].text` in plain words, using `db` when given (registry labels + `value_labels`,
  attachment type names; without `db`, the key with "_" -> " " and the value as is):
  `"frg" read as Finish: French Gold`, `"zzkt71ss" read as product ZZKT71SS`,
  `"basin" read as product type Basin`, `"drawing" read as file type ZZ Technical Drawing`,
  `"ce" read as certificate scheme CE`, `"frg" read as a warehouse`, `"ali" read as a sales agent`.
  No hint: `"basin"`.
- `result[].text`: "Changed: read as Finish: White" (labels and value labels as above);
  "Kept: on the file type list (ZZ Technical Drawing)" (the type name, not the code).
- `held[]` = plain strings ("Finish: Chrome").
- NEW `looked_up`: from the turn's `tool` event, `null` when none:
  `{"what": "<tool name, '_' -> ' ', first letter upper>", "details": ["<Key>: <value>", ...]}`;
  details from `args` in order, key "_" -> " " capitalised, lists joined ", ", skipping null / "" /
  [] / dict values / any value that looks like a UUID; at most 8.

### BE-3 (architecture: groups, not headings)

`sections` is replaced by `groups`, at most these four, in this order, each
`{"name", "size", "share"}` (`size` = round(chars / 4); `share` = size / total, 0..1), a group with
size 0 omitted:

1. "Rules": the template's own text (variables removed), minus the example lines.
2. "Examples": the template's own text lines that hold a quoted phrase followed by `->`
   (regex `"[^"\n]+"\s*->`), counted whole-line.
3. "Product lists": the rendered `{{specs}}`, `{{attachment_types}}`, `{{certification_types}}`
   wherever they sit (the index pointer lines in index mode on a CLOSED LISTS version, the full
   lists otherwise).
4. "Lists from other settings": every other rendered registry variable (`{{current_date}}` counts
   under Rules).

`total_size` replaces `total_tokens` (= sum of the groups). Each `lists[]` item gains `"how"`, one
plain sentence:
- Specifications: "A word of the message matches a value, its name or a synonym from Product
  Specifications, or a code ending like -FRG; close spellings count too."
- File types: "A word matches a file type's code, name, its words or an alias keyword; close
  spellings count too."
- Certificates: "A word matches a certificate kind or a certificate scheme by its name or words;
  close spellings count too."
- Warehouses: "Not sent to the bot; a warehouse the bot reads is checked against the warehouse
  list (the exact code, or the part after the last dash)."
`sent_each_message_tokens` / `full_list_tokens` are renamed `sent_each_message_size` /
`full_list_size`.

### FE-1 (per-turn section)

- Visible columns, exactly: "Word", "Matched list entry", "What the bot understood",
  "Kept or dropped". The entry cell shows `plain` and, muted, `source` (and "close spelling").
- One toggle button above the rows, "Show details" / "Hide details": when on, each row also shows
  "What the bot was given" with the raw `parser_got` lines (monospace). Off by default.
- After the rows: "What the bot looked up" with `looked_up.what` and its details; absent when
  `looked_up` is null.
- Held collapsible text unchanged ("Also sent: N lines on record for the held product"), plain lines.

### FE-2 (Architecture tab)

- Summary: "Each message, v<version> gives the bot about <total_size formatted 35.7k> of
  instructions and lists." + the same badge as before.
- Flow, six boxes, exactly: "Customer's message" -> "Matched list entries" -> "What the bot was
  given" -> "What the bot understood" -> "Kept or dropped" -> "What the bot looked up".
- Lists table columns: "List", "Comes from", "How a message is matched", "Entries",
  "Size each message", "Full list size".
- "What the bot is given" table: "Part", "Size" (formatted like the summary, with a bar), at most
  the four groups. No heading names anywhere.
