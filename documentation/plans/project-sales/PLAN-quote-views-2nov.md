# PLAN: PS-QUOTE-VIEWS (view count on the proposal/quotation sign link)

Status: Build. Track: full, size M (one additive migration, new public ingest endpoint).

Lane: PS-QUOTE-VIEWS, owner 2 Nov 2026 ~21:20 MYT. Behaviour card: `CARD-quote-views-2nov.md`.
UAC: `quote-views-2nov-acceptance-criteria.md`.

## Slices

1. BE: model + migration `projects.quotation_issue_views`; service `quotation_view_service.py`
   (`record_view`, `summary_for_document`, `log_for_document`); public `POST /{token}/view`; document
   serializer gains `view_count`, `last_viewed_at`; staff `GET .../documents/{id}/views` (log).
2. FE: sign page beacon (skip when signed in), document page "Viewed N times, last ..." + view log.
3. Tests: pytest for dedupe, bot refusal, expired token, summary per latest issue; vitest for the beacon
   skip and the header line.
