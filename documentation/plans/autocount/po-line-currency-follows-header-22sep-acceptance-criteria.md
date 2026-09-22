# UAC: PO line currency follows header (22 Sep 2026)

- AC-PLC-1: FoundryX push, header `currency: "MYR"`, lines without `currency` -> every stored line carries `MYR`.
- AC-PLC-2: FoundryX push, header `USD`, one line states `CNY` -> that line `CNY`, the rest `USD`.
- AC-PLC-3: FoundryX push, no currency anywhere -> header `CNY` (existing header rule), lines equal the header; no line-level CNY literal remains in `_line_values`.
- AC-PLC-4: Excel upload creating a new line on a PO header already holding `MYR`, file has no currency column -> line `MYR`.
- AC-PLC-5: Excel upload restating `MYR` on a line currently `CNY` -> line `MYR` (existing refresh rule still holds).
- AC-PLC-6: Backfill script dry-run reports the count and writes nothing; `--apply` flips only autocount lines whose header currency is set and differs; non-autocount rows untouched.
- AC-PLC-7: Chatbot last-cost for MAP4944A after backfill on the local copy prints `RM`/`MYR 31.83` for PO-2020/09-0009 (manual check by captain, MCP presenter untouched).
