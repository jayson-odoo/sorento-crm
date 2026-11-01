# UAC: DOC-ACCESS-SIMPLE - Document Access page

Plan: `PLAN-doc-access-simple-01nov.md` (same folder). Mock v1 approved by the owner 1 Nov 20:37 ("Ok"); card
Q1-Q5 all (a), confirmed 20:4x ("Doc all a"). `BE` = `sorento_crm_backend/app`, `FE` =
`sorento_crm_frontend/app/(protected)`.

## Journey

1. **Actor:** a staff admin who looks after documents (holds `resource.attachment_types.view`, and `.edit` to change
   anything). A dealer has complained that the WhatsApp agent "does not know" the Cabana warranty.
2. **Arrives from:** sidebar Resource Management > Document Access (under Attachment Types).
3. **First screen:** every document type in one grid: how many files and how many the AI can read (PDF, DOCX), a
   Staff tick and one tick per active access type, and how the type is sent as a file. A ticked cell that some
   documents do not carry shows "reach/readable" in amber. Nothing to type.
4. **System already knows:** the access types, every file's access levels and company, each contact's access
   types, companies, linked CRM user and agent switch. None of it is asked again.
5. **Step, one decision:** pick the dealer in **Preview as**. Every row now says what that contact reads ("Reads 5
   of 15 · 2 no shared access type, 8 other company") or the first thing that stops it ("No access type").
6. **Step, one decision:** tick the access type on the type row (or in the row's sheet). It saves at once; the toast
   says how many documents that access type can now read. The preview updates.
7. **Optional step:** open the row's sheet to see each document with its access levels, company and verdict, and fix
   one document's access levels in place.
8. **Holds at the end:** the type set the way they meant, and proof on screen of what that dealer reads.
9. **Everyone else:** nobody is notified. A type that had no tick and gets its first one reads its files in the
   background (the file's "Read by AI" row shows progress), as switching a type on does today. The next WhatsApp
   question uses the new ticks.

## Phase 2 - backend `[BE]` / `[T]`

- **DAS-BE-1** Given main's alembic head, when the lane migration runs, then `attachment_types` has
  `ai_read_staff BOOLEAN NOT NULL DEFAULT false` and `ai_read_codes JSONB NOT NULL DEFAULT '[]'`; the revision id is
  at most 32 characters and chains onto main's single head. `ai_audience` stays in the table, unread (dropped later,
  backlog).
- **DAS-BE-2** Given types with `ai_audience` off / staff / dealer / public and an access type catalogue holding
  active and inactive codes, when the migration runs, then: off -> (false, []); staff -> (true, []); dealer -> (true,
  every ACTIVE code except `end_user`, in catalogue sort order); public -> (true, every ACTIVE code).
- **DAS-BE-3** `[T]` **Carry-over, no change.** Given seeded data covering every audience; codes including the office
  codes, `end_user` and an inactive code; files whose levels are all codes, one brand pair, only `end_user`, and an
  inactive code; files in the contact's company, another company and shared (NULL); contacts with several codes,
  only `end_user`, only an office code, no code, no company: the set of (contact, document) pairs a contact may read
  BEFORE the migration (today's rule, `knowledge_service.py:692-703` + company) equals the set AFTER (new rule), and
  each type's staff readability is unchanged. Owner requirement (1 Nov): also run on a dev-copy migration with
  before/after reader counts per type x contact, zero differences, posted as a crew-note.
- **DAS-BE-4** Given a contact with active codes C, a type with ticks T and a file with levels L, when
  `search_for_contact` runs, then the file can be returned only if some code is in C AND T AND L (the SAME code), and
  the company rule is unchanged. Examples: T=[dealer], L=[end_user], C={dealer,end_user} -> not returned;
  T=[mocha_dealer], L=all, C={mocha_dealer} -> returned; T=[dealer] and C={sorento_office} -> not returned (an
  office code reads only when ticked).
- **DAS-BE-5** Given a contact with no active code, then nothing is returned (unchanged); given C has codes but none
  is ticked on any type, then nothing is returned.
- **DAS-BE-6** Given staff `search()` with `resource.attachments.view`, then passages come only from types with
  `ai_read_staff` true; a type with codes ticked and Staff unticked gives staff nothing; hand-off team names come
  only from Staff-ticked types. Permission behaviour unchanged (denied without it).
- **DAS-BE-7** A type is "AI on" when `ai_read_staff` is true or `ai_read_codes` is not empty. `queue_read` and
  `read_block_reason` use it (an Off type: "The AI does not read files of this type."). `update_type` queues the
  type's unread or failed files when the type goes from not-on to on (first tick), as today; removing the last
  tick queues nothing.
- **DAS-BE-8** Given `PUT /api/v1/resources/attachment-types/{id}` with `ai_read_staff`, `ai_read_codes` or
  `is_direct_access`, then it saves them (partial update; omitted fields untouched); a code not in the catalogue or
  inactive -> 400 with a readable message naming it; duplicates are stored once, in catalogue order; the response
  carries `ai_read_staff`, `ai_read_codes`, `is_direct_access` and no `ai_audience`; create accepts the two AI fields
  (default false / []). Without `resource.attachment_types.edit` -> 403.
- **DAS-BE-9** Given `GET /api/v1/resources/document-access` with `resource.attachment_types.view` (403 without),
  then the response is `{access_types: [{code, name}] (active, sort order), contact: null, rows: [...]}` with one row
  per type: `id, type_name, is_shared, is_direct_access, grant_count, file_count` (not deleted), `readable_count`
  (not deleted, filename ends .pdf or .docx, the reader's own rule `knowledge_service.py:341-342`),
  `ai_read_staff, ai_read_codes, reach` (`{code: readable documents whose levels hold the code}` for each active code),
  `preview: null`. File counts cover every company the caller is granted (`company_scope=grants`, BE
  `services/company_scope_resolver.py:556`), never a company they are not.
- **DAS-BE-10** Given `contact_id` on the same endpoint, the caller also needs `user_management.contacts.view` (403
  without). `contact` = `{id, name, runs_as: "contact"|"staff", agent_on, access_types: [active codes], companies:
  [{id, name}], blocked: null|"no_access_type"|"no_company"|"ambiguous"}`, where `agent_on` and `ambiguous` follow
  `chatbot/agent/access.py:75-82,112` and the codes `_active_access_codes` (:171-188). Each row's `preview` =
  `{verdict, reads, total, no_shared_code, other_company}`, verdict one of `reads`, `off` (no tick), `staff_only`
  (Staff ticked, no code), `not_ticked` (no contact code ticked), `no_documents` (readable_count 0), `staff_reads` /
  `not_for_staff` (runs as staff), or the contact's `blocked` value. `reads` counts documents through the SAME
  predicate function `search_for_contact` uses (one function, not a copy), restricted to the contact's companies or
  shared; `no_shared_code` and `other_company` split the rest. A parity test seeds chunks and asserts `reads` equals
  the distinct documents `search_for_contact` can return.
- **DAS-BE-11** Given `GET /api/v1/resources/document-access/{type_id}/documents?contact_id=&page=&limit=`, then it
  lists the type's readable documents (`id, original_filename, access_levels, company_name` or null for shared,
  `ai_read_status`, `verdict`: `reads|no_shared_code|other_company|<blocked>`|null without a contact), ordered by
  filename, `limit` default 50 and at most 200, with `total`; unknown type -> 404; same permissions as DAS-BE-9/10.
- **DAS-BE-12** `[T]` Global guards run: `tests/test_list_pagination_limit.py`, `tests/test_schema_uuid_id_principle.py`.

## Phase 2 - frontend `[FE]` / `[UX]`

- **DAS-FE-1** Sidebar Resource Management shows **Document Access** after Attachment Types for a user with
  `resource.attachment_types.view` (`config/menu.config.tsx`, both menus that list Attachment Types); the route is
  `/resource-management/document-access`.
- **DAS-FE-2** The page: `PageHeader` "Document Access", no CTA, no subtitle; a DataGrid (`tableLayout fixed,
  columnsResizable`, `columnResizeMode onChange`, explicit sizes, long text `truncate` + `title`) with columns Type
  (name; "Shared · N files"), Documents ("N readable" or "none readable"), the preview column when a contact is
  picked, Staff, one column per active access type (header on two lines), Sent as a file ("Direct access" Badge,
  "Granted to N"). Rows sort by readable documents, then name. Toolbar: search by type name, an "AI reads" filter
  (any / on / off, clearable `SearchableSelect`), **Preview as**. Type column stays visible on horizontal scroll.
- **DAS-FE-3** A tick cell is a checkbox; a ticked cell whose reach is below the readable count shows "reach/readable"
  in the warning colour with a title. Clicking saves at once through the attachment-type update service; success
  toast `"<Type>: <Access type> can now read N documents."` or `"... no longer reads N documents."` (Staff: N = the
  readable count); an error shows the extracted message and the tick returns to its saved state. Without
  `resource.attachment_types.edit` the ticks are read-only.
- **DAS-FE-4** **Preview as** is a clearable `SearchableSelect` with server search over contacts (shows the contact
  name, never an id). Picking one shows a strip (Runs as, Agent on WhatsApp, Access types, Companies) and the
  preview column: a Badge pill with the verdict text ("Reads 5 of 15 · 2 no shared access type, 8 other company",
  "Not ticked for End User", "No access type", ...), and highlights that contact's access-type columns. Hidden for a
  user without `user_management.contacts.view`.
- **DAS-FE-5** Clicking a row opens a `Sheet`: type name + "Shared" Badge, "N files · M readable", **Who can read**
  chips (same save + toast as DAS-FE-3), **Documents** (file name, access levels editable through the existing
  `AccessLevelsMultiSelect` and attachment update, company or "Shared", verdict for the previewed contact,
  paginated), **Sent as a file** (Direct access `Switch` saving `is_direct_access`, toast; "Granted to N
  contacts").
- **DAS-FE-6** The Attachment Type dialog no longer shows "AI can read"; "Escalate to" stays; create and update no
  longer send `ai_audience`.
- **DAS-FE-7** `[UX]` Usable with no clipped control and no horizontal page scroll at 375px (rows render as cards,
  chips wrap, the preview pill wraps) and at 1280px. Loading: grid skeleton. Error: the extracted message in the
  grid body. Search with no match: heading "No types match" + hint, no button. Nothing animates except the existing
  Sheet open/close and the toast (no new motion).
- **DAS-FE-8** No UUID is shown anywhere on the page or sheet.

## Docs `[T]`

- **DAS-DOC-1** `documentation/user-guides/system-management/ai-reads-uploaded-documents.md` describes the Document
  Access page (ticks, preview, sheet) and the one-sentence rule; `chatbot-agent-on-whatsapp.md` and
  `chatbot-console-agent-mode.md` no longer name the old Off / Staff only / Dealers / Everyone options. Same PR.
