# CARD SAMPLE-FROM-QUOTE: a sample request starts from the project's quotation

Status: card filed, waiting on owner answers and on #1953 (PORTAL-P4-REQUESTS) merging. Track: M lane
(not small-fix: a new read endpoint on the portal surface, possibly a migration, see Q5).

Source: owner team meeting 29 Oct 15:40 (Project Sales). A sample request pulls ALL items of the
project's quotation into its item list by default; the user deletes the lines not needed instead of
typing lines by hand. Standing rule (owner 28 Oct, #1953): the CRM create/edit/view forms ARE the
portal forms, the same component. So the pre-fill is built once, inside that single shared form
(`app/(auth)/portal/components/SampleRequestForm.tsx`), not as a helper called from two forms
(crew review, 29 Oct).

## Where things are (main ec29a81c)

- Both forms already share the line table and its delete control:
  `components/common/SampleRequestLines.tsx:162` ("Remove line", Trash icon) and the shared state
  helpers `lib/sample-request-form.ts` (`blankLine` :87, `stateFromDetail` :97, `payloadFromState` :138;
  rows without a product are dropped from the payload, :85).
- CRM form: starts with one blank row
  `app/(protected)/project-sales/sample-requests/components/SampleRequestForm.tsx:95`; `?project_id`
  seed :118-139; project picker :264-280; Add item :367.
- Portal form: one blank row `app/(auth)/portal/components/SampleRequestForm.tsx:87`; project picker
  :295-317; Add item :414. On #1953's head (`crew/portal-p4-requests`, a32591c06c) the CRM
  `SampleRequestForm` becomes a switch: a salesperson limited to their own requests gets this
  portal component (wrapped in `MyRequestClientProvider`, new requests via `NewOwnSampleRequest`
  seeding `project_id` from `?project_id=`), everyone else keeps `StaffSampleRequestForm`.
- Quotation model: project -> `quotation_documents` (one letterhead, `models/projects.py:1073`) ->
  scopes `quotations` (:1398, each with its own outcome) -> `quotation_versions` (:1456, current =
  MAX(version_no), `project_quotation_service.py:123`) -> `quotation_lines` (:1500). What the customer
  holds is an ISSUE (R1, R2, ... `quotation_issues` :1215, current = MAX(issue_no)) recording which
  version of each scope went out (`quotation_issue_scopes` :1355).
- A quotation line names a product, a product SET (`product_set_id`, parts frozen in
  `set_parts_snapshot`), or neither (off-catalogue free text, `product_id` nullable :1525). Lines may be
  rate-only alternates (`is_rate_only`).
- Sample request lines: `product_id` NOT NULL, `qty >= 1` (`models/sample_request.py:162-171`). A NEW
  product id must be active or save fails with `SAMPLE_REQUEST_PRODUCT_INVALID`
  (`services/sample_request_service.py:185-219`).
- Portal project access: `assert_portal_project_allowed` (`sample_request_service.py:251`). There is no
  portal endpoint that reads quotations today.

## Rules (proposed)

1. **When.** A NEW sample request whose project gets set (URL seed or picker, CRM or portal) and whose
   item list is untouched (no row has a product) is filled with the chosen quotation's product lines.
   A project with no quotation, or a quotation with no product lines, leaves the one blank row as
   today.
2. **Never on edit.** Opening an existing draft never re-fills, even if its project's quotation
   changed since.
3. **Project changed after pre-fill.** If the user has not touched the pre-filled rows, they are
   replaced by the new project's lines. If the user deleted, added or edited any row, the rows stay as
   they are (we never throw away their work). Clearing the project leaves the rows.
4. **Which lines.** Every line of the chosen quotation that resolves to an active catalogue product,
   in quotation order (scope order, then line order), rate-only alternates included. A product SET
   line contributes its parts' products. Lines with no product (free text) and lines whose product is
   inactive are left out and listed in a one-line note under the table (Q3).
5. **Same product twice** (two scopes, or a set part that is also its own line): one row (Q4).
6. **Qty** per row: 1 (Q2). **Remark**: empty.
7. **Each row** keeps the existing Remove line control; Add item still adds a blank row.
8. **Long quotations.** No cap: a 200-line quotation gives up to 200 rows (fewer after Q4). The table
   already scrolls; nothing to paginate.
9. **One form, one code path.** The pre-fill lives in the shared portal `SampleRequestForm`, so the
   portal and the CRM (My Requests, through #1953's injected client) run the same code. It reads one
   backend route at the portal-relative path, which #1953's fetcher maps to `/api/v1/my-requests`
   for the CRM; the route reuses `assert_portal_project_allowed` and returns product id, code and
   description only (no prices).

## Examples (masked)

The cloud sandbox has no access to the dev database, so these are the five shapes the model allows,
not counted rows. Crew can confirm each exists on dev with the query at the end before the build.

| # | Project shape | Pre-filled rows | Note shown |
|---|---|---|---|
| A | Project P-A, one document Q-A, issued R1 with 2 scopes (8 + 4 product lines) | 12 rows, qty 1 | none |
| B | Project P-B, one document revised R1 -> R3; a second document Q-B2 (showroom) never issued | rec: picker shows Q-B1 (R3) and Q-B2 (draft); default Q-B1 R3 lines | none |
| C | Project P-C, no quotation | 1 blank row (today's form) | none |
| D | Q-D R1 has 10 lines, 2 of them free text ("Bespoke vanity top") and 1 discontinued SKU | 7 rows | "3 quotation lines not added: 2 have no product, 1 product is inactive" |
| E | Q-E R2: same basin in scope "Type A units" and "Type B units", plus a set whose part is that basin | 1 basin row (Q4 a) | none |

```sql
-- Read-only. One row per quotation document: how many documents its project has, its latest issue and
-- the line mix ON THAT ISSUE only (never-issued documents show latest_issue NULL and zero counts).
-- Masking: ids are hashed to 8 chars; no names, titles or document numbers are selected.
WITH latest AS (
  SELECT DISTINCT ON (i.document_id) i.document_id, i.id AS issue_id, i.issue_no
  FROM projects.quotation_issues i
  ORDER BY i.document_id, i.issue_no DESC
)
SELECT left(md5(d.project_id::text), 8)                                   AS project,
       left(md5(d.id::text), 8)                                           AS document,
       COUNT(*) OVER (PARTITION BY d.project_id)                          AS docs_on_project,
       lt.issue_no                                                        AS latest_issue,
       COUNT(DISTINCT s.quotation_id)                                     AS scopes,
       COUNT(l.id)                                                        AS lines,
       COUNT(l.id) FILTER (WHERE l.product_id IS NOT NULL AND p.is_active) AS active_product_lines,
       COUNT(l.id) FILTER (WHERE l.product_id IS NOT NULL AND NOT p.is_active) AS inactive_product_lines,
       COUNT(l.id) FILTER (WHERE l.product_set_id IS NOT NULL)            AS set_lines,
       COUNT(l.id) FILTER (WHERE l.product_id IS NULL AND l.product_set_id IS NULL) AS free_text_lines,
       COUNT(l.product_id) - COUNT(DISTINCT l.product_id)                 AS repeated_product_lines
FROM projects.quotation_documents d
LEFT JOIN latest lt ON lt.document_id = d.id
LEFT JOIN projects.quotation_issue_scopes s ON s.issue_id = lt.issue_id
LEFT JOIN projects.quotation_lines l ON l.version_id = s.version_id
LEFT JOIN products p ON p.id = l.product_id
GROUP BY d.project_id, d.id, lt.issue_no
ORDER BY project, latest_issue NULLS LAST;
-- Projects with no quotation document at all (example C):
SELECT COUNT(*) AS projects_without_quotation
FROM projects.projects pr
WHERE NOT EXISTS (SELECT 1 FROM projects.quotation_documents d WHERE d.project_id = pr.id);
```

## Questions

**Q1. Which quotation?** A project can hold several documents, each with revisions R1..Rn, and a
document may exist that was never issued.
(a) The latest ISSUE of the document; when the project has more than one document, a quotation picker
appears above the items (default: the most recently issued); a never-issued document uses its scopes'
current versions. (b) Latest issue only; never-issued documents are ignored, no picker (first issued
document wins). (c) Current working versions of every scope of every document.
**Rec: (a)**: the issue is what the customer holds and what the samples are for; the picker only shows
when there is a real choice.

**Q2. Sample qty per row?** (a) 1. (b) The quoted quantity (often hundreds of units).
**Rec: (a)**: a sample is one piece; the user raises it where needed.

**Q3. Quotation lines with no product (free text) or an inactive product?** (a) Left out, with a
one-line note under the table naming how many and why. (b) Left out silently. (c) Added as a row with
an empty product the user must fill or delete.
**Rec: (a)**: a sample line must name an active product (`sample_request_service.py:185`), so (c)
blocks submit until fixed; (b) hides what was skipped.

**Q4. Same product in two scopes (or as a set part and its own line)?** (a) One row. (b) One row per
quotation line.
**Rec: (a)**: one sample of the product is enough; duplicates are just more deletes.

**Q5. Store the source quotation on the request?** (a) Yes: nullable `sample_requests.quotation_issue_id`
(FK `quotation_issues`, SET NULL), shown read-only on the detail page. This is a MIGRATION, and the
lane would publish the idempotent SQL for the dev copy. (b) No: the request only lists products, as
today.
**Rec: (a)** if the owner wants "which revision did we sample from" answerable later (the same reason
`project_samples.quotation_version_id` exists, `models/projects.py:1606`); otherwise (b) keeps the
lane migration-free. Note (a) needs a NULL for Q1's never-issued fallback.

## UI

The form keeps its layout. Pre-filled rows render in the existing `SampleRequestLines` table with its
existing Remove line control; nothing new there. The only new elements are Q1 (a)'s quotation picker
(an existing `SearchableSelect`, shown only with more than one document) and Q3 (a)'s note (one muted
line of text). If the owner answers Q1 (b) and Q3 (b), the change is pure reuse and the lane asks to
skip the mock (owner's 29 Sep exception); otherwise a Lavish mock of the picker + note with the
element-to-component map comes before the build.

## Build plan (after answers + #1953)

- BE: `sample_request_service.quotation_prefill(db, project_id, document_id=None)` returning
  `{documents: [...], lines: [{product_id, product_code, description}], skipped: {no_product, inactive}}`;
  staff route under `api/v1/projects/sample_requests.py`, portal route under
  `api/v1/public/portal_sample_request.py` behind `assert_portal_project_allowed` (security-reviewer
  joins: portal surface). #1953 mounts portal routes on `/api/v1/my-requests` too.
- FE: built into the single shared `app/(auth)/portal/components/SampleRequestForm.tsx` (its project
  picker onChange and its seeded `project_id` on first paint), nothing in a per-form helper. The
  staff-only `StaffSampleRequestForm` that #1953 keeps for non-limited users is not touched unless
  crew rules otherwise (see crew-note on the PR).
- Tests red-first: pytest for the service (A-E shapes, issue vs. never-issued, portal refusal on a
  foreign project), vitest per form (pre-fill on project set, no re-fill on edit, project change rules,
  delete a pre-filled row).
