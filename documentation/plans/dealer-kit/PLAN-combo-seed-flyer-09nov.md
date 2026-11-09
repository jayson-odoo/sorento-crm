# PLAN: Seed every combo from the 2026 dealer A3 flyer with one idempotent script

Status: Plan. Track: full (prod data bulk write, size L). Lane: COMBO-SEED-FLYER. Waiting on the flyer PDF bytes
(crew is fetching a fresh link from the owner; bolding is TODO until it lands).

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

TODO after the code map lands: layer (script only, no API/UI change), mechanism (reuse or sibling of
`import_product_combos.py`), classes touched.

## Open questions for the owner (filed with the review page)

(a) Existing combo with the same host + name: skip / fill empty fields only / overwrite. Recommendation: fill
only empty fields.
(b) UNMATCHED codes: leave out and list, or create a placeholder. Recommendation: leave out and list.
