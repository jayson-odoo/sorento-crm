# PLAN: Seed every combo from the 2026 dealer A3 flyer with one idempotent script

Status: Built and verified; #2282 merged 9 Nov (main 8ab90e53), live in prod image e81cc34f; owner prod dry run
done 9 Nov ~21:55. Follow-up #2289 (owner's hand-made combos as aka). Track: full (prod data bulk write, size L).
Lane: COMBO-SEED-FLYER.

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

1. `sorento_crm_backend/scripts/data/combo_seed_flyer_2026.json`: every combo, host code, name, LP, SP,
   description HTML, parts (fixed / choice with options / upgrades), free items (accessory vs product), flyer page.
   UNMATCHED list on the review page. Built by `combo-seed-flyer-tools/` (spans reader, seed builder, page maker).
2. Owner review page `documentation/plans/dealer-kit/combo-seed-flyer-review.html` (static, self-contained), filed
   via `crew report --ask` with 5 questions (answered 9 Nov: all recommendations).
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
(f) Discontinued parts (crew, 9 Nov, from the owner's 7 Nov price tag ruling): load like any part, named on the
line as `loaded (discontinued): CODE`; discontinued hosts load (`host discontinued`). UAC AC-15b.

## Prod run (owner, on server A, the primary; never run by a lane)

Precondition: PR #2282 merged AND released (the seed ships in the image as
`scripts/data/combo_seed_flyer_2026.json`). Check first:

```
cd /opt/sorento-crm2
C=$(cat .active_color); echo "colour: $C"
docker compose exec -T backend_$C ls -l scripts/data/combo_seed_flyer_2026.json
```

1. Dry run (writes nothing; prints one line per combo, then counts):

```
docker compose exec -T backend_$C python scripts/import_product_combos.py --strict \
  --file scripts/data/combo_seed_flyer_2026.json --report /tmp/combo-seed-dryrun.csv \
  > ~/combo-seed-dryrun.txt 2>&1; tail -n 7 ~/combo-seed-dryrun.txt
```

   Paste back: `grep -v '^SKIP' ~/combo-seed-dryrun.txt` (every CREATE / UPDATE / UNMATCHED / FAILED line and the
   counts). Look at CREATE lines that end `host also has: "..."`: when one of those names is a combo you made by
   hand for the same flyer package, say "old name -> flyer name" and the lane adds it as `aka` (no duplicate).
2. Apply, only after the dry run has been read:

```
docker compose exec -T backend_$C python scripts/import_product_combos.py --strict --apply \
  --file scripts/data/combo_seed_flyer_2026.json --report /tmp/combo-seed-apply.csv \
  > ~/combo-seed-apply.txt 2>&1; tail -n 7 ~/combo-seed-apply.txt
```

3. Re-run step 1: every loaded combo now reads SKIP (the UNMATCHED ones stay UNMATCHED until their codes are named).

Never add `--update` (it overwrites and prunes). Expected on the 4 Nov dev copy (seed v2): CREATE 110, UPDATE 41
(`fills: description bold`), SKIP 61, UNMATCHED 31; prod differs by the combos made after 4 Nov.

## Follow-up: the owner's hand-made combos as aka (owner "map ok", 9 Nov ~22:10)

Prod dry run 9 Nov ~21:55 (e81cc34f): CREATE 110, UPDATE 2, SKIP 100, UNMATCHED 31; 20 CREATE rows sat on hosts with an
owner hand-made combo under another name. Seed now carries the owner's pairing as `aka` (21 entries): "BATHTUB COMBO" x5;
"WALL HUNG WATER CLOSET COMBO" (push panel row) / "... 2" (flush valve row) on SRTWC6021-SH-UF, SRTWC6011-RL-BL,
SRTWC6022-SH-UF; "FLOOR STANDING WATER CLOSET COMBO" (+SRTFP4001) / "... 2" (+SRTFV2011) on SRTWC6031-SH-UF;
"URINAL BOWL COMBO" x5; "BATHROOM FURNITURE COMBO" on SRTBF11412; "CERAMIC BASIN COMBO" on SRTWB1419-GY; and
"SRTBF11834 + SRTMR502-BL" on the flyer's "(p21)" entry. That name was the p20 entry's exact name, so the p20 package
is now "SRTBF11834 + SRTMR502-BL (p20)" (created as its own combo). SRTWB7065: no pairing (owner).
Kitchen sinks SRTKS8835-BL / SRTKS1235-BL / SRTKS8835 / SRTKS1035: their own-code combos are already the exact-name
match of the flyer's p56 entries (dev 4 Nov: same SRTKT71SS tap); no aka, so the p55 SRTKT74SS packages still create.
An aka match keeps the owner's name and fills only what is empty. No release is needed: `--file` takes a patched copy
(`crew/state/files/COMBO-SEED-FLYER/prod-aka2.sh`).

## Follow-up 2: the first prod apply ran WITHOUT aka (crew, 9 Nov ~22:55)

The owner applied the original seed; the aka dry run then read CREATE 1 / SKIP 211 / UNMATCHED 31 because each
flyer entry now exact-matches the flyer-named combo the first apply created next to the owner's own (the exact name wins
over an aka, `import_product_combos.py:638-641`); the CREATE is "SRTBF11834 + SRTMR502-BL (p20)". Reproduced on a
slim dev copy (owner combos made by a user first, then main's seed applied): same three numbers, 20 hosts with BOTH.
`scripts/oneoff/remove_flyer_seed_duplicates.py` (UAC AC-D1..D5) deletes only a flyer-named combo that the importer
created (created_by NULL, creation audit row by job `import_product_combos`), that nobody touched since (no other audit
row as entity or root, `app/models/audit.py:42,84-85`), with no tag template link or price tag request line, and only
when the owner's paired combo exists. Dev proof: dry run 0 writes; apply deleted the 20 (combos 304 -> 284, owner combos
20 kept, audit 941 -> 999, existing rows kept); re-run NO DUPLICATE 21; then the aka seed: UPDATE 20 (owner combos
filled: prices, parts, free items; names and text kept), CREATE 1 "(p20)"; re-run SKIP 212 + UNMATCHED 31.
Prod order (owner): `crew/state/files/COMBO-SEED-FLYER/prod-pairs-report.sh` (read only) -> `prod-dups.sh` dry run ->
owner go -> `--apply` -> aka seed dry run (`prod-aka.sh`) -> owner go -> its `--apply`.
