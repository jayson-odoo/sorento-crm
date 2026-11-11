# UAC: AGENT-PANEL-FIXES

1. After a panel turn finishes, the next message in the same chat is answered (never the busy
   reply), even when the lock release runs on a different DB connection than the acquire.
2. A lock left behind by a crashed turn frees itself after the turn time budget plus a margin.
3. A quotation compare answer never shows a bare percentage: the tool labels it "x% below list" /
   "x% above list".
4. The per-turn input token total for a quotation compare question drops versus main (numbers in PR).
5. The trace drawer for an agent turn shows each round (model, ms, tokens in/out, stop reason), the
   thinking summary, each tool call (name, args, result size, ms, ok/error) and "Context sent to the
   AI"; no "Not recorded" rows for legacy stages on agent turns.
6. "View trace" in the AI panel opens the drawer over the current page, same tab, no navigation.
7. Steps, route line and View trace show for admins only.
