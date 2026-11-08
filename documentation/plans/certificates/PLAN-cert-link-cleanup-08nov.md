# PLAN: Certificate links to check (CERT-LINK-CLEANUP)

Status: Built, in review (PR #2249). Track: full (M: migration + new report + bulk actions + ingest change).
Tests first, reviewer READY after round 2, security-reviewer findings fixed, cloud browser pass done, crew pass done;
boundary + short-code rule (crew ruling 8 Nov) built test-first, reviewer round 3 findings fixed.
Follow-up to #2245 (QUOTE-CERT-TAB). Behaviour card: `CARD-cert-link-cleanup-08nov.md`.
UAC: `cert-link-cleanup-08nov-acceptance-criteria.md`.

## Owner ask (gist)

The AI ingest over-links products on short codes (the 14A stop-valve certificate SPAN BPAI/1327-2024 is
linked to 158 products; 10,176 of 10,178 links are source `ai`). This lane: (1) a Master Data report
"Certificate links to check", (2) explicit bulk Remove / Confirm with audit, never automatic, (3) tighten
the ingest so a link needs the printed code as a whole token going forward.

## Owner answers (crew, 8 Nov)

- Q1: FOUND = the printed code (whole token on the PDF, spaces/hyphens/case ignored, symbol font decoded)
  is CONTAINED in the product code as a contiguous run, 3+ characters with a digit; digits-only = Check;
  a code a person typed always counts. (Supersedes the card's Q1 recommendation.)
- Q2 (a): certificates only. Q3 (a): Confirm flips `source` to `manual`, audit says "was AI".

Consequence applied in review round 1 (no new question): the exact tiers the ingest keeps also count as
backed: the product's own code, a printed product-set code the product belongs to, each part of `A + B`.

**Crew ruling after the crew pass (8 Nov, safety first), replacing the Q1 contained-run rule.**
Run offline on the real SPAN BPAI/1327-2024 file, the Q1 rule gave 153 found / 5 check / 0 not found:
the certificate also prints `11C` (row 14) and `13C` (row 16), so BRD7711CP, BRHSD213C, FUR-A11C,
MGB5011C and GB3011C read Found.
- Boundary: a printed code that starts with a digit must not be preceded by a digit in the product
  code, and must not be followed by another letter or digit unless that is the end of a dash/space
  segment. (Kills BRD7711CP, BRHSD213C, MGB5011C, GB3011C.) Crew answer (a), same day: a code that
  ENDS with a digit may not be followed by a digit either (`CSK14` does not back `CSK140-BL`; `WB 1515`
  still backs `SRTWB1515`, `WC 8355` still backs `SRTWC8355-RL`).
- Crew offline check on the real file (head 9c1208df, 158 links: 14 Found / 78 Check / 66 Not found)
  found one false Found: `CB313A-NL` through `3 13A`, where the row number printed beside model `13A` was
  joined into `313A`. Now a row-number cell (a digits-only word of up to 3 characters that starts its line,
  followed by a word a column gap away) is never joined into a run, and a run printed only as tokens of 3
  or fewer characters (`AB 12C`, `3 13A`) is short: Check, never Found.
- Crew re-check on 2fa5b573 (real BPAI/1327-2024 and BPAI/1271-2024): digit-led printed codes collide
  across families because the family prefix is not printed (`75-RG` backed M459A-75-RG, M460A-75-RG,
  M461A-75-RG; `32SS` backed M32SS-*; `61SS` backed CB61SS-*). Crew rule: a printed code that starts with a
  digit is Check, never auto-Found, unless the FULL product code is printed (22KT, 28KT, 31SS, 51SS, 53SS,
  55SS, 62SS move to Check, accepted). The "preceded by a digit" check now only counts a digit in the same
  dash/space segment (`75-RG` in `M459-75-RG` reads Check on the rule, not Not found by accident).
- Confirm on a link with NO code (the common case: 5 of 10,178 dev links carry one) now reads Found: the
  no-code branch counts a confirmed link like a typed code (any printed run of the product code backs it).
- Sweep over every certificate file crew holds (read-only):
  `venv/bin/python scripts/cert_link_verdicts.py --pdf-dir state/files/quote-cert-8nov/prod-certs --digit-led-found`
  lists every AI link still read Found through a digit-led code, plus a total.
- Crew re-check on 7cb4e585 (all 126 prod certs): 0 false Found, but 107 right Founds became Check
  (1327 and 1271 showed 0 Found). Crew simulated alternatives offline and chose **rule B-cat**, which
  keeps 89 of the 107 with 0 false Found. A digit-led printed run that is not the full product code is
  Found only when, across the WHOLE active catalogue, the products containing it on a valid boundary
  belong to exactly ONE family; 2+ families is Check. Family = the normalised product code up to the
  start of the run (M459A-75-RG -> m459a, SRTKT32SS -> srtkt, M32SS-DIY -> m, CB61SS-BL -> cb,
  ORIWT906SS -> oriwt). So `75-RG`, `32SS`, `61SS` and `906SS` read Check, while `162-QT` and `165-QT`
  (srtwt only) read Found. `CatalogueFamilies` is built once per check job and memoised per run.
- The one family must be the LINKED product's own family (reviewer round 5): the catalogue holds active
  products only, so a link to an inactive product could otherwise read Found through another family.
- The sweep script also matches files named by certificate, revision or attachment id.
- A confirmed link (`source` manual) counts like a typed code; its code must still be printed. `source`
  is part of the check key, so a Confirm reads the link again (reviewer round 3).
- Short codes (3 or fewer letters and digits after normalising: `14A`, `11C`, `13C`) are never
  auto-Found: Check. A person confirms once (the link becomes manual) or removes it. Longer codes
  (`WB 1515`, `WC 8355`, `CSK14A`) keep the found rule. A typed code still always counts.
- The ingest substring tier applies the same boundary rule.
- Links outside the current view (manual links in the AI-only view) are checked too: the list returns
  `pending_all`, and the page queues the check on it.
- Offline proof on a real file (read-only):
  `cd sorento_crm_backend && venv/bin/python scripts/cert_link_verdicts.py --certificate "BPAI/1327-2024" --pdf <path to the PDF>`

## Build map

| Piece | Where |
|---|---|
| Verdict rule (pure) | `sorento_crm_backend/app/services/certificate_link_check.py` |
| Offline proof (read-only) | `sorento_crm_backend/scripts/cert_link_verdicts.py` |
| Printed runs, read once, only the wanted strings | `certificate_pdf_service.printed_runs` |
| Ingest tightening (prefix as last resort, gated substring, printed check, `+` per part) | `app/api/v1/external/product_attachments.py` `_resolve_product_codes` |
| Stored verdict + key | `certificate_products.check_verdict/check_code/check_key/checked_at`, migration `clink_0001_link_checks` |
| Report, check queue, Confirm, Remove handler | `app/services/certificate_link_report_service.py` |
| Routes | `app/api/v1/master_data/certificate_links.py` (`GET /`, `POST /check`, `POST /confirm`) |
| Remove | pending action `certificate_link.remove` (`record_actions.py`), park-time check in `pending_actions.py` |
| Worker | `app/tasks/certificate_link_tasks.py`, queue `flyer_read` |
| FE | `master-data-management/certificates/links/page.tsx`, `components/CertificateLinksList.tsx`, menu "Certificate Links" |

## Deviations from the card (recorded)

- R3 backfill: there is no deploy-time job. The first visit to the report queues one check job for every
  certificate with unchecked links (one job per pending set, deduped); the page polls up to 10 minutes.
  Trigger to add a deploy-time job: the first visit's wait is reported as a problem.
- R6 audit: one row per link on the product's Audit Trail (the existing PRODUCT-ATTACH-AUDIT pattern:
  `file_unlinked` for Remove, `certificate_link_confirmed` for Confirm), not one per certificate.
- `POST /check` needs only `.view`: it writes derived verdict columns only and is deduped.

## Known limit

- Adding a product to a product set, or removing it, does not re-check its links: the stored key covers
  revision, Code on certificate and product code, not set membership. The verdict refreshes on the next
  revision or code change. Trigger to add membership to the key: a set edit leaves a wrong verdict that
  someone acts on.

- Rule B-cat reads the catalogue at check time. A product added later can turn a one-family run into a
  two-family run, but already-stamped verdicts are not re-read until their key changes (revision, code,
  product code, source). To re-read everything after a catalogue change, run
  `UPDATE certificate_products SET check_key = NULL;`. Trigger to automate this: a catalogue change leaves
  a wrong Found that someone acts on.

## Owner ruling, 8 Nov 21:00: keep #2249, family prefix back as the last resort

"keep #2249". One change, applying the owner's earlier ruling #440 (31 Aug, R7: "SRTBV is fixed in the
ONE resolver as a last-resort tier"): the certificate ingest keeps the family-prefix tier ON as the LAST
resort, reached only when tiers 1-4 find nothing, as #440 built it. This lane had turned it off for
certificates; it is restored. A prefix match must have its family head printed on the PDF (a text PDF),
and stores no Code on certificate (it names a family, not a printed code). Every other #2249 rule stays:
whole-token, boundary, short and digit-led codes are Check, rule B-cat, the report and bulk actions.

## Deploy notes

- Migration `clink_0001_link_checks` (additive, idempotent).
- Worker restart: new task module `app/tasks/certificate_link_tasks.py` on the `flyer_read` queue.
