# PLAN: Certificate links to check (CERT-LINK-CLEANUP)

Status: Step 1 (behaviour card, no code). Track: full (M: new report + bulk actions + ingest change).
Follow-up to #2245 (QUOTE-CERT-TAB). Behaviour card: `CARD-cert-link-cleanup-08nov.md`.

## Owner ask (gist)

The AI ingest over-links products on short codes (14A stop-valve certificate linked to 158 products,
10,176 of 10,178 links are source `ai`). This lane: (1) a Master Data report "Certificate links to
check", (2) explicit bulk remove / confirm with audit, (3) tighten the ingest so a link needs the
printed code as a whole token going forward.
