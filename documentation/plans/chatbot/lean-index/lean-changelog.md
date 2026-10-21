# LEAN-INDEX parser candidate: changelog against v88

Base: `chatbot_semantic_parser` v88 (id 4646e9a2-696e-4461-955e-5722b916b763), the consolidated template.
Candidate: `parser-lean.txt` (the template text plus one trailing newline, the same convention as the v88 copy
taken with `psql -t`; psql's backquote strips that one newline when `explore-data.sql` reads the file).
Every `{{variable}}` is kept (16, same set). Kept untouched: grammar particles (R-X-04, R-P3-09), FLYER
(R-P3-15), KNOWN BRANDS (R-P2-09), output and routing rules.

Size (template text): v77 142,657 chars / 35,651 tokens; v88 70,537 / 18,347; lean 70,453 / 18,318
(o200k_base).

## Edits (old -> new)

1. Line 157, R-P2-06 FILE, (a) no implied-photo phrase and (c) spec sheet is not the drawing item:
   - old: `a drawing, TD, CAD or spec sheet is the item that holds drawings; a photo, image, picture, "how does it
     look" or "show me" the item that holds photos`
   - new: `a drawing, TD or CAD is the item that holds drawings; a photo, image or picture the item that holds
     photos`
   - The parenthetical after it is kept: `(a "show me" over one offered list is that pick, see R-P1-05; "show me
     everything" widens the ask, see R-P3-09)`. It says where "show me" is NOT a photo ask, which still applies
     once "show me" is an alias word on the photo line.
2. Line 190, R-P2-12 ACCESS, (b) no hard-coded brand name:
   - old: `A brand with dealer or office is that brand's level ("sorento" + "dealer" -> Sorento Dealer);`
   - new: `A brand with dealer or office is that brand's dealer or office level;`
   - `{{access_levels}}` renders `contact_access_types.name` (data: e.g. "Sorento Dealer", "Mocha Office"); no
     other literal brand is near it.
3. Line 200, R-P3-01 product_attachment, (a) no implied-photo phrase:
   - old: `a file of one product: photos and how it looks, drawings,`
   - new: `a file of one product: photos, drawings,`

## Checked, not edited ("spec")

- Line 162: `A bare "spec" beside a code asks for the product's spec list ... even when a Words line holds "Spec"
  (see R-P3-05); a spec sheet, drawing or PDF the message asks for is a file.` Names spec sheet and drawing as
  two separate files; it does not equate them.
- Line 200: `a spec sheet` is listed beside `drawings` as its own file.
- Lines 133, 140, 231: spec values and the bare-spec attribute rule; no file mapping.

# v90 candidate (`parser-v90.txt`): v89 (`parser-lean.txt`) plus four general reading rules

Each rule is worded once, in the section that already states the related rule; no word list, no conversation
example. Size: v89 70,453 chars / 18,318 tokens; v90 71,220 / 18,506 (o200k_base). Every `{{variable}}` kept.

1. R1, R-X-04 MEANING (line 25): the typo precedent generalised to listed items.
   - old: `any case, short form or misspelling: "oustaning" is outstanding,`
   - new: `any case, short form or misspelling, and a misspelled word names the listed item the word means (a status,
     a promotion or flyer kind, a file type, any value on a list): "oustaning" is outstanding,`
2. R2, R-P2-04 CONF (line 151, v90 152): spelling never lowers `confident`; the false reasons are unchanged.
   - old: `` `confident` is true when raw is one cleanly typed referent: a single word, ``
   - new: `` `confident` is true when raw is one cleanly typed referent, whatever its spelling (one word read as
     exactly one listed item is confident, misspelled or not): a single word, ``
3. R3, R-P1-02 CARRY (new bullet after line 54, v90 55): no paging rule existed; added beside the continuation
   rules.
   - old: (none)
   - new: `- After a reply that listed a page of items, a message that only asks for more of them, in any language or
     spelling, continues that same set: `continuation` true (R-X-06) and keep, with the held domain and no entity
     or file type of its own; never a new ask.`
4. R4, R-P3-08 ACTIVE (line 269, v90 270): a negated lifecycle or status word flips; linked to R-P3-06 STATUS.
   - old: `null otherwise, the default ("show me Sorento promotions" is null).`
   - new: `null otherwise, the default ("show me Sorento promotions" is null). A negated lifecycle or status word
     means its opposite: a negated inactive word is true, a negated active word false, and a negated order status
     word is never that status (see R-P3-06).`
5. R3's output field, R-X-06 OUT (line 343, v90 344): paging runs only on `continuation` true
   (`turn_runtime.with_set_more`), which v89 declared always false.
   - old: `` - `continuation` false; `reference_target`, `po_refs`, ``
   - new: `` - `continuation` true when the message only asks for more of the set the last reply listed (see
     R-P1-02), else false; `reference_target`, `po_refs`, ``

# v91 candidate (`parser-v91.txt`): v90 plus two wording fixes from the v90 battery controls

Size: v90 71,220 chars / 18,506 tokens; v91 71,402 / 18,548 (o200k_base). Every `{{variable}}` kept.

6. (A) R1, R-X-04 MEANING (line 25): a correctly spelled kind word came back as its label, not its code; the value
   is the item's code as listed. (B) R3, R-P1-02 CARRY (line 55) and R-X-06 OUT (line 344): "more <file type> of
   <code>" continued the set; only a message that names nothing new continues.
   - (A) old: `, and a misspelled word names the listed item the word means (a status, a promotion or flyer kind, a
     file type, any value on a list):`
   - (A) new: `, and a word, misspelled or not, names the listed item it means (a status, a promotion or flyer kind, a
     file type, any value on a list) by that item's code exactly as its list line gives it, never its label:`
   - (B) R-P1-02 old: `a message that only asks for more of them, in any language or spelling, continues that same set:
     `continuation` true (R-X-06) and keep, with the held domain and no entity or file type of its own; never a new
     ask.`
   - (B) R-P1-02 new: `a message that only asks for more of them and names nothing new, in any language or spelling,
     continues that same set: `continuation` true (R-X-06) and keep, with the held domain; a message that also names
     a product, a file type, a filter or any other new thing is a new ask (`continuation` false).`
   - (B) R-X-06 old: `` - `continuation` true when the message only asks for more of the set the last reply listed (see
     R-P1-02), else false; ``
   - (B) R-X-06 new: `` - `continuation` true when the message only asks for more of the set the last reply listed and
     names nothing new (see R-P1-02), else false; ``

# v92 candidate (`parser-v92.txt`): v91 with R1 scoped so it does not override the brand rule

Size: v91 71,402 chars / 18,548 tokens; v92 71,433 / 18,557 (o200k_base). Every `{{variable}}` kept (16).

7. R1, R-X-04 MEANING (line 25): "the item's code, never its label" read against a brand would contradict R-P2-09
   (line 176: a brand's `canonical_code` is the brand name exactly as listed, never the code); the brand keeps
   R-P2-09.
   - old: `(a status, a promotion or flyer kind, a file type, any value on a list) by that item's code exactly as its
     list line gives it, never its label:`
   - new: `(a status, a promotion or flyer kind, a file type, any other closed-list value; a brand keeps R-P2-09) by
     that item's code exactly as its list line gives it, never its label:`
