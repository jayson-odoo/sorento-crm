# PLAN: Certificate links to check (CERT-LINK-CLEANUP)

Status: Built, in review (PR #2249). Track: full (M: migration + new report + bulk actions + ingest change).
Tests first, reviewer + security-reviewer fix round 1 done, cloud browser pass done.
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

## Build map

| Piece | Where |
|---|---|
| Verdict rule (pure) | `sorento_crm_backend/app/services/certificate_link_check.py` |
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

## Deploy notes

- Migration `clink_0001_link_checks` (additive, idempotent).
- Worker restart: new task module `app/tasks/certificate_link_tasks.py` on the `flyer_read` queue.
