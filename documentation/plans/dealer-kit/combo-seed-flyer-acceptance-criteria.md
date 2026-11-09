# UAC: Seed every flyer combo with one idempotent command (COMBO-SEED-FLYER)

Plan: `PLAN-combo-seed-flyer-09nov.md`. Script: `sorento_crm_backend/scripts/import_product_combos.py`
(extended, not a sibling). Seed: `sorento_crm_backend/scripts/data/combo_seed_flyer_2026.json` (product codes,
prices and flyer text only; no customer data).

Owner answers (review page, 9 Nov 15:12 MYT): all recommendations accepted; the rows marked [default] are now
the owner's answers.

## Command

- AC-0 The flyer rules below (AC-7, AC-8, AC-13 to AC-15, the per-host transaction of AC-3) apply under a new
  `--strict` flag; without it the importer behaves exactly as today (its 63 existing tests stay green unchanged).
  The owner's commands always carry `--strict`.
- AC-1 One command loads the whole seed: `venv/bin/python scripts/import_product_combos.py --strict --file
  scripts/data/combo_seed_flyer_2026.json` is a dry run and writes nothing to the database (every table it can
  touch has the same row count and the same values after the run).
- AC-2 The dry run prints one line per combo, in seed order: `CREATE`, `UPDATE (<fields>)`, `SKIP` or
  `UNMATCHED (<codes or names>)`, with host code, combo name and flyer page; then a count per verdict.
  Line shape (tests parse it by splitting on ` | `): `<VERDICT> | <host code> | <combo name> | p<page> | <details>`;
  VERDICT is one of CREATE, UPDATE, SKIP, UNMATCHED, FAILED; details: UPDATE `fills: <field>, <field>` (field
  names: description, list price, selling price, free items, parts <codes>), UNMATCHED `missing: <code or name>,
  ...`, CREATE `host also has: "<name>", "<name>"` or empty, FAILED the error. Counts: `<VERDICT>: <n>`.
- AC-3 `--apply` writes. All writes for one host product are one transaction: when anything for that host
  fails, nothing for that host is kept, the host's combos print `FAILED (<reason>)`, and the other hosts load.
- AC-4 Re-running `--apply` with the same seed right after an apply writes nothing and prints `SKIP` for every
  combo it loaded (no new combo, part, free item, or changed value; `updated_at` unchanged).

## Existing combos (Q(a) [default: fill only empty fields])

- AC-5 A combo already on the host with the same name (case-insensitive) is never duplicated.
- AC-6 Without `--update`, an existing combo only gets what it lacks: an empty description, an empty free
  items list, a blank list or selling price, and its parts only when it has no parts at all. A value someone
  set (name, description, price, free items list, parts) is never overwritten or mixed with the flyer's: a
  combo whose parts differ from the flyer keeps its own (`kept: parts differ (flyer: ...; on file: ...)`).
  The line reads `UPDATE (<filled fields>)` or `SKIP`.
- AC-7 A seed entry with `aka: ["<old name>"]` matches an existing combo on that host named any of those names
  (case-insensitive) and treats it as the same combo: no new combo; the existing name is kept.
- AC-8 When the host already has combos under other names and none matches the entry's name or aka, the line
  still reads `CREATE` and lists those names (`host also has: "X", "Y"`), so a renamed combo can be caught
  before `--apply`.

## Parts

- AC-9 A component is a fixed part (`choice_group` NULL). A choice group's options are parts sharing that
  group label; an option's printed SP is that part's `sell_price`.
- AC-10 A top-up is an upgrade part: `is_upgrade` true, `topup_amount` = the printed top-up, no choice group.
- AC-11 Codes match the catalogue exactly (case-insensitive, same company); nothing is guessed from a name or
  a prefix.

## Free items

- AC-12 A free item with `kind: "product"` and a code that names a catalogue product becomes a product entry
  (`item_product_id`).
- AC-13 A free item with `kind: "accessory"` becomes the library accessory whose name equals the label
  (case-insensitive, same company). Under `--strict` no library accessory is ever created.
- AC-14 Under `--strict`, a free item whose code or name does not match is UNMATCHED: listed on the combo's line, never
  created, never guessed.

## Unmatched (Q(b) [default: hold the whole combo])

- AC-15 A combo whose host, any part, or any free item is unmatched is not written at all; its line reads
  `UNMATCHED (<every missing code or name>)`. The rest of the seed loads.

- AC-15b A discontinued part (`products.is_discontinued`), fixed or choice or upgrade, loads like any part and is
  named on the line (`loaded (discontinued): <code>`) so the owner sees it. A discontinued host is named too
  (`host discontinued`); its combo loads. Rule: owner, 7 Nov ~21:30-21:50 (price tag flow: discontinued items stay
  selectable with the Discontinued hint, a discontinued fixed part warns only, dealers still sell discontinued
  stock), relayed by crew 9 Nov; it supersedes `CARD-pricetag-combo-render-04nov.md:109-110` for combos.
- AC-15c A free product that is also a part of the combo loads as that product on the free list, and the
  part stays a part (COMBO-FREE-PART, owner 9 Nov, `PLAN-combo-free-part-09nov.md`); it never fails the host.

## Description

- AC-16 The seed's `combo_description` is the app's rich text HTML (one `<p>` per flyer line, `<strong>` for
  every bold run as printed); it is stored exactly as the editor would store it (through the same sanitiser),
  so the bold survives and the combo editor shows it bold.
- AC-17 A description up to the app's limit (5000 characters) loads; the seed check no longer cuts at 1000.

## Safety

- AC-18b Names read from the database are printed with control characters removed, so one verdict line is always
  one line. The script exits non-zero when any combo is FAILED.

- AC-18 The script never deletes a combo, never removes a part or free item, and never overwrites a set value
  unless `--update` is given (and `--update` is not part of the owner's prod commands).
- AC-19 The seed file holds only product codes, combo names, prices, flyer text and accessory names; no
  customer, dealer or person data.

## Data (the seed itself)

- AC-20 Every combo on the flyer is in the seed or in the review page's "not a combo / page offer" lists, with
  its flyer page.
- AC-21 On a throwaway copy of the dev DB, after `--apply`, 3 combos per family (bathtub, water closet, urinal,
  bathroom furniture, kitchen sink) open in the product page's Combos card with the flyer's name, prices, bold
  description, parts (fixed / choice / upgrade) and free items.
