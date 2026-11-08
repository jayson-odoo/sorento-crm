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
| Ingest tightening (prefix off, gated substring, printed check, `+` per part) | `app/api/v1/external/product_attachments.py` `_resolve_product_codes` |
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

## Deploy notes

- Migration `clink_0001_link_checks` (additive, idempotent).
- Worker restart: new task module `app/tasks/certificate_link_tasks.py` on the `flyer_read` queue.
