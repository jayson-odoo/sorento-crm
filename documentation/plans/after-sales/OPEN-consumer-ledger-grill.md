# OPEN - Consumer Profile and Purchase Ledger: forks to grill

**Status:** GRILLED. All seven forks answered between 2026-07-29 and 07-31. The "Ungrilled, must not be
implemented" wording below this line was the state on 2026-07-26 and was left stale; corrected 2026-08-02
when S2b was about to start and the header would have blocked a slice its own contents had already
cleared. Group L and the purchase-ledger DDL are now buildable.

**S2b is NOT blocked.** The two consequences still open gate LATER slices: the fork 4 / fork 5
margin-granularity conflict is a reporting question due before **S9**, and the service-only consent
one-way door is due before **S3**. Neither changes a table S2b creates.

Seven forks. **ALL ANSWERED (2026-07-29 to 07-31).**
**Two consequences still need a decision:** the fork 4 / fork 5 margin-granularity conflict (before S9),
and confirmation that the service-only consent one-way door is understood (before S3).

**Fork 6 (consent) is a hard gate on S3**, not a later item: a portal cannot collect consumer personal data
without consent wording that matches the intended use. It blocks S3 alongside the S3-pre spike.
Fork 5 (dealer channel conflict) blocks no code but should be a stated position before the Consumer 360
page exists.

---

## 1. Is a phone number really a Consumer? — RESOLVED 2026-07-29

**Resolved: provisional profiles.** The sharper framing found while grilling: on most complaints the
consumer **never authenticates** - staff type their details into a message, so there is no verified phone
for the majority, which is exactly the population the ledger is meant to capture.

So a staff-typed phone creates a **provisional** `consumer_profile`, promoted to confirmed the first time
that phone completes an OTP login (deterministic, no human judgement). Provisional profiles are never
marketed to and are excluded from headline counts, so "we have N consumers" stays honest. Dedupe on
**E.164-normalised phone** at write time. Same phone with a conflicting name goes to a **review queue**,
never an auto-merge - `Miss Ong daughter` arriving on a phone already holding `Ong Mei Ling` is a human
call. **Merge is in scope, split is not.**

Original framing kept below.

The profile is keyed on the verified phone. That is the right auth key and possibly the wrong identity key.

Failure modes, all realistic in Malaysian housing:
- One phone, several people - a household shares a number, so two consumers merge into one profile and
  the purchase history becomes a fiction.
- One person, several phones - they change number and the history splits silently.
- The complainant is **not** the owner: a maid, a contractor, a tenant, an adult child. The maintenance
  chat already shows this (`Miss Ong daughter`, `Sanimart owner house`, `我表弟家` - "my cousin's house").

**Needs deciding:** whether a profile can be merged and split, who may do it, and what happens to
purchases and complaints attached to the losing side. If the answer is "no merge", the ledger will
accumulate wrong history and nobody will trust the reporting.

## 2. Does a purchase belong to the person or the product? — RESOLVED 2026-07-29

**Resolved: the Purchase is authoritative for warranty; the consumer link is advisory.**
`consumer_purchases.consumer_profile_id` is **nullable**. Cover resolves from the purchase alone (policy
clause 6 attaches cover to the product and its purchase date, not to a person), so a staff-reported
purchase may carry no profile at all and a house changing hands does not break the new occupant's claim.

Accepted consequence: "consumers captured" will read much lower than "purchases captured" on any
dashboard. That is honest rather than broken.

Original framing kept below.

Warranty runs from the date of purchase and attaches to the **product** (policy clause 6). But a
purchase record links to a **Consumer Profile**. Those diverge the moment a house changes hands: the new
occupant complains about a water closet bought by someone else, still inside a lifetime ceramic term.

**Needs deciding:** is the consumer link on a purchase authoritative, or advisory? If advisory, cover must
resolve from the purchase alone with the consumer as metadata - which is a different query and a different
Consumer 360 page.

## 3. What makes two purchase records the same purchase? — RESOLVED 2026-07-31

**Resolved: header + lines, dedupe on the header, link never reject.** The earlier framing was
structurally wrong - purchases were flat, so dedupe had to happen per line, where a misread quantity or an
unresolved variant produces a near-duplicate. One receipt is **one purchase event covering several
products** (Sean's `SRTWC8366 x 1 / SRTWC8152 x 1` under one document), so `consumer_purchases` is the
header and `consumer_purchase_lines` holds the products - matching `orders`/`order_lines`.

- **Dedupe key:** `(customer_id, dealer_document_number_norm, purchase_date)` as a **partial** unique
  index, only where all three are non-null, so an incomplete key still writes.
- **`attachments.file_hash`** catches an exact re-upload of the same file for free.
- **Link, never reject.** The packing-list precedent rejected on a triple match, which was right for a
  staff import; here the submitter is a consumer and refusing their complaint because we think we have seen
  the receipt is unacceptable. On collision, attach the new Complaint to the existing purchase.
- **Partial key writes and flags** (`dedupe_pending`) into a CS review list. Never blocks (AC-C14).
- **Value splits by level:** `total_value` on the header is what the receipt says at the bottom;
  `line_value` on a line is usually unknown and stays nullable.
- **Warranty assessments attach to a line, not a purchase**, via
  `complaint_product_lines.consumer_purchase_line_id`, since cover is per product and per part.

Original framing kept below.

One receipt covers several items; two complaints months apart cite the same receipt. Without a dedupe key
the ledger double-counts, and value reporting inflates.

Candidate key: `dealer + dealer_document_number + purchase_date`. Problems: dealer document numbers are
**not** unique across dealers, OCR misreads them, and the dealer may be unresolved at the time of writing.

**Direct precedent:** the packing-list duplicate-detection work hit exactly this and needed a
three-field composite plus explicit rejection. That lesson applies here and has not been applied.

## 4. What does `line_value` actually mean? — RESOLVED 2026-07-31

**Resolved: capture `total_value` as printed, nothing more, behind a permission gate.**

- **No normalisation.** No SST handling, no discount allocation, no per-unit derivation. Normalising a
  photographed third-party receipt produces false precision that will be wrong in a way nobody can explain.
- `line_value` stays **null** in the normal case; only `total_value` on the header is captured, labelled in
  the UI as *"as printed on the dealer's receipt, unverified"*.
- **Reporting states coverage** (`value known on N of M purchases`) so no total is ever read as complete.
- **New permission slug `consumers.purchase_value.view`**, off by default. Keeps the number available for
  the commercial question while stopping retail prices appearing on every CS screen where a dealer's own
  staff might be shoulder-reading during a support call.

**Named consequence, unanswered and folded into fork 5:** Sorento already knows its own wholesale price to
each dealer, so storing retail makes **dealer margin computable** whether or not anyone intends to compute
it. That is a business decision, not a schema one.

Original framing kept below.

A dealer receipt line can be a bundle price for three items, tax-inclusive or not, before or after a
discount, or absent entirely. Capturing "value" from an arbitrary third-party document is not one number.

Worse, the *interesting* number commercially is the **dealer's retail price** - it reveals channel margin.
That is exactly the number a dealer would least like Sorento to hold.

**Needs deciding:** which value we store (line total as printed? unit price? nothing?), whether we
attempt tax and discount normalisation at all (recommend: no), and whether retail-price capture is a goal
or a liability.

## 5. How do Dealers react to being bypassed? — ANSWERED 2026-07-31

**Sorento's position: reciprocal, and margin visibility is intended.**

- **Reciprocal.** Dealers get back complaint and service history **for their own customers**. This turns
  extraction into a shared after-sales service, and makes a dealer discovering the system a good day rather
  than a bad one. **New scope:** a dealer-facing view scoped to their own `customer_id`, with its own
  permission and its own slice. Not previously in the plan.
- **Margin visibility is intended**, and is to be stated in the plan rather than left implicit.

> **UNRESOLVED CONFLICT with fork 4.** Fork 4 captures `total_value` on the **header only**, with
> `line_value` null in the normal case. **Per-product margin is therefore not computable** - a receipt total
> covering three items cannot be compared against per-product wholesale. Margin reporting is only possible
> coarsely (receipt total vs the sum of our wholesale for those lines, when every line resolved). Either
> accept coarse-only, or reverse part of fork 4 and capture line values. Needs deciding before S9.

Original framing kept below.

The module's stated purpose is to capture consumer data **by bypassing the dealer**. Dealers are Sorento's
paying customers, and the same platform shows them promotions, forms and orders.

If a dealer works out that Sorento is accumulating their end-customer list and their retail prices, that
is channel conflict - and this system is the evidence. This is a business risk, not a technical one, and it
should be a deliberate decision by Sorento rather than a side effect of a schema I designed.

**Needs deciding:** is this explicit strategy that Sorento is comfortable defending, or quiet
data-gathering? The answer does not change the tables much. It changes what the consumer-facing portal
says, and what a dealer can see.

**Folded in from fork 4:** does Sorento *intend* dealer-margin visibility? Wholesale price is already
known, so storing retail makes margin derivable. If intended, state it in the plan so nobody is surprised.
If not, narrow further: capture `total_value` but never expose it per-product, so margin cannot be derived
line by line.

## 6. What consent are we actually collecting, and for what? — ANSWERED 2026-07-31

**Sorento's position: warranty and service only. Anonymise on request, keep the purchase.**

- **Purposes: warranty and service only** (option 1 wording). No marketing opt-in is collected.
  `consumer_profiles.marketing_consent` is **removed** from the DDL - it would be a field nobody may act on.
- **Erasure: anonymise the profile, retain the purchase record.** A lifetime ceramic warranty may still be
  claimed against a purchase years later, so the commercial and warranty record survives while the person
  does not.
- **PDPA 2010 s.7(2): the collection notice must be in Bahasa Malaysia AND English.** Build requirement.
  ~~The Malay wording is not drafted and needs someone who writes it properly.~~
  **BUILT 2026-08-03.** The notice is versioned, immutable-once-published, admin-editable
  configuration (`consent_notices`, migration 322), seeded with v1 in both languages covering
  every element s.7(1) enumerates. Publishing without either language is refused, so the
  statute is enforced by the code rather than remembered. The Malay is written as Malay, not
  transliterated, and **still wants sign-off from whoever approves Malay legal wording for
  Sorento** - now a review of real text at
  **System Management -> Consent Notices**, not a blocking blank.

  Two things the build corrected. `consumer_service` stamped a literal
  (`2026-08-BM-EN-DRAFT`) that resolved to no text at all, so the column answered nothing.
  And a staff-created profile now claims **no** notice: `ensure_profile` runs where nobody is
  shown anything, and stamping a version there asserts somebody read words that were never on
  their screen. `record_consent` stamps it only when a portal displays the notice, and fails
  closed when none is published.

> **ONE-WAY DOOR, flagged.** Service-only consent means these profiles **cannot be used for SMC
> broadcasting or any marketing**, now or later, without fresh consent from each person. And re-contacting
> them to ask for that consent is itself arguably marketing. So the ledger becomes an **analytics asset**
> (aggregate dealer sell-through, volumes, values) rather than a **marketing list**. That is a coherent
> choice, but it is much cheaper to capture an unticked opt-in now than to run a re-consent campaign later.
> Sorento should confirm they understand this is effectively permanent.

Original framing kept below.

`consumer_profiles.marketing_consent` exists in the DDL because I put it there. Nobody decided it.

Phase 2 also ships **SMC broadcasting**, so there is an obvious pull to feed these profiles into marketing
sends. PDPA consent obtained for *warranty service* does not cover marketing, and the consent has to be
captured at the moment of collection with wording that matches the intended use.

**Needs deciding:** the permitted purposes, the wording shown at submission, retention period, and whether
a consumer can ask to be forgotten while Sorento keeps the purchase record for warranty. Likely needs
someone other than us to sign it off.

## 7. Does a Consumer Profile belong to the warranty module at all? — RESOLVED 2026-07-29

**Resolved: a new `consumers` MODULE owns `consumer_profiles` + `consumer_purchases`; `warranty` depends
on it and owns only policy, terms, kinds and assessments.** Not CORE (core is exactly one module today,
`base`, and consumer data would be the first domain data in it; a direct-selling tenant would never
install this). Not named `purchase` (collides head-on with `procurement`, which runs the opposite
direction). `warranty_registrations` renamed **`consumer_purchases`**; "Warranty Registration" survives as
the glossary term for the *act*, now a `registered_at` timestamp on a purchase.

Original framing kept below for the record.

**I think I got this wrong.** I put `consumer_profiles` inside the `warranty` module because that is where
I happened to be working. But by the reuse test in `PRINCIPLES.md`, a Consumer Profile is plainly a shared
asset: SMC engagement wants it, marketing broadcasts want it, e-commerce wants it, and none of them should
depend on the warranty module being installed.

That makes it a strong candidate for **CORE**, or for its own small module that `warranty` depends on -
not a table inside `warranty`. Getting this wrong is not cosmetic: it decides whether uninstalling warranty
takes the consumer list with it.

**Needs deciding:** CORE, own module, or stays in `warranty`. This is the classification step
`PRINCIPLES.md` requires **before** the UAC, and it was skipped.

---

## Recommended order to grill

~~7~~ · ~~1 and 2~~ · ~~3~~ · ~~4~~ **all done**. Remaining: **5 and 6 with Sorento** - 6 before S3 ships.
