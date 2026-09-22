# Evidence - dealer stock verdict (AC-1780, AC-1781)

Filled in during the ONE live pass at the end of the lane (`documentation/agents/browser-verification.md`
/ `documentation/agents/chatbot-verification.md`), not per slice. Run both:

```
venv/bin/python scripts/chatbot_journey.py --base http://localhost:<lane-port> \
    --contact 404285551 --chain tests/chatbot/journeys/dealer-stock-verdict.json \
    --sleep 8 --record tests/chatbot/journeys/_record

venv/bin/python scripts/chatbot_console_check.py \
    tests/chatbot/console_cases/2026-09-22-dealer-stock-verdict.yaml \
    --base-url http://localhost:<lane-port> --sleep-seconds 8
```

Before either run: apply the setup SQL in both files' own headers (dealer test contact
`404285551` flipped to `availability` mode, warehouses BRW + MWH), and re-check the two
prerequisites that can drift on a shared prod copy - the parser prompt's `proceed_anyway` /
`entities[].quantity` publish state (D13) and `system_settings.chatbot_stock_low_threshold_pct` /
`default_product_standard_lead_time_days` (50 / 90 assumed below). Revert the contact's policy
row after the pass.

## Journey (`dealer-stock-verdict.json`, AC-1780)

| case | expected (ruling) | result | notes |
|---|---|---|---|
| A - four products, two quantities, then fill | D14 noted+ask, then D6/D17 four verdict lines in asked order | | |
| B - restated quantity | D16 replace, missing unchanged | | |
| C - just proceed | D15 answers noted, names not checked | | |
| D - detour (promotion then ETA) then fill | D21-D24 parks silently across two detours, fills after | | |
| E - resume by naming | D22 re-asks only what is missing, no verdict on resume | | |
| F - never mind closes | D23 close by the dealer's own words; a later bare number does not reopen | | |
| G - detailed contact unchanged | D19/AC-1767 no loop, no verdict, byte-identical shape | | |
| H - 18-row verdict spot checks (rows 1,2,4,5,7,9,11,13,14,16) | D6, exact text per row (see file header) | | |

## Console check (`2026-09-22-dealer-stock-verdict.yaml`, AC-1781)

| case | expected (ruling) | result | notes |
|---|---|---|---|
| ask then noted-and-missing question | AC-1757, D14 | | |
| answer fills the task | AC-1762 | | |
| just proceed | AC-1763, D15 | | |
| detour parks silently, fill resumes | AC-1771, D22 | | |
| detailed contact unchanged | AC-1767, D19 | | |

## Environment notes at run time

- Parser prompt `chatbot_semantic_parser` production version / `has_proceed_anyway`: ____
- `chatbot_stock_low_threshold_pct` / `default_product_standard_lead_time_days`: ____
- Any case marked "environment-blocked" (prompt not yet published) rather than FAIL: ____
- Journey step 6 asked-order check (no automated matcher - read `--record` output by eye): ____
- Screenshot / transcript reference (if browser-driven instead of the script): ____
