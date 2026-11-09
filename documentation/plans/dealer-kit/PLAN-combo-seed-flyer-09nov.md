# PLAN: Seed every combo from the 2026 dealer A3 flyer with one idempotent script

Status: Build (script green, seed v1 applied on a throwaway dev copy; review + browser pass next). Track: full (prod
data bulk write, size L). Lane: COMBO-SEED-FLYER. PR #2282.

## Journey

Owner, 9 Nov 2026 ~14:35 MYT: seeding bathtub, water closet, urinal bowl and bathroom furniture combos by hand is
too slow. He wants one script that seeds every combo on the flyer: description with the flyer's bolding, list and
selling price, free items (accessory library entry or catalogue product), and parts as fixed or choice.

## Source

- Flyer: promotion attachment `fba70095-04ed-43f7-9a74-f110a8c8bd33`, "UPDATED SORENTO A3 FLYER  2026
  DEALER_21072026.pdf", 35 050 946 bytes, sha256 `bd9506f6...83b6` (dev copy `sorento_prod_1104`).
- The lane's R2 settings are the staging bucket; `storage_router.get_backend('r2').download_file(key)` answers
  "File not found in R2". Crew ruling 9 Nov: no prod CDN / bucket reads; crew drops the PDF at
  `crew/state/files/COMBO-SEED-FLYER/flyer.pdf`.
- `dealer_kit.flyer_reading` `7dc0db32-96c9-4a12-90ec-825592fc4a7f` is the SAME file (same sha256, same size):
  71 pages, per-card code, text lines, LP and SP. It carries no font weight, so it cannot give the bolding.

## What exists (cite before building)

- Combo: `app/models/product_combo.py:44` `ProductCombo` - natural key `UNIQUE (host_product_id, name)`
  (:100), `name` String(100), `description` Text, `list_price` / `sell_price`, `image_attachment_id`.
- Parts: `app/models/product_combo.py:104` `ProductComboPart` - `choice_group` NULL = fixed part; a label =
  one option of that choice (rows sharing the label are the options). Per part `sell_price`, `topup_amount`,
  `is_upgrade`. `UNIQUE (combo_id, part_product_id)`.
- Free items: `app/models/accessory.py:160` `ProductComboAccessory` - exactly one of `accessory_id` (library)
  or `item_product_id` (catalogue product); name/spec/remark overrides, `image_id`.
- Loader: `sorento_crm_backend/scripts/import_product_combos.py` (JSON seed loader; details in the Mechanism
  section once confirmed).
- Dev copy today: 174 combos (162 bulk-created 2 Nov with plain-text descriptions, hosts SRTBF 90, SRTKS 81,
  SRTWB 3), 646 parts (263 choice options), 261 combo free items.

## Flyer families (from flyer_reading 7dc0db32)

Bathtubs + mixers p2-7 (SRTBT, SRTWT510xx), jacuzzi p3-4 (SRTJC), water closets p8-12 (SRTWC, seat covers
SRTSCBD, flush SRTFP/SRTFC/SRTFV), urinals p9 (SRTUB, SRTFV/SRTUFV), bathroom furniture p13-21 (SRTBF, SRTWB,
SRTWT, SRTMCB, SRTMR), basins p24-27, kitchen sinks p55-69 (SRTKS, SRTKT, SRTWF, SRTBK).

## Deliverables (order fixed by the brief)

1. `combo-seed-flyer.json`: every combo, host code, name, LP, SP, description HTML, parts (fixed / choice with
   options), free items (accessory vs product), flyer page. UNMATCHED list separate.
2. Owner review page `documentation/mockups/COMBO-SEED-FLYER/index.html` (static, self-contained), filed via
   `crew report --ask` with at most 5 questions.
3. Script: one command, `--dry-run` default, `--apply` one transaction per host, re-run is a no-op.
4. Red-first tests, kill tests, reviewer, security-reviewer.
5. Apply on a throwaway copy of the dev DB, browser check 3 combos per family.
6. Prod is owner-run: crew-done carries the exact dry-run then apply command.

## Architecture

Layer: script only (`sorento_crm_backend/scripts/`). No API, schema, migration or UI change.

What already exists and is reused unchanged (code map, 9 Nov):
- `import_product_combos.py` loads a JSON seed through `ProductComboService` and `AccessoryService`; matches
  host + combo name case-insensitive (:366-370); without `--update` it fills only empty fields (description,
  free list, photo, null prices) and adds missing parts (`_wanted` :252-259, fill block :408-415);
  `--update` overwrites and prunes (:468-497). Parts: components = fixed, choice group options = parts sharing
  the label with option `sp`, `topups` = `is_upgrade` parts (`wanted_parts` :151-171). Seed model:
  `flyer_combo_read.py:123-133`. 63 tests in `tests/test_import_product_combos*.py`.
- Rich text: `combo_description` passes through `clean_description` (`app/services/tag_description.py:13`,
  5000-char cap) and `sanitise_tag_html` (`app/utils/tag_rich_text.py:199`, allow-list :19-22: `<strong>`
  kept, `<b>` dropped). Editor shape on dev rows: one `<p>` per line, `<strong>` per bold run.

What changes (one new flag, `--strict`, so legacy behaviour and its tests stay as they are):
1. Free item `kind`: `product` = exact code match only; `accessory` = existing library accessory by exact
   name (case-insensitive, company). Under `--strict` nothing is `find_or_create`d (today :459-461 creates
   "CODE label" accessories).
2. Hold rule: under `--strict` an entry with an unmatched host, part or free item writes nothing and prints
   `UNMATCHED (<codes/names>)`.
3. `aka` on an entry: previous combo names that also count as a match (owner renames).
4. Per-host transaction under `--strict --apply`: entries grouped by host; inside a host block the session's
   `commit` only flushes (the services commit per call today, e.g. `ProductComboService.create` :260), then
   one real commit; any failure rolls the whole host back and marks its entries FAILED.
5. Printed verdict per combo (`CREATE` / `UPDATE (fields)` / `SKIP` / `UNMATCHED` / `FAILED`) plus the
   names of other combos already on the host; the CSV report stays.
6. Seed model: `combo_description` cap 1000 -> 5000 (the service cap), `Free.kind`, `Combo.aka`.

Data: `scripts/data/combo_seed_flyer_2026.json` built from the flyer by the lead (PyMuPDF spans for exact text
and bold, page images for tile grouping, cross-checked against `flyer_reading` 7dc0db32 LP/SP per code).

## Owner answers (review page `combo-seed-flyer-review.html`, 9 Nov 15:12 MYT: "Ok all rec")

(a) Existing combo with the same host + name: fill only empty fields; add the flyer bold only where the stored
plain text has the flyer's exact words; never overwrite; a renamed combo is matched through `aka`.
(b) UNMATCHED codes / names (14 in 31 combos): hold the whole combo; crew-done lists them with catalogue hints so
the owner can name the right codes later (then the seed gets exactly those codes and is re-run).
(c) WC / urinal combos (separate LPs per item, one SP): combo list price blank.
(d) Bathtub combos: SRTWT51012 a free item; the 4 colour mixers RM 150 upgrades.
(e) Load every family: bathtub, WC, urinal, bathroom furniture, basin, shower fitting package (host = the
concealed mixer valve), kitchen sink. SRTSCBD291 (p12) left out: one product with its fittings.
