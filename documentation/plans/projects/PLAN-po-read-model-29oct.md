# PLAN: PO document reader model comes from System Settings (PO-READ-MODEL)

Status: in progress (normal track: carries a migration; diff expected under 300 lines)

## Problem (prod, 29 Oct 2026)

Project > Orders > "Upload a PO document" ends in "This document could not be read. No page of this
document could be read." The prod Gemini key belongs to a new Google account, which gets a 404 on
`gemini-2.5-flash`. The PO reader took its model only from `DOCUMENT_AI_MODEL` (default
`gemini-2.5-flash`, `app/config.py:335`), so nothing on a settings screen could fix it. Photo reading
already works on prod with `gemini-3.5-flash`, picked in System Settings.

## Decision

- Two nullable columns on `system_settings`, `document_ai_provider` / `document_ai_model`, the same
  shape as the photo lane's `media_image_provider` / `media_image_model`. The migration seeds the
  existing row with `gemini` / `gemini-3.5-flash`, so prod reads again on deploy with no click.
- Picker: a "PO and delivery schedule reading" card on System Settings > Chatbot Media, the page
  that already holds the photo model picker, reusing its provider select and `ModelField` (live
  model list from `useProviderModels`, typed names accepted, Test button probing the model).
- Resolution order in `document_extraction.extract_document`: the setting, then the env
  (`DOCUMENT_AI_PROVIDER` / `DOCUMENT_AI_MODEL`) only when the setting is blank. Env default becomes
  `gemini-3.5-flash`.
- Every `gemini-2.5-*` default in backend code moves to `gemini-3.5-flash`.
- When every page fails, `extraction_error` carries the first page's reason (short, no secrets), so
  the "could not be read" panel says why.
- A provider "model not found / not available" answer logs one clear line naming the model.

## UAC

1. With the setting saved as gemini / M, the PO reader calls Gemini with model M (env ignored).
2. With the setting blank, the env model is used (fallback only).
3. A 404 "model not found" on every page leaves the version failed with that reason in
   `extraction_error`, and a log line naming the model.
4. No `gemini-2.5-*` literal remains as a default in `app/`.
