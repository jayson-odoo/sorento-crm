# PLAN: CHAT-CHANNEL-LOOKUPSET - sales channel words from a lookup set; span calls record their cost

Status: in progress (small fix track: backend only, < 300 lines, one additive seed migration, no auth/RBAC, no UI)

UAC: `chat-channel-lookupset-acceptance-criteria.md` (this folder).

## Why

1. Owner, 29 Oct 2026: "retail" means Dealer, and staff also say 经销商 / 零售 / peruncit. Today the
   parser's sales channel rows carry only the bare code word (`head/lookup_lists.py:693`, from
   `SALES_CHANNELS = ("dealer", "project")` at `reports/ask.py:386`), so "retail sales" never
   surfaces the dealer row.
2. Every v70 turn shows no cost: the span call stores `cached_tokens` as `... or 0) or None`
   (`head/span_extract.py:163`), the pricer treats NULL as unknown, and the turn cost blanks.
   The parser stores 0 for the same case (`head/parser.py:1403`).

## Architecture

- Layer: lookup row building (`head/lookup_lists.load_rows`), the same place file types read their
  aliases (`_file_type_rows`, `pv._alias_words(db)` at `lookup_lists.py:550`).
- Owner principle: rows come from the source (the code values in `SALES_CHANNELS`); the lookup set
  only holds OPTIONAL aliases keyed by those values. An option whose value is not in
  `SALES_CHANNELS` is ignored by construction (rows iterate `SALES_CHANNELS`, never the set).
- Shared mechanism reused: `chatbot_prompt_vars._alias_words(db, set_key)` (already serves
  `attachment_type_alias` and `brand_alias`). No new reader, no regex, no word list in code.
- `lookup_bindings` is NOT used: it validates writes to a stored table column
  (`services/lookup_validator.py`) and pre-selects a form default; no stored column holds the
  channel, and the existing alias sets carry no binding (`511_attribute_first_lookup_sets.py`).
- Prompt text unchanged, parser version unchanged. The rendered candidate line is still
  `sales_channel: dealer`; only the texts the shortlist matches against grow.

## Changes

1. Migration `chan_alias_0001_sales_channel` (additive, idempotent, insert-only): lookup set
   `sales_channel_alias` (tenant NULL), options `dealer` / `project`, keywords
   dealer -> retail, retailer, 经销商, 零售, peruncit; project -> project team. Never updates a row
   an owner edited (INSERT ... WHERE NOT EXISTS / ON CONFLICT DO NOTHING). Downgrade drops the set
   (options and keywords cascade).
2. `lookup_lists.load_rows`: channel rows read `texts=(ch, *aliases.get(ch, []))` from
   `pv._alias_words(db, "sales_channel_alias")`.
3. `span_extract.py:163`: store `cached_tokens` as an int (0 when none), like the parser.
   No backfill: old v70 rows keep NULL (noted in the PR).

## Tests (red first)

- `tests/chatbot/test_chat_channel_lookupset.py`: channel rows carry the set's keywords; an option
  outside `SALES_CHANNELS` adds no row; inactive option/set contributes nothing; shortlist of
  "retail sales last month" / "零售 sales" / "经销商 sales" offers `sales_channel: dealer`.
- Migration test: upgrade seeds the set/options/keywords; a second upgrade adds no duplicates and
  keeps an owner-added keyword.
- `tests/chatbot/test_span_extract.py:665-669` flipped: cached_tokens is 0, not NULL, and the span
  usage row prices.

## Eval

Dev eval (crew-run, Gemini, minimal spend): "retail sales last month", "零售 sales",
"经销商 sales" resolve to `sales_channel = dealer`.
