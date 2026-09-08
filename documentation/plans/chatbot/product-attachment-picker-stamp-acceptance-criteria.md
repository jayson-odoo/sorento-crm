# UAC: product_attachment picker stamp

Plan: `PLAN-product-attachment-picker-stamp.md`. All pytest, each seeding its own chain
on the blank schema (CI's DB is empty), driving the REAL resolver, gate, dym_transform,
dym_annotate, run_miss_lane and build_suggest_offer with only the MCP client monkeypatched
(the pattern `tests/chatbot/test_product_attachment_picker_stamp.py` already uses).

- AC-1 Picker stamp. "photo for srtwc286" with SRTWC286-SH carrying a Product Photos
  attachment and SRTWC286-SH-200 not: the picker lines read
  `1. SRTWC286-SH-200 - no Product Photos` and `2. SRTWC286-SH - has Product Photos`
  (numbering and order exactly as the gate rendered them; no line dropped, none reordered).
- AC-2 Noun is the resolved type name, not the raw token. Same turn worded "gambar for
  srtwc286" (parser canonical_code "photo") still stamps "Product Photos". A request whose
  resolved type name matches `_CERT_PREFIX_RE` stamps "certificate" as today.
- AC-3 D1 surfaces. A product_attachment did-you-mean miss (one unresolved token with two
  candidates, one holding the type) renders the has/no suffix on the D1 offer lines, which
  today render bare for this domain.
- AC-4 Company-suffixed line. Two companies each own a product coded SRTWC286-SH; the gate
  renders `SRTWC286-SH (Company A)` / `SRTWC286-SH (Company B)`; the probe finds the type
  on Company A's only. Lines read `- has Product Photos` for A and `- no Product Photos`
  for B.
- AC-5 Twin code renders bare. A code that resolves to two uuids and is flagged ambiguous
  by the annotator gets NO suffix, while its unambiguous siblings are stamped.
- AC-6 Probe failure still renders the bare picker (the existing fail-open rule): with
  the MCP client raising, the picker is byte-identical to today's.
- AC-7 Existing suites: `pytest tests/chatbot -q -k "dym or picker or suggest or miss"`
  green, no capture-graded node body modified (`build_suggest_offer` is graded; its
  captures must still pass).
- AC-8 Browser (tester, agent-browser via sidebar, stack over `sorento_ai_automation_0907`,
  backend from this lane): Chatbot Console, contact Jayson, "photo for srtwc286" shows the
  ten-line picker with `- has Product Photos` on SRTWC286-SH and `- no Product Photos` on
  the rest that lack it (verify the expected split with SQL on product_attachments joined
  to attachment_types first); replying "4" returns SRTWC286-SH.jpg as before.
