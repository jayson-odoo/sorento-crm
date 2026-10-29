# PLAN: PARSER-X-AND-OUTSTANDING (prod case #b6e9)

Status: Plan. Track: small fix (parser prompt edit + parser gold rows; no migration, no auth change).
Base: `claude/restore-outstanding-summary-wmza75` (PR #1973, REPORT-OUTSTANDING-SUMMARY).

## Problem

"SRT5733 stock and outstanding" parses (v189, gemini-3.5-flash-lite) as order_status null, status null, basis null,
sales_basis null, document [], entities [product SRT5733], domain_hint inventory, asks
[{inventory, check_stock}, {order, check_order}]. No parser field carries "outstanding", so the order half falls to the
plain DO-list period question. #1973 already prints stock + the outstanding summary for every outstanding reading.

## Fix

Prompt only (semantic, no word list): the order half of an "X and outstanding" message is an outstanding order ask, so
the parser fills the outstanding status on it. Gold rows for #b6e9, "X and Y" shapes, and negatives.
