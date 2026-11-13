# PLAN: Register a CRM project in AutoCount (AC-PROJECT-REGISTER)

Status: Plan - behaviour card posted as a crew ask, waiting for answers. Track: M (one additive
migration on `projects`; reuses the AC-QTSO-CRM write path, permission and dialog). Size from brief: M.

Owner, 13 Nov: "our project need to integrate with autocount to register a project in autocount,
the endpoint will be provided by autocount next week" ... "for autocount project registration ok"
(= build the CRM side now). UAT Wed 18 Nov shows the CRM flow with the AutoCount call pending.

## Reuse (discovery, file:line)

| Piece | Existing function | Use |
| --- | --- | --- |
| SS client, key, X-Request-ID + actor headers | `app/services/foundryx_autocount_client.py:259` `write()`, `:123` `trace_writes()` | reuse as is |
| Create that may land twice: write-ahead key, refusal releases, unknown keeps and re-sends the same key, row lock | `app/services/project_autocount_write_service.py:422` `_create()` | reuse as is (needs `autocount_pending_create` + `autocount_doc_key` on the record) |
| Every call logged + audit row with the person | `project_autocount_write_service.py:378` `_log_unlanded()` | reuse as is |
| SS answer -> plain words (refused / unreachable / pending / switched off) | `project_autocount_write_service.py:574` `_interpret()` | reuse as is |
| Capabilities read (op enabled or "Waiting for AutoCount") | `project_autocount_write_service.py:481` `_read_capabilities()` | extend: add `projects` kind to `_KINDS` |
| Book rule (no write without a book) | `project_autocount_write_service.py:519` `_no_book_answer()` | reuse |
| Route guard order: permission -> switch -> record -> SS | `app/api/v1/projects/project_autocount_write.py:69-91` | reuse `_assert_project_access`, `_guard`; add one route |
| Permission | `projects.autocount.write` (`app/rbac/permission_registry.py:743`) | reuse |
| FE hooks / button / result dialog | `project-sales/_shared/hooks/useProjectAutocountWrite`, `_shared/components/AutocountWriteButton`, `AutocountWriteDialog` | reuse; add one mutation hook |
| AutoCount number badge in a header | `QuotationDocumentPageHeader.tsx:113` | same Badge pattern |
| Project header gear menu | `ProjectDetailClient.tsx` `DetailActionsMenu` (~line 380) | add one item |

## Behaviour card

Posted as `crew-ask` on the PR; answers are folded back here before any code.
