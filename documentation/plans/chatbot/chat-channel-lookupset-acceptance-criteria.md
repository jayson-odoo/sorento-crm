# UAC: CHAT-CHANNEL-LOOKUPSET

- AC-CCL-1: After migration, Master Data > Lookup sets holds `sales_channel_alias` with options
  `dealer` (keywords retail, retailer, 经销商, 零售, peruncit) and `project` (keyword project team).
- AC-CCL-2: Re-running the migration adds no duplicate set, option or keyword and leaves an
  owner-added keyword in place.
- AC-CCL-3: The parser's sales channel candidates for "retail sales last month", "零售 sales" and
  "经销商 sales" include `dealer`; the parser verdict sets `sales_channel = dealer` (dev eval).
- AC-CCL-4: A keyword the owner adds later (Lookup sets screen) is matched on the next turn with
  no code change; an option whose value is not dealer/project adds no channel.
- AC-CCL-5: An inactive set or option contributes no alias words.
- AC-CCL-6: Prompt template text and parser version are unchanged.
- AC-CCL-7: A span call whose provider reports no cached tokens stores `cached_tokens = 0`, so
  the turn's cost is priced (not blank). Rows written before the fix stay NULL (no backfill).
