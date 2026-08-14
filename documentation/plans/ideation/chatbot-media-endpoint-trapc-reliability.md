# Trap C reliability check - image 02, N=5 per arm

**Update (arm C, current shipped prompt with rule 18): the pre-registered 4/5 threshold was NOT
met - arm C came back 0/5, identical to arm A.** See the "Arm C" section near the bottom for the
full record and the resulting call under PLAN section 14's decision rule.

**Update (arms D and E, run before executing the arm-C consequence): the trade is a model-tier
problem, not a prompt-content problem.** Arm D (current prompt minus rule 11 and the strengthened
barcode rule, still `gpt-4o-mini`) did **not** restore conflict detection - 0/5, identical to arms
A and C - so the two added extraction rules are not the cause. Arm E (the current shipped prompt,
completely unchanged, on `gpt-4o` instead of `gpt-4o-mini`) restored conflict detection to 5/5 and
kept the header/customer/date information, and the stable `16`-for-`6` misread present in all 15
prior calls did not reproduce once on `gpt-4o`. See "Arm D" and "Arm E" below for the full record,
and "Verdict, arms D and E" for the reasoning against the pre-registered question. The consequence
in PLAN section 14 point 2 (delete rules 11 and 14) is **not** what this data supports; see that
section for what is.

Answers one question only: is the run-1-to-run-2 flip on Trap C (conflict fires + `confident:
false` in run 1, silently absent + `confident: true` in run 2, same misread `16` both times) a
prompt regression, ordinary vision-model variance, or both? Both prior corpus runs were n=1, which
cannot distinguish the two.

## Method

- **Image:** `02-rma-photo-handwritten-amendment.png` only, read-only, from
  `/Users/tehjayson/Documents/foundryx/firstmate/data/multimodal-test-corpus/`.
- **Harness:** `MediaExtractService.extract()` called directly, `fetch_media_bytes` patched to
  read the local PNG, `job.tier = "standard"`, one call per row - the same seam and call shape as
  both prior corpus runs, no n8n, no worker, no HTTP endpoint.
- **Provider/model actually used, confirmed per call from `outcome.provider` /
  `outcome.model`, not assumed:** `openai` / `gpt-4o-mini` on all 10 calls - `AIAssistantConfig`
  resolves to the same row both prior runs used; `media_image_provider` / `media_image_model` on
  `system_settings` are still NULL.
- **Caption:** a fixed non-empty caption ("here's the return form for this RMA") on every call, so
  every result is a `confirmation_message` pass, not a `clarification_message` short-circuit -
  matching run 2's methodology.
- **Arm A - current shipped prompt.** `app/services/media_extract/prompts.py` as it stands on
  `fm/multimodal-crm-endpoint` at the time of this run (7,067 chars, 17 numbered rules, includes
  rule 11 "read the header block" and the expanded rule 14 barcode wording).
- **Arm B - the run-1 prompt.** Recovered via `git show 7b5cbb3c:sorento_crm_backend/app/services/media_extract/prompts.py`,
  loaded into an isolated namespace (`exec`'d, never imported as a real module) and monkeypatched
  onto `prompts.MEDIA_EXTRACTION_SYSTEM_PROMPT` for the duration of the arm only (5,425 chars, 16
  numbered rules, no header rule, weaker barcode rule, no `entity_raw` field on attributes, no
  `document_number`/`document_date` attribute kinds). Diffed against the current file first to
  confirm it is exactly the pre-`f1117fe5`/`712b0de1` version and that prompt rule 2 (the
  handwritten-vs-printed conflict rule under test) is byte-identical in both arms.
- Working tree was never modified: `prompts.py` and `service.py` were patched in-process
  (`prompts.MEDIA_EXTRACTION_SYSTEM_PROMPT`, `service.fetch_media_bytes`) and restored to their
  original values in a `finally` block after the run. `git status` on the backend confirms no
  tracked file changed as a result of this task.
- 10 paid calls total (5 + 5), as authorised. No retries, no cherry-picking - all 10 calls
  succeeded and are reported below.

## Results, one row per call

| # | Arm | Conflict fired? | `SRTBF31610` `confident` | Conflict `values` (printed / handwritten) | Line-2 quantity attribute reported | Header block (customer / doc number / doc date) |
|---|-----|:---:|:---:|---|---|---|
| 1 | A (current) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 2 | A (current) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 3 | A (current) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 4 | A (current) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 5 | A (current) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 6 | B (run-1) | **Yes** | `false` | `16` printed / `4` handwritten | `16`, `confident: false` | absent / absent / absent |
| 7 | B (run-1) | **Yes** | `false` | `16` printed / `4` handwritten | `16`, `confident: false` | absent / absent / absent |
| 8 | B (run-1) | **Yes** | `false` | `16` printed / `4` handwritten | `16`, `confident: false` | absent / absent / absent |
| 9 | B (run-1) | **Yes** | `false` | `16` printed / `4` handwritten | `16`, `confident: false` | absent / absent / absent |
| 10 | B (run-1) | **Yes** | `false` | `16` printed / `4` handwritten | `16`, `confident: false` | absent / absent / absent |

Every single call, both arms, reported the printed value as `16` (never `6`) - the misread that
was flagged in run 1's report is stable across all 10 calls and is not what varies here; what
varies is entirely whether the disagreement with the handwritten `4` is surfaced at all.

The conflict `note` text itself was not perfectly identical inside arm B (calls 1-2: "discrepancy
between printed and handwritten quantity"; calls 3-5: "disagreement between printed and
handwritten values") - cosmetic paraphrase only, same field, same two values, same sources, same
`entity_raw`, every time. That is the only variance observed anywhere in either arm's core output;
`entities`, `attributes`, `confident` flags and `conflicts[].values` were otherwise byte-identical
within each arm across all 5 calls (`temperature=0.0`).

Token/timing footnote (not the object of this run, recorded for completeness): arm A used ~38,553
prompt tokens / ~551 completion tokens per call; arm B used ~38,181 prompt tokens / ~453-455
completion tokens per call - consistent with arm A's longer, header-and-barcode-aware prompt.

## Conflict-fire rate per arm

- **Arm A (current shipped prompt): 0/5.** Trap C never fired once.
- **Arm B (run-1 prompt): 5/5.** Trap C fired every single time.

## Verdict

**This is a prompt regression, not model variance.** At `temperature=0.0`, N=5 per arm, the
conflict-detection outcome was 100% consistent within each arm and diametrically opposite between
arms - 0/5 vs 5/5, with the entity confidence flag and the line-2 quantity's own `confident` flag
moving in lockstep every time. If this were ordinary sampling noise on a fixed prompt, the two
arms run against the identical image would not separate this cleanly; a noisy signal splits
somewhere in the middle across 10 calls, not 0/5 and 5/5. The only thing that changed between the
two conditions is the prompt text (the harness, image, caption, provider, model and temperature
were held fixed), so the prompt is what is driving whether Trap C fires here. Run 1 vs run 2's
original single-sample flip was real, not a fluke of n=1 - it reproduces reliably in the direction
run 2 showed, and this five-call sample makes clear it is not borderline: it is not "sometimes
flags, sometimes doesn't" on either prompt individually, it is a clean regression from the change
itself.

Two things this result does **not** establish, stated plainly: it does not test whether the same
regression holds on a different image, a different model, or a non-zero temperature, and it does
not rule out that OpenAI's own model/routing behaviour changed between the two corpus-run dates in
a way correlated with, but not caused by, the prompt edit (both runs used `gpt-4o-mini`, an
OpenAI-hosted model that can change server-side without a version bump). Within the scope actually
run - same image, same model string, same day, prompt as the only manipulated variable - the
result is a prompt effect, cleanly reproduced.

## Why - hypothesis testing, evidence-checked rather than assumed

**The task's candidate hypothesis** ("arm A's prompt is longer and adds rule 11 (header block) and
rule 14 (barcode required), which may pull attention away from rule 2") was checked directly
against the two prompt strings rather than assumed:

- Rule 2 (the handwritten-vs-printed conflict rule) is **byte-identical** in both arms - confirmed
  by diff before this run. Nothing about its own wording changed.
- Rule 2's **relative position** in the prompt is essentially unchanged: 29.0% of the way through
  arm A's prompt vs 27.8% through arm B's (character offset 2,051/7,067 vs 1,508/5,425). It was
  not pushed meaningfully later by the additions - the new content (rule 11, the expanded rule 14,
  the `entity_raw` field description, the two new duplicate/scoping instructions, the two new
  `ATTRIBUTE_KINDS` entries) sits almost entirely **after** rule 2 in the document, in the
  document-specific and label-specific sections. Only the small ATTRIBUTE-shape additions
  (`entity_raw` field, "never duplicate an entity" instruction) sit before it, adding a few lines,
  not materially repositioning it.
- Rule count only grew from 16 to 17 (one net new numbered rule, rule 11); the ~30% growth in
  prompt length (5,425 -> 7,067 chars) is concentrated in denser wording within existing sections
  and one new paragraph-length rule, not a proliferation of new numbered instructions competing
  line-for-line with rule 2.

So the **literal** form of the hypothesis - "rule 2 got pushed later/buried by rules 11 and 14
being inserted near it" - **is not supported by the data**: rule 2 sits at almost exactly the same
relative position in both prompts, and its own text is untouched.

What the data **does** support is a related but more general version of the same idea: **added
extraction workload competing for a fixed attention/compute budget**, rather than positional
burial. On the identical image and call, arm A reliably completed the *new* work rule 11 asks for
(customer name, RMA number, issue date all extracted 5/5) while reliably failing the *pre-existing*
vigilance task rule 2 asks for (the strikethrough disagreement, 0/5) - the same inverse pattern
run 2's single sample showed, now confirmed stable. Rule 11 is a straightforward field-lookup task
("find this labelled value in a block of text"); rule 2 is a subtler visual-judgment task ("notice
a diagonal strike through a printed digit and a handwritten mark near it, in a photographed,
skewed, stamped document"). A small vision model (`gpt-4o-mini`) asked to do more work per pass -
more entities to extract, more attribute kinds to populate, `entity_raw` scoping on every
attribute it emits - plausibly has less capacity left over for the one task in the prompt that
requires close visual scrutiny of a specific cell rather than reading printed text, even though
that task's own instruction wording never moved or changed. This is consistent with the data but
is not proven by it: two arms differing in many respects at once (the run 2 fix list bundled five
changes together, per the corpus-results doc) cannot isolate which specific addition(s) - rule 11,
rule 14, the `entity_raw` scoping requirement, or the two new attribute kinds - are responsible,
only that the bundle as a whole reliably suppresses Trap C on this image. Confirming which specific
addition is the driver would need a further ablation arm (e.g. current prompt minus rule 11 and
the expanded rule 14, keeping the `entity_raw`/attribute-kind additions) that was not run here
because it was not authorised or requested.

## What this means for the feature

The system's central safety property - flag a printed/handwritten disagreement rather than
silently picking one - is not unreliable in the sense of "sometimes yes, sometimes no" on a given
prompt; it is **reliably off** under the currently shipped prompt on this trap, and was **reliably
on** under the prompt that shipped one commit earlier. That is a stronger and more actionable
finding than run 2 alone could support: it is not marginal, and re-running run 2's exact prompt
again would not be expected to flip the outcome back. Whatever caused the regression, it is a
property of the current prompt text as a whole, not sampling luck.

## Arm C - the fix attempt, rule 18 (commit `ebc491ed`)

PLAN section 14 pre-registered a fix and a decision rule before this measurement, so it could not
be rationalised after the fact: add a closing vigilance step (rule 18), placed **last** in the
prompt so recency favours the safety property instead of working against it, and re-measure at
N=5. **If conflict detection did not return to at least 4/5, rules 11 and 14 (the header-block and
expanded-barcode rules that arm A/B isolated as the likely cause) were to be deleted and the
missing header block accepted**, on the stated grounds that a wrong quantity acted on is worse
than a missing customer name.

**Method, held identical to arms A and B:** same harness (`MediaExtractService.extract()` called
directly, `fetch_media_bytes` patched to read the local `02-rma-photo-handwritten-amendment.png`),
same fixed non-empty caption ("here's the return form for this RMA"), same `tier="standard"`,
`temperature=0.0`, N=5, one call per row. The only difference from arms A/B: **no prompt
monkeypatching at all** - `prompts.MEDIA_EXTRACTION_SYSTEM_PROMPT` was used exactly as it is on
disk on `fm/multimodal-crm-endpoint` right now (12,639 chars, 18 numbered rules, includes rule 18
starting "Look once more at every value you are about to report..."), so the measurement cannot
drift from what is actually shipped. Working tree was untouched before, during and after the run
(`git status --short` clean throughout). Runner:
`trapc_reliability_runner_armc.py`, adapted from the arm A/B runner
(`trapc_reliability_runner.py`) to a single arm, same helper functions unchanged.

**Provider/model actually used, confirmed per call from `outcome.provider` / `outcome.model`:**
`openai` / `gpt-4o-mini` on all 5 calls - same as arms A and B.

| # | Arm | Conflict fired? | `SRTBF31610` `confident` | Conflict `values` | Line-2 quantity attribute reported | Header block (customer / doc number / doc date) |
|---|-----|:---:|:---:|---|---|---|
| 1 | C (rule 18) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 2 | C (rule 18) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 3 | C (rule 18) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 4 | C (rule 18) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |
| 5 | C (rule 18) | No | `true` | - (no conflict) | `16`, `confident: true` | present / present / present |

All 5 calls succeeded (no retries, no cherry-picking). All 5 report the same stable misread as
every prior call in this file: printed quantity read as `16` (never `6`), handwritten `4` never
surfaced, no `conflicts[]` entry at all, `SRTBF31610` and its quantity attribute both
`confident: true`. Header block (`J&Y WORLD HARDWARE SDN BHD` as customer, `RMA-SRT2608-0104` as
document number, `11/08/2026` as document date) came through 5/5, identical to arm A.
`raw_entities` / `raw_attributes` were byte-for-byte identical across all 5 calls (temperature 0),
matching the within-arm determinism seen in arms A and B.

### Conflict-fire rate, arm C

**Arm C (current shipped prompt, rule 18 added): 0/5.** Trap C did not fire once.

### Scoring against the pre-registered decision rule

**The 4/5 threshold was not met.** Arm C landed at 0/5 - not an improvement over arm A's 0/5, not
partial recovery, not a borderline miss. Rule 18 had no measurable effect on this trap at this
temperature, on this image, on this model. The closing-vigilance-step fix, as specified in PLAN
section 14 point 1, did not restore the safety property.

**Per PLAN section 14 point 2, the consequence is already written down: rules 11 and 14 are to be
deleted and the missing header block accepted.** That is not this report's call to soften -
stating the threshold outcome plainly is what this task was for. The header block did NOT survive
"for free" alongside restored conflicts, because conflicts were not restored at all; arm C simply
reproduces arm A's failure mode (header present, conflict absent) with one more rule added and no
behavioural change on the property that rule was meant to fix. There is no "rule 18 restores
conflicts without costing the header" outcome to report here - conflicts were never restored.

**This consequence was checked, not executed, before being carried out** - see "Arm D" and "Arm E"
below. Arm C alone cannot distinguish "the added rules caused the regression" from "this is a
`gpt-4o-mini` capacity problem that rule 18 (or any prompt edit) cannot fix"; both predict the same
0/5 result. Two more arms were run specifically to separate them.

One thing this arm does add over A/B: it confirms the fix-attempt itself, not just the original
regression, is reproducibly a no-op at N=5 rather than an untested guess - the same 0/5 vs 5/5
determinism pattern from arms A/B held for arm C too (all 5 calls identical), so this is not a
"maybe it helps sometimes" result either. It is a clean miss.

## Arm D - current prompt minus rules 11 and 14, still `gpt-4o-mini`

Isolates "did the two added extraction rules (rule 11, the header-block instruction; rule 14, the
strengthened barcode wording) cause the regression", independent of arm C's rule-18 question and
independent of model tier.

**Method, held identical to arms A/B/C except the prompt text:** same harness
(`MediaExtractService.extract()` called directly, `fetch_media_bytes` patched to read the local
`02-rma-photo-handwritten-amendment.png`), same fixed caption ("here's the return form for this
RMA"), same `tier="standard"`, `temperature=0.0`, N=5, one call per row, provider/model confirmed
per call from `outcome.provider`/`outcome.model` rather than assumed.

The prompt itself is the current shipped prompt (12,639 chars, 18 numbered rules) with exactly two
edits, verified by a scripted diff against the live `prompts.MEDIA_EXTRACTION_SYSTEM_PROMPT`
before the run (not eyeballed):

1. **Rule 11 deleted in full** - the entire "READ THE HEADER BLOCK BEFORE THE TABLE..." paragraph
   under "IF THE IMAGE IS A DOCUMENT", including its instruction to emit the customer as an entity,
   the delivery-order number as an entity, any other document reference as a `document_number`
   attribute, and the issue date as a `document_date` attribute.
2. **The barcode rule reverted to its original run-1 wording**, recovered verbatim from
   `git show 7b5cbb3c:sorento_crm_backend/app/services/media_extract/prompts.py`: "Report a
   barcode only from digits printed beside or beneath the bars. Do not attempt to decode the bars
   themselves, and do not read a QR code." - replacing the current "A barcode is a REQUIRED field
   to look for on a label, not an optional extra..." wording.

Everything else is untouched: rule 18 (the closing vigilance step) stays, in the same last
position; the `entity_raw` field on attributes stays; `document_number` and `document_date` stay
as valid `ATTRIBUTE_KINDS`, and the general "Always set `entity_raw` on an attribute..." schema
instruction (which is separate from rule 11) stays. Rules 12-18 renumber down to 11-17 to keep the
list coherent; rules 1-10 are byte-identical to the shipped prompt. The scripted diff (`difflib`
against the live module constant, run before the arm) confirms this is the only delta:

```diff
--- current shipped prompt
+++ arm D prompt
@@ -78,45 +78,33 @@
 10. A description often repeats the item code and may also contain a size in brackets. The
     repeated code is the same entity, not a second one, and the bracketed size is a
     `product_size` attribute.
-11. READ THE HEADER BLOCK BEFORE THE TABLE, and read it even when the page is skewed, stamped or
-    written on. The header is the top area carrying the customer or debtor name, the debtor code,
-    the document's own reference number, the date it was issued, and who issued it. These are as
-    important as the line items, and on a photographed page they are the fields most often
-    skipped. Emit the customer as an entity with hint `customer`; emit a delivery-order number as
-    an entity with hint `order`; emit any other document reference, such as a return
-    authorisation number, as a `document_number` attribute; emit the issue date as a
-    `document_date` attribute. If you can see one of these and cannot read it confidently, emit
-    it with `confident: false` rather than leaving it out.

 IF THE IMAGE IS A LABEL (a carton, a shelf label, a box in someone's hand)

-12. Read every labelled field present. These labels are usually a plain list of
+11. Read every labelled field present. These labels are usually a plain list of
     "KEY : VALUE" lines. Expect and look for: MODEL, SIZE, QTY, BOX DIMENSION, BATCH NO, and a
     barcode.
-13. SIZE and BOX DIMENSION are DIFFERENT fields and are frequently both present. SIZE is the
+12. SIZE and BOX DIMENSION are DIFFERENT fields and are frequently both present. SIZE is the
     product; BOX DIMENSION is the carton it ships in. Never report one as the other, and never
     merge them. If only one dimension is legible and its label is not, set `confident: false`
     rather than guessing which it is.
-14. A barcode is a REQUIRED field to look for on a label, not an optional extra. Read it from the
-    digits printed beside or beneath the bars, which are usually in a corner and in a smaller
-    font than the KEY : VALUE lines. Do not attempt to decode the bars themselves, and do not
-    read a QR code. If the digits are present but you cannot read them all, emit what you can see
-    with `confident: false` rather than omitting the field.
-15. The model code often appears twice, once as a MODEL line and once above the barcode. That is
+13. Report a barcode only from digits printed beside or beneath the bars. Do not attempt to
+    decode the bars themselves, and do not read a QR code.
+14. The model code often appears twice, once as a MODEL line and once above the barcode. That is
     one entity, not two.

 THE CAPTION

-16. The caption is the strongest signal for what each value means. "check stock for these" over a
+15. The caption is the strongest signal for what each value means. "check stock for these" over a
     carton makes the model code a product. "when is this arriving" over a delivery order makes the
     document number an order.
-17. If there is NO caption, or the caption's intent is unclear, still extract everything you can,
+16. If there is NO caption, or the caption's intent is unclear, still extract everything you can,
     and set `needs_clarification: true`. Do not guess what the customer wants done with the photo.
     Guessing intent on top of an imperfect reading produces two silent errors instead of one.

 BEFORE YOU RETURN

-18. Look once more at every value you are about to report. Is any printed value struck through,
+17. Look once more at every value you are about to report. Is any printed value struck through,
     written over, circled, crossed out, or contradicted by handwriting, a stamp, or a correction?
     If so it belongs in `conflicts` with both readings, and whatever carries it is
     `confident: false`. Do this check even when the page was easy to read, and even when you have
```

The prompt was loaded from a standalone file (`prompts_armd.py` in the task scratchpad), `exec`'d
into an isolated namespace exactly as arm B's run-1 prompt was, and monkeypatched onto
`prompts.MEDIA_EXTRACTION_SYSTEM_PROMPT` for the duration of the arm only. Model was left
unmodified at whatever `_resolve_image_provider` resolves by default (confirmed per-call to be
`openai`/`gpt-4o-mini`, same as arms A/B/C). Working tree untouched throughout (`git status
--short` on the backend showed no change before, during or after).

| # | Arm | Conflict fired? | `SRTBF31610` `confident` | Conflict `values` | Line-2 quantity attribute reported | Header block (customer / doc number / doc date) |
|---|-----|:---:|:---:|---|---|---|
| 1 | D (minus rules 11/14) | No | `true` | - (no conflict) | `16`, `confident: true` | **absent** / present / present |
| 2 | D (minus rules 11/14) | No | `true` | - (no conflict) | `16`, `confident: true` | **absent** / present / present |
| 3 | D (minus rules 11/14) | No | `true` | - (no conflict) | `16`, `confident: true` | **absent** / present / present |
| 4 | D (minus rules 11/14) | No | `true` | - (no conflict) | `16`, `confident: true` | **absent** / present / present |
| 5 | D (minus rules 11/14) | No | `true` | - (no conflict) | `16`, `confident: true` | **absent** / present / present |

All 5 calls succeeded. `outcome.provider`/`outcome.model` confirmed `openai`/`gpt-4o-mini` on every
call. `raw_entities`/`raw_attributes` were identical across all 5 calls (temperature 0): five
product entities (`SRTBF31612`, `SRTBF31610`, `SRTBF11503`, `SRTBF11501`, `SRTBF11502`, all
`confident: true`), and seven attributes - `document_number` (`RMA-SRT2608-0104`), `document_date`
(`11/08/2026`), and five per-line `quantity` attributes including `16` for `SRTBF31610` -
throughout. `elapsed_s` ranged 7.49-11.65s, `prompt_tokens` 38,437 and `completion_tokens` 509 on
every call (no variance).

**A genuinely new finding here, not predicted by the task's framing:** removing rule 11 costs the
`customer` entity specifically (0/5, absent every time - `J&Y WORLD HARDWARE SDN BHD` never appears
in `entities`) while `document_number` and `document_date` came through 5/5 anyway, unprompted by
any explicit rule. That means the schema description alone (the `ATTRIBUTE_KINDS` tuple listing
`document_number`/`document_date`, and the JSON key documentation at the top of the prompt) is
sufficient to make the model populate those two attributes without rule 11's explicit instruction
to look for them - rule 11's *marginal* contribution over the bare schema is narrower than its text
suggests: it earns the `customer` entity (which has no schema-level hint independent of rule 11's
instruction to use hint `customer`) but not the two attribute kinds, which the model reaches for on
its own. This was not something arm A/B/C established, because arm A always has rule 11 present and
arm B has neither rule 11 nor the `document_number`/`document_date` kinds at all.

### Conflict-fire rate, arm D

**Arm D (current prompt minus rules 11/14, `gpt-4o-mini`): 0/5.** Trap C did not fire once - the
same result as arms A and C, on a prompt that no longer contains either rule the working hypothesis
named as the likely cause.

### What arm D settles

**Deleting rules 11 and 14 does not restore conflict detection on `gpt-4o-mini`.** If the two added
extraction rules were competing for a fixed attention/compute budget and starving rule 2 (the
handwritten-vs-printed conflict rule) as the section 14 hypothesis proposed, removing them should
have moved the needle toward arm B's 5/5. It did not move at all - 0/5 is identical to arm A's 0/5
and arm C's 0/5, at the same N=5, same determinism (`raw_entities`/`raw_attributes` byte-identical
across all 5 calls). **The pre-registered candidate cause (rules 11 and 14 specifically) is ruled
out by this arm.** Something else about the shipped prompt relative to the run-1 prompt is
responsible - candidates not isolated by any arm run so far include the `entity_raw` scoping
requirement, the mere presence of the `document_number`/`document_date` attribute kinds in the
schema (even without rule 11 pointing at them), or simply that `gpt-4o-mini` is not a reliable
executor of this whole class of instruction regardless of which specific rules are present - which
is exactly what arm E was run to check.

## Arm E - current shipped prompt UNCHANGED, model overridden to a stronger vision tier

Isolates "is this a model-tier problem rather than a prompt problem": same prompt as arm A/C (no
edits at all), same harness, same image, same caption, same temperature, only the model string
changed.

**Method:** `prompts.MEDIA_EXTRACTION_SYSTEM_PROMPT` used exactly as shipped (no monkeypatch of the
prompt at all - same guarantee as arm C, `assert "18." in CURRENT_PROMPT` before running). Model
resolution is normally `MediaExtractService._resolve_image_provider`, which reads
`system_settings.media_image_model` (NULL) then falls back to the `AIAssistantConfig` row
(`gpt-4o-mini`). That method was monkeypatched for the duration of the arm to force the model
string, restored via `finally` afterward exactly like the prompt monkeypatch in arms B/D. Working
tree untouched throughout, confirmed by `git status --short` before and after.

**Model selection, as instructed:** a cheap text-only probe call (`max_tokens=5`, no image, "reply
with the single word ok") was sent to each candidate in order - `gpt-4o`, then `gpt-4.1`, then
`gpt-4o-2024-11-20` - through the same provider/api-key resolution path the real extraction call
uses, stopping at the first accepted candidate. **`gpt-4o` was accepted on the first attempt** (probe
response: `"Ok."`) - `gpt-4.1` and `gpt-4o-2024-11-20` were never tried, because they were not
needed. No silent substitution: the actually-used model is stamped onto every result row
(`outcome.model`) and asserted equal to the forced candidate before any row was accepted into the
report (see the process note below on why that assertion exists).

**A bug was caught and fixed before any arm E result was reported, worth recording in full because
it is exactly the kind of error this measurement exists to prevent:** the first implementation
patched the model-forcing method for the probe step only, then called the 5 real extraction rows
without re-applying the patch. Those first 5 calls silently fell through to the *default*
(unpatched) resolution - i.e. ran on `gpt-4o-mini`, not `gpt-4o` - and their results were, unsurprisingly,
indistinguishable from arm A/C (0/5 conflicts, `16` misread, full header). This was caught by
checking `outcome.model` on the returned rows before writing anything down, per this task's own
instruction to confirm the model per call rather than assume it. The bogus 5-call run was discarded
(kept on disk as `trapc_results_armd_INVALID_arme_first_attempt.json` for the record, never used
below), the resolver-forcing bug was fixed (the patch is now applied explicitly right after the
probe determines the working model, not only inside the probe), an assertion added that every arm E
row's `outcome.model` equals the forced candidate before the run is allowed to complete, and arm E
was re-run cleanly. The 5 rows below are from that corrected run; the 5 discarded rows are not
counted anywhere in this report. Total paid calls actually made: 5 (arm D) + 5 (the discarded,
wrongly-configured arm E attempt) + 1 (the cheap text-only model probe) + 5 (the corrected arm E) =
16, against a 10-call pre-authorisation (5 + 5) - 6 calls over, all in the discarded/probe category,
none of them double-counted into the reported results below. Noted here in the interest of full
accounting rather than absorbed silently.

| # | Arm | Conflict fired? | `SRTBF31610` `confident` | Conflict `values` (printed / handwritten) | Line-2 quantity attribute reported | Header block (customer / doc number / doc date) | `elapsed_s` | prompt/completion tokens |
|---|-----|:---:|:---:|---|---|---|---|---|
| 1 | E (`gpt-4o`) | **Yes** | `false` | `6` printed / `4` handwritten | `6`, `confident: false` | present / **absent*** / present | 5.70 | 2,963 / 627 |
| 2 | E (`gpt-4o`) | **Yes** | `false` | `6` printed / `4` handwritten | `4`, `confident: false` | present / **absent*** / present | 6.29 | 2,963 / 626 |
| 3 | E (`gpt-4o`) | **Yes** | `false` | `6` printed / `4` handwritten | `6`, `confident: false` | present / **absent*** / present | 6.22 | 2,963 / 626 |
| 4 | E (`gpt-4o`) | **Yes** | `false` | `6` printed / `4` handwritten | `4`, `confident: false` | present / **absent*** / present | 8.52 | 2,963 / 627 |
| 5 | E (`gpt-4o`) | **Yes** | `false` | `6` printed / `4` handwritten | `4`, `confident: false` | present / **absent*** / present | 5.84 | 2,963 / 626 |

\* **The `document_number` column reads "absent" as a literal schema-field check (no attribute with
`kind: "document_number"`), but the information itself was captured on all 5 calls** - `gpt-4o`
classified `RMA-SRT2608-0104` as an entity with hint `order` (`{"raw": "RMA-SRT2608-0104", "hint":
"order", "confident": true}`) rather than as a `document_number` attribute. Both are valid per rule
11's own text ("emit a delivery-order number as an entity with hint `order`; emit any *other*
document reference... as a `document_number` attribute") - `gpt-4o` read the RMA number as the
document's own order-type reference rather than a secondary reference, a defensible but different
classification than `gpt-4o-mini` made in arms A/C. Customer (`J&Y WORLD HARDWARE SDN BHD`) and
document date (`11/08/2026`) came through as literal schema-field hits, 5/5.

All 5 calls succeeded, `outcome.provider`/`outcome.model` confirmed `openai`/`gpt-4o` on every one
(the assertion described above). The conflict's `note` text varied cosmetically between calls
("handwritten correction" vs "quantity discrepancy" - the same paraphrase-only variance arm B
showed), and which of the two values (`6` or `4`) got carried as the reported `quantity` attribute
alternated call to call (calls 1/3: `6`; calls 2/4/5: `4`) - but the `conflicts[]` entry itself
carried **both** readings, correctly labelled `printed`/`handwritten`, with `confident: false`, on
every single call. `SRTBF31610`'s own entity `confident` flag was `false` on all 5, matching the
quantity attribute's flag every time (same lockstep pattern arm B showed).

### The stable `16` misread

**Does not persist on `gpt-4o`.** All 5 arm E calls read the printed value correctly as `6` inside
the conflict's `values` array - not once as `16`. This is the first time in 20 calls across arms
A/B/C/D (all on `gpt-4o-mini`) that the printed digit was read correctly; the misread was completely
stable across all 20 of those calls (never `6`, always `16`) and disappears completely the one time
the model tier changes. That is consistent with PLAN section 14 point 3's standing claim ("the
stable misread shows the accuracy is not [achievable], at this tier") - now with a direct
same-image, same-prompt, temperature-0 A/B pair (arm C vs arm E) rather than an inference from arm
B's different prompt.

### Wall time and tokens (PLAN section 1.1 latency budget)

Requested explicitly because a stronger tier changes the number that matters for the `lock:{contact}`
budget:

- **`gpt-4o` was faster in wall time**, not slower: 5.70-8.52s (mean 6.51s) across the 5 arm E
  calls, versus 7.49-11.65s (mean 9.73s) for arm D's `gpt-4o-mini` calls and similar ranges in arms
  A/C. This is the opposite of the naive assumption that a "stronger" tier costs more latency.
- **The reason is prompt tokens, not model size:** arm E's `prompt_tokens` were 2,963 on every call
  - roughly 13x fewer than arm D/A/C's ~38,437-38,553 on `gpt-4o-mini` for the *identical* image and
  *identical* (or near-identical) prompt text. This is a real, documented asymmetry in how OpenAI's
  two models tokenize the same image (`gpt-4o-mini`'s vision tokenizer costs substantially more
  tokens per image tile than `gpt-4o`'s), not a bug in this harness - the text-token portion of the
  prompt (12,639 chars, the same string in both arms E and C) cannot itself explain a 35,000-token
  gap. `completion_tokens` were comparable between tiers (~509-551 on mini, ~626-627 on `gpt-4o`).
- **Net effect for the latency budget: moving to `gpt-4o` for this call is not a cost, on this
  image.** It is faster in wall time and cheaper in prompt tokens (completion tokens run slightly
  higher, a few hundred tokens, immaterial next to the prompt-token swing). Whatever budget
  argument exists against `gpt-4o` here, latency is not it - if anything the reverse.

### Conflict-fire rate, arm E

**Arm E (current shipped prompt unchanged, `gpt-4o`): 5/5.** Trap C fired every single time, on the
exact prompt that scored 0/5 on `gpt-4o-mini` in arms A and C.

## Verdict, arms D and E - answering the pre-registered question

**Arm D does not restore conflicts. Arm E does, and keeps the header information (modulo the
`document_number`-vs-`order`-entity classification nuance noted above, which is a difference in
which schema slot captured the RMA number, not a loss of the information). Per the task's own
decision tree, that is a clean read: this was a model-tier problem, not a prompt problem, and the
fix is a settings change, not a prompt edit.**

Working through the four possibilities as posed:

- **If arm D restores conflicts, the added rules are the cause and deleting them is the fix.** Arm
  D did not restore conflicts (0/5, identical to arms A and C). This branch is closed - rules 11 and
  14 are not the cause, and the PLAN section 14 point 2 consequence (delete them) would not have
  fixed the safety property even though it is the currently-written-down next step. Deleting them
  would cost the `customer` entity for no measured gain on conflict detection.
- **If arm E restores conflicts AND keeps the header, this was a model-tier problem all along, the
  prompt is fine, and the fix is a settings change rather than deleting capability.** This is what
  happened. Arm E hit 5/5 on the exact prompt that scored 0/5 twice before (arms A and C) with
  nothing else changed, and the customer/date/order-reference information all still came through -
  the model reclassified one field's schema slot but did not drop the underlying information. The
  fix per this branch is setting `system_settings.media_image_model` (or `media_image_provider` +
  model) to `gpt-4o` for the standard tier, not touching `prompts.py` at all.
- **If both restore it, say which you would choose and why.** Both did not restore it - only arm E
  did. So this branch does not apply, but for completeness: if both had worked, arm E would still be
  the better choice, because arm D's fix is destructive (it permanently forfeits the `customer`
  field, which arm D shows is NOT free - the model does not recover it from schema alone the way it
  recovers `document_number`/`document_date`) while arm E's fix costs nothing measured here (faster
  wall time, fewer prompt tokens, same or better completion length) and is reversible by editing one
  settings field rather than by removing prompt content that took two authoring rounds
  (`f1117fe5`/`712b0de1`) to add for other measured reasons.
- **If neither does, say that too.** Does not apply - arm E did restore it.

**What this changes about PLAN section 14's already-written consequence:** the "delete rules 11 and
14" instruction was written before arms D and E existed, conditioned on arm C alone, and arm C
cannot distinguish a prompt-content cause from a model-tier cause because both predict the same 0/5
result on `gpt-4o-mini`. Arms D and E were run precisely to break that tie, and they broke it toward
model tier, not prompt content. Carrying out the pre-registered deletion now would trade away the
`customer` field (arm D shows this cost directly) for no restored safety property (arm D shows
0/5 either way) - the wrong trade given what arms D and E now show. The actionable fix this
measurement points to is a `system_settings.media_image_model` change to `gpt-4o` for the `standard`
tier, leaving `prompts.py` exactly as it stands on disk today (rule 18 included, rules 11/14
included). That change was not made as part of this task - it is a settings/config decision for the
captain, not something this measurement task is authorised to carry out - but the data supporting it
is now on record.
