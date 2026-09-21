# Appendix A (129 lines) coverage - status, 16 Sep 2026

`contract/line-001-stock-by-location.json` re-recorded from a clean run this session
(the previous recording carried an intermediate engine state - "stage remembered, no
sent record" - a non-standard action shape; re-recorded from the same source turn,
now one real divergence remains: `send_attachments` missing, the same engine finding
already logged in `DIVERGENCES.md`).

**The rest of Appendix A's 129 lines are NOT individually linked or hand-built this
session** - time-boxed. A first-pass automated slug-keyword match against the 190
already-recorded `console/`/`prod_sample/` cases found only 33/129 lines with a
plausible filename match (`/tmp/contract_line_matches.json`, not committed - a rough
proxy only, unverified, many real matches will be missed since a case's CONTENT
covers a line even when its slug does not literally name it). Doing this properly -
reading each of the 129 lines, checking every existing case's actual `verdict`/
`expected` for a real match, and hand-building the genuine gaps with a comment
naming the line - is a dedicated follow-up pass, not a few-minutes addition once the
corpus already exists. Flagged for the captain rather than rushed to a low-confidence
`contract_lines` field that would misrepresent coverage.
