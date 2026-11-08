# UAC: Certificate links to check (CERT-LINK-CLEANUP)

Plan: `PLAN-cert-link-cleanup-08nov.md`. Card: `CARD-cert-link-cleanup-08nov.md`.

## Verdict (tests: `tests/test_certificate_link_check.py`)

- V1 Printed `14A` on the PDF: `SV-14A-CP` and `CSK14A-BL` are Check (short code); `BRD7711CP`, `BRHSD213C`, `FUR-A11C` are Not found.
- V1b Real SPAN shape (prints `11C`, `13C`, `14A`): `BRD7711CP`, `BRHSD213C`, `MGB5011C`, `GB3011C` are Not found through `11C`/`13C` (preceded by a digit);
  `FUR-A11C` is Check; `SV-14AB` is Not found through `14A` (followed inside its segment); `CSK14A-BL` is Found through a printed `CSK14A`; none of the over-linked products is Found.
- V1c Numbered table (`3 | 13A`): the row number is never joined into the code (`313A` is not a run), so `CB313A-NL` is not Found; a run of short tokens only (`AB 12C`) is Check.
- V1d A printed code that starts with a digit is Check unless the full product code is printed: `75-RG` for M459A-75-RG / M460A-75-RG / M461A-75-RG / M459-75-RG, `32SS` for M32SS-*, `61SS` for CB61SS-* are Check; a printed `SRTKT61SS` is Found for SRTKT61SS. "Preceded by a digit" only counts inside the same dash/space segment.
- V1f Rule B-cat: a digit-led run that only ONE catalogue family contains reads Found (`162-QT`, `165-QT` in SRTWT only); in 2+ families it reads Check (`75-RG` in M459A/M460A/M461A, `32SS` in M/SRTKT, `61SS` in CB/SRTKT, `906SS` in SRTWT/ORIWT). Short codes stay Check whatever the catalogue says.
- V1e A confirmed link with no code on it reads Found when any run of its product code is printed (SRTWB241 with `WB 241`).
- V2 `4A` inside the printed word `14A` is never a hit (whole token only); spaces, hyphens and case are ignored.
- V3 A code under 3 characters or without a digit does not count as contained; a digits-only code, or any code of 3 or fewer characters, is Check, never Found.
- V4 A code a person typed skips the containment rule.
- V5 No code on the link: the longest printed run inside the product code decides.
- V6 Exact product code, a printed set code the product belongs to, each part of `A + B`: Found (Check when the code is 3 or fewer characters).
- V7 No text layer: Scanned. No readable file: No file. Symbol-font text is decoded first.

## Ingest (tests: `tests/test_cert_link_ingest_tighten.py`, `tests/test_qcert_ingest_code.py`)

- I1 A printed short code links only products that contain it on a boundary (`11C` never links `BRD7711CP`).
- I2 A string not printed on a text PDF links nothing and is listed as unmatched / skipped.
- I3 The family-prefix tier is off for certificates; digits-only and short strings never fan out.
- I4 A scanned PDF skips the printed check only. A renewal adds only printed links. `A + B` parts are checked separately.

## Report and actions (tests: `tests/test_certificate_links_report.py`, FE `CertificateLinksList.test.tsx`)

- R1 Unchecked links read Checking (`pending`); opening the page queues one deduped check job when any link in scope is unchecked, including links outside the current view (manual links).
- R2 Filters: verdict (with counts), certificate, certificate type, certificate status, source, search; sort allowlisted.
- R3 The default view is AI links that are Not found or Check.
- R4 A changed code, product code or revision reads Checking again.
- R5 Confirm: source becomes manual, one audit row per link on the product ("was AI"), unknown id = 404 and nothing changes.
- R6 Remove: 10 s server-deferred countdown with Cancel; commit hard-deletes the link and its projection and writes `file_unlinked`.
- R7 Another company's link: not listed, Confirm 404, Remove refused at park time (404) and at commit time.
- R8 View needs `master_data.certificates.view`; Confirm and Remove need `.edit`.
