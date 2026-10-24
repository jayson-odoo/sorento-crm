# PLAN: media intake guard (24 Oct 2026 prod incident)

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Journey

A customer sends a photo to the chatbot. Today a download that is not really an image (an HTML
error page, a truncated body, a non-image the provider labels as one) is forwarded to Gemini as
`image/jpeg`; Gemini then fails fast or answers "the image appears corrupted", the job either
fails with no reason in the trace or "completes" with 0 items, and the parser runs on empty text.

## Changes

1. After download, check the first bytes against the expected modality (image: jpeg/png/webp/gif/heic;
   document: pdf; video; audio). A mismatch fails the job with
   `Downloaded file is not a <modality>: content-type X, N bytes, first bytes <hex>`.
2. A completed image read with 0 items and no caption/text replies `wording.nothing_read()` instead
   of running the parser on empty input.
3. `stored_attachment` passes the stored media mime type when the chat history row has it.
4. Gemini 402 / "credits depleted" gets the same whose-problem operator hint as 429.
5. Trace view prints "quoted turn" as readable fields instead of `[object Object]`.

No prompt changes. Touched tests only.

UAC: `media-intake-guard-24oct-acceptance-criteria.md`.
