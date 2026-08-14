# Trap C reliability check - image 02, N=5 per arm

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
