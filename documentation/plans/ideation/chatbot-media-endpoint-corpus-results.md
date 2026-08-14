# Chatbot media endpoint - corpus run results (UAC S4-11)

**Run date:** 2026-08-14
**Corpus:** `/Users/tehjayson/Documents/foundryx/firstmate/data/multimodal-test-corpus/` (read-only,
outside the repo), scored against its `README.md` ground truth.
**How it was run:** `MediaExtractService.extract()` called directly per image, one pass each, with
`app.services.media_extract.service.fetch_media_bytes` patched to read the local PNG bytes instead
of hitting Respond.io's CDN. No n8n, no worker, no HTTP endpoint. `job.tier = "standard"` (the
non-degraded path) for all three.
**Provider/model actually used:** `media_image_provider` / `media_image_model` are both NULL on
`system_settings`, so `_resolve_image_provider` fell back to the `AIAssistantConfig` row, which
is `provider=openai`, `model=gpt-4o-mini`. Confirmed from the outcome object on every call, not
assumed - **`openai` / `gpt-4o-mini` ran all three images**.
**Runner script** (kept for reference, not committed): patches `fetch_media_bytes` per PLAN's
stated seam, builds a `MediaJobInput` per image, calls `MediaExtractService(db).extract(job)`, and
prints/serializes `outcome.result` plus timing and token counts.

No prompt or code changes were made as part of this run.

---

## Image 01 - manual delivery order screenshot (clean, axis-aligned)

`image_kind` returned: `document` (correct).

| field | ground truth | extracted | bucket |
|---|---|---|---|
| Debtor code | `300-L115` | entity `300-L115` hint=`customer`, confident | exact match |
| Customer | `LUXEWARE BATH AND ART` | entity `LUXEWARE BATH AND ART` hint=`customer`, confident | exact match |
| Document no. | `RF2608-016` | entity `RF2608-016` hint=`attachment`, confident | exact match (value); hint choice is a reasonable stretch - no better-fitting hint exists in the 14-value enum |
| Your Ref | `REP202607-0152` | entity `REP202607-0152` hint=`order`, confident | exact match |
| Document date | `13/08/2026` | not present anywhere in the output | refused-or-absent |
| Address (Ipoh, Perak) | present on the form | not present | refused-or-absent |
| Contact `017-429 3882` | present on the form | not present | refused-or-absent |
| Item code (line 1) | `ACC-SRT1011` | entity `ACC-SRT1011` hint=`product`, confident | exact match |
| DO reference (line 1) | `REP202607-0152` dated `07/07/2026` | date not present; code already captured above | refused-or-absent (the `07/07/2026` line-date) |
| Qty (line 1) | `1 UNIT` | attribute `quantity` = `1 UNIT`, confident | exact match |
| Trap A - compat codes `SRTWT8200`/`SRTWT5903`/`SRTWT5904` | must NOT become product entities | not present as entities | exact match (correctly excluded) |
| Trap A - wrongly-received `ACC-SRT1016` | must NOT become a product entity | not present as entities | exact match (correctly excluded) |
| Trap B - `#N/A` row | must not become a line item | not present as an entity or attribute | exact match |
| (spurious) | - | attribute `batch_number` = `ACC-SRT1011`, confident | **plausible-but-wrong** |

**The one plausible-but-wrong on image 01:** `ACC-SRT1011` is emitted a *second* time, as an
attribute with `kind: "batch_number"`. It is not a batch number - it is the same product code
already captured correctly as an entity, and it is exactly the "description repeats the item
code" case prompt rule 10 names ("the repeated code is the same entity, not a second one"). The
model treated the repetition inside the description text as a new value with a plausible-looking
but wrong kind instead of recognising it as the same code. A downstream consumer that trusts
`attributes[].kind` would be told this photo names a batch, and it does not.

**Trap A: PASS.** Only `ACC-SRT1011` is a product entity; the three compatibility codes and the
wrongly-received part are correctly kept out of `entities`.
**Trap B: PASS.** The `#N/A` row produced nothing.

The clean-screenshot case does regress on completeness in one place worth naming even though it
is not one of the two named traps: the document date (`13/08/2026`, unambiguous - day is 13) and
the line's own DO-reference date (`07/07/2026`) are both dropped silently. This is not a
misread - it is a genuine schema gap: `ATTRIBUTE_KINDS` has no `date` kind and none of the 14
entity hints fits a bare date, so the model has nowhere to put a value it clearly read, and rule 4
("never invent... if you cannot read something, leave it out") does not distinguish "illegible"
from "no field exists for this." The result looks identical to a miss even though nothing was
misread.

---

## Image 02 - RMA form (photographed, skewed, stamped, handwritten)

`image_kind` returned: `document` (correct).

| field | ground truth | extracted | bucket |
|---|---|---|---|
| Debtor code | `300-J093` | not present | refused-or-absent |
| Customer | `J&Y WORLD HARDWARE SDN BHD` | not present | refused-or-absent |
| RMA number | `RMA-SRT2608-0104` | not present | refused-or-absent |
| Date issued | `11/08/2026` | not present | refused-or-absent |
| Issued by | `SITI` | not present | refused-or-absent |
| Agent | `SEAN` | not present | refused-or-absent |
| Line 1 code | `SRTBF31612` | entity, confident | exact match |
| Line 1 qty | `7` | attribute `quantity`=`7`, **confident: false** | exact match on value; confidence flag is wrong (see finding below) |
| Line 2 code | `SRTBF31610` | entity, **confident: false** | exact match, and correctly flagged low-confidence |
| Line 2 qty (Trap C) | printed `6`, struck through, handwritten `4` | `conflicts[0]` = `{field: quantity, entity_raw: SRTBF31610, values: [{16, printed}, {4, handwritten}]}` | conflict correctly raised, entity correctly `confident:false` - but the **printed value it captured is wrong** (`16`, not `6`) - **plausible-but-wrong** |
| Line 3 code | `SRTBF11503` | entity, confident | exact match |
| Line 3 qty | `4` | attribute `quantity`=`4`, **confident: false** | exact match on value; confidence flag is wrong |
| Line 4 code | `SRTBF11501` | entity, confident | exact match |
| Line 4 qty | `4` | attribute `quantity`=`4`, **confident: false** | exact match on value; confidence flag is wrong |
| Line 5 code | `SRTBF11502` | entity, confident | exact match |
| Line 5 qty | `1` | attribute `quantity`=`1`, **confident: false** | exact match on value; confidence flag is wrong |

I zoomed the qty cell on line 2 directly (`Read` on a 4x crop) to check the README's claim against
the pixels rather than trust the description: it is a printed `6` with a diagonal strike through it
and a handwritten `4` beneath it - the README's ground truth is confirmed correct, and the model's
printed reading of `16` is confirmed wrong (there is no `1` anywhere in that cell).

**Trap C, answered directly:** yes, the result carries a `conflicts` entry naming **both** values
with sources (`printed` / `handwritten`), and the affected entity (`SRTBF31610`) is marked
`confident: false`. **It did not silently pick one.** That part of the design works. But the
printed value it recorded inside that correctly-triggered conflict is itself a misread - `16`
where the document says `6` - which is exactly the "confident, plausible, wrong quantity" failure
mode the trap exists to catch, just relocated one level in: the *disagreement* was caught, the
*printed value* was not read correctly.

**A second, systemic defect surfaced by this image, in code rather than in the model:**
`schema.py::_apply_conflicts` matches attributes to a conflict by `kind == field_name` alone (see
`app/services/media_extract/schema.py` around line 283), with no `entity_raw` on the attribute
side to disambiguate. Because the one conflict's `field` is `"quantity"`, **every** `quantity`
attribute in the document - lines 1, 3, 4 and 5, none of which have any disagreement - was also
forced to `confident: false`. The values (`7`, `4`, `4`, `1`) are all correct; only the confidence
signal is wrong, and it is wrong in the direction of crying wolf on four lines that were fine. This
is a direct, reproducible consequence of `MediaAttribute` having no field to carry which line an
attribute belongs to (`{kind, raw, confident}` - no `entity_raw`), so a genuinely per-line conflict
becomes a document-wide one the instant more than one attribute shares a `kind`. Any future
multi-line document with an unrelated quantity conflict will reproduce this.

**The date, answered directly:** `11/08/2026` is **not returned in any form** - not the raw printed
string with an ambiguity conflict (as S4-04 specifies), and not silently resolved to November
either. It is simply absent, as if the field were never looked at. This is a different failure from
the one S4-04 was written against (silent wrong resolution); it is a coverage miss on a value that
is large, unrotated relative to the rest of the skew, and printed in a clean sans-serif font at the
top of the form.

**The name, answered directly:** `J&Y WORLD HARDWARE SDN BHD` is **not returned in any form** -
not the correct punctuated string, and not `JAY`. It is simply absent, alongside the debtor code,
the RMA number, the issuer and the agent. The prompt rule this AC exists to test (rule 1, transcribe
exactly as printed) cannot be scored as pass or fail here, because the field was never attempted.
This is the most important finding of the run: on the harder, more realistic photo, the model
extracted **the table and nothing from the header block** - it is not that it degraded the header
values, it dropped the entire top third of the document.

**Plausible-but-wrong count for image 02: 1 strict value error** (the misread printed quantity,
`16` vs `6`), **plus a systemic confidence-flag defect touching 4 more fields** (lines 1/3/4/5
quantities wrongly marked unconfident) that is a code bug rather than a vision error - counted
separately because it is not "wrong data," it is "correct data with a wrong trust signal," which
still matters because S4-03's whole point is that `confident: false` must be trustworthy.

---

## Image 03 - carton label (angled phone photo, warehouse)

`image_kind` returned: `label` (correct).

| field | ground truth | extracted | bucket |
|---|---|---|---|
| Model | `SRTKS6647` | entity, confident | exact match |
| Product size (Trap E) | `750X470X250MM` | attribute `product_size`=`750X470X250MM`, confident | exact match |
| Qty | `1 PC` | attribute `quantity`=`1 PC`, confident | exact match |
| Box dimension (Trap E) | `820X540X310MM` | attribute `box_dimension`=`820X540X310MM`, confident | exact match |
| Batch (Trap E) | `YG2539` | attribute `batch_number`=`YG2539`, confident | exact match |
| Barcode (Trap E) | `9551028470852` | not present | refused-or-absent |

I opened the image directly (not just the README's claim) to check whether the barcode digits are
actually legible in this specific photo before scoring the miss: they are - `9551028470852` is
printed cleanly under the bars, unrotated, in the bottom right of the label, at a size comparable
to the other fields the model did read. This is a genuine miss on a legible value, not a case where
the ground truth overclaims legibility.

**Trap E, answered directly:** yes - `750X470X250MM` (product size) and `820X540X310MM` (box
dimension) are both present, under their own distinct attribute kinds, with no merging and no
mislabeling either way. Batch `YG2539` is correctly captured as a `batch_number` attribute. The
barcode is the one field of the six the label carries that did not come through at all.

**Plausible-but-wrong count for image 03: 0.** Every value that came back is correct; the only
failure is an omission of a legible field (`refused-or-absent`), which per the task brief is the
cheaper failure mode of the two.

---

## Timing and token cost, per image (PLAN section 8)

One provider call per image, `temperature=0.0`, `response_format=json_object`, `gpt-4o-mini`.

| image | wall time | prompt tokens | completion tokens |
|---|---|---|---|
| 01 (delivery order, 805x421, clean) | 5.52s | 15,508 | 302 |
| 02 (RMA photo, 740x1080, skewed/stamped) | 6.16s | 38,176 | 451 |
| 03 (carton label, 1280x720, angled) | 4.22s | 38,176 | 216 |

The prompt token count for images 02 and 03 is identical (38,176) despite different content and
resolution - both land in the same vision-tokenization tile bucket for `gpt-4o-mini`; image 01's
smaller/lower-resolution screenshot lands in a smaller bucket (15,508). This is consistent with
known OpenAI image-tokenization behaviour (tiled, resolution-bucketed), not a bug in this code.
These three numbers are what section 1.1's "extraction, typical: 5.8-9.8s" budget line and section
8's "worst-case end-to-end call" arithmetic should be checked against for this run; they are lower
than the range quoted from the prior experiment, but this is three single data points, not a
distribution, and should not be read as a tighter guarantee.

---

## Did anything land in `entities` under an approximate hint that should have been an `attribute`?

No. Every value the model put in `entities` across all three images carries a hint from the real
14-value enum, and no batch number / barcode / dimension / quantity value was ever put in
`entities` - the entity/attribute split held in both directions the prompt asks for.

The defect that did surface runs the other way and is not what this question asked, but is close
enough to be worth restating here: a genuine **entity** value (`ACC-SRT1011`, a product code)
reappeared as a spurious **attribute** under a wrong kind (`batch_number`) on image 01. That is a
duplication-and-mislabeling failure, not an entity/attribute-boundary failure - the code-level
enforcement in `schema.py::_parse_entities` (which rescues an entity mis-hinted as an attribute
kind) has nothing to catch this, because the model emitted it as a *new* attribute from scratch
rather than mis-hinting the existing entity.

---

## Summary: plausible-but-wrong count

| image | plausible-but-wrong (strict value errors) | notes |
|---|---|---|
| 01 | 1 | duplicate/mislabeled `ACC-SRT1011` as `batch_number` |
| 02 | 1 | printed quantity misread as `16` instead of `6`, inside an otherwise-correct conflict |
| 03 | 0 | one legible field (barcode) omitted, not misread |
| **total** | **2** | plus 1 systemic confidence-flag bug touching 4 further fields on image 02 (code defect, not a vision error) |

Refused-or-absent count is much larger, concentrated entirely on image 02's header block (debtor
code, customer name, RMA number, date, issued-by, agent - six fields, zero extracted).

---

## Honest verdict

**What works, and is verified against real photos for the first time:** the two loudest traps the
prompt was written against both hold. Trap A (subject-code discrimination among five codes on one
line) and Trap B (`#N/A` is not a line item) both pass on the real document. Trap C's core
mechanism - detecting a printed-versus-handwritten disagreement and refusing to silently pick one -
also holds: the conflict is raised, both sources are named, and the entity is correctly marked
`confident: false`. Trap E (product size vs. box dimension) passes cleanly with both dimensions
captured under the correct, distinct kinds, which is the strongest result of the run and confirms
the label lane transfers to a real angled warehouse photo, not just a mocked one.

**What still gets it wrong, named plainly:**

1. **The printed value inside a correctly-detected conflict can itself be misread.** Catching the
   disagreement is not the same as reading either side of it correctly. On image 02 the model
   invented a `16` where the document prints `6`. A consumer of this data that trusts
   `conflicts[].values[].value` for the "printed" side would be told the wrong number even though
   the system did exactly what S4-03 asked of it structurally.
2. **A code-level bug over-applies conflict-confidence.** `_apply_conflicts` matches on `kind`
   alone with no per-line link, so one real quantity conflict marked four unrelated, correct
   quantities as untrustworthy on the same document. `MediaAttribute` has no `entity_raw`, unlike
   `MediaConflict`, so there is no way to fix this without a schema change; it is a real gap, not
   a prompt-tuning problem, and it will reproduce on any multi-line document with more than one
   attribute sharing a `kind`.
3. **The harder photo drops the whole header block rather than degrading it.** On image 02, none
   of debtor code, customer name, RMA number, issue date, issuer or agent came through - not
   wrongly, not partially, just absent. This means the two AC-named judgement rules for this image
   (S4-04's ambiguous-date handling, S4-05's punctuation-preserving name transcription) were never
   actually exercised on this run, because the fields they govern were never attempted. This is a
   materially different failure from the one those rules were written to fix (silent wrong
   resolution / silent normalisation) - it is a coverage regression on a skewed, stamped,
   handwritten-on photo relative to the clean screenshot, and it means the specific baseline defects
   named in the plan (`J&Y` -> `JAY`, `11/08/2026` -> November) are unverified rather than fixed on
   this corpus, because there was nothing to compare against.
4. **A legible, in-scope field on the carton label (the barcode) is silently omitted**, not
   misread - the cheaper failure mode per the task's own framing, but still a real gap against the
   ground truth's six-field expectation, and against prompt rule 13's instruction to report it when
   the digits are printed beside the bars.
5. **Unambiguous dates have no home in the output schema at all.** `13/08/2026` on image 01 (not
   ambiguous - day is 13) is dropped, not because it was misread, but because neither an entity hint
   nor an attribute kind exists for a bare date. This looks identical to a miss from the output side
   and is worth a schema decision (a `date` attribute kind, or accept the gap) rather than being
   mistaken for evidence the extraction "worked" on image 01 just because its two named traps
   passed.

**Do not read this run as "the prompt works."** It has one clean pass (image 01, mostly - modulo the
duplicate batch number and the dropped date) and one image, image 03, that is a genuinely strong
result on the previously-unverified label lane. Image 02, the photographed/skewed/stamped/
handwritten document - the one closest to what a dealer on WhatsApp actually sends per the
corpus's own Trap F framing - is the weakest result: correct on every line-item code and quantity
value bar one misread digit, and blank on the entire header. That header is exactly where a
customer's identity and a document's own reference number live, and a feature whose confirmation
message is meant to let the dealer say "is that what I meant?" cannot ask about fields it never
attempted to read.
