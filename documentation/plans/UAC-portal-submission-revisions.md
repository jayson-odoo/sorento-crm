# UAC - Portal submission revisions

Status: **IMPLEMENTED**, in review on PR #122. The earlier "implementation on hold at the user's request" note is superseded - the hold was lifted, the feature was built across all three adapters, and it is now in live testing. Grilled 2026-08-10 (sections A-bis, C-bis, F-bis, F-ter, G7, I2a, J4, J5 came out of that pass), then reviewed by the user in Lavish 2026-08-10 (round 2 decisions below).

## Round 2 decisions (Lavish review, 2026-08-10)

| # | Decision | Note |
|---|---|---|
| Q1 | Enable **PR and SF** with the same statuses as SI | Conflicts with the earlier "SI only this round" decision - see open question 1 |
| Q2 | Reuse the **assignment** preference pair | Plus: the notification must carry real revision context, not generic assignment copy |
| Q3 | Revision **allowed** while handling-locked / escalated | As recommended |
| Q4 | **Suffix the document number per revision** (SI-26-0184-R2) | Overrides the earlier recommendation - see AC N |
| Q5 | Blocked on all three terminal statuses | As recommended |
| Q6 | **Snapshot the superseded purchasing answer, clear it on the entity** | As recommended |
| Q7 | Fence **every office write on every revisable form** | Wider than recommended |
| Q8 | Generic wording to the contact | Copy says "the office", never "purchasing" - PR/SF are not purchasing |

## Round 3 decisions (Lavish review, 2026-08-10)

| Decision | Outcome |
|---|---|
| Scope conflict | **Enable PR and SF live from day one, alongside SI.** The earlier "SI only this round" is superseded. All three adapters wired and enabled at launch; complaint keeps a disabled-but-present config row. |
| "Send from any status" | **Wide - block sends outside the allowed statuses**, qualified by the user's own note: *"we only got two places for response: complaint and stock inquiry ... of course the chat function is still available."* Resolved as section O below: the **response** is gated, ordinary chat is not. |
| Document number suffix | **Everywhere, integration payloads included.** User note: *"not too worried about integration from n8n or mcp side cause there isn't any use case now."* See N5/N6 - one live inbound consumer does exist (the external-API resubmit-by-number path), and it is handled. |

## Round 4 correction (2026-08-10)

The user is right that **public view links are retired** - "no more system view link, we use either system view or portal link". The routes confirm it: they sit behind `require_public_view_links_enabled`. `external/view_link.py` is therefore **not** a reason to do anything, and the earlier N6 justification naming it is withdrawn.

N6 itself stands, on better evidence: the **external API create endpoints** key off the document number to decide create-vs-resubmit. See the rewritten N6.

Plus four review notes, folded in as ACs: revise entry point belongs in the long-press preview card (AC B6); attachments and chat stay exactly where they are today (AC H2a); the revision timeline follows the existing packing-list timeline pattern (AC G8); and the "chat can be sent from any status" permissiveness is removed rather than only fenced (section O).

## Round 5 decisions (live testing on PR #122, 2026-08-13)

Three changes reported by the user while testing a live stock inquiry.

| # | Report | Outcome |
|---|---|---|
| R5-1 | *"I can see the revision history but I should be able to view the entire form in the previous revision"* | **Full-form view, portal side.** The history showed only the per-field diff. Each entry now opens the WHOLE form at that version, read-only. See AC G9. |
| R5-2 | *"don't need this at least 5 characters limitation"* | **Minimum length removed**, both sides. Still required, still max 2000. See the rewritten D1. |
| R5-3 | *"i supposed to be able to see the exact form across multiple revisions"* (office route) | **Same view, office side**, through the shared timeline so both sides cannot drift. See AC H6. |

R5-1 and R5-3 are one capability in two places, so they ship as **one shared component** (`RevisionSnapshotDialog`), mounted by both `RevisionTimeline` (office) and `RevisionHistory` (portal). Every form type the shared timeline serves - stock inquiry, purchase request, sponsorship form - gets it at once, since all three office routes already read the same `list_revisions` payload.

## Round 6 decisions (live testing on PR #122, 2026-08-13)

Four more changes after the user tested round 5. Reaching the history, and getting it off the screen and onto paper.

| # | Report | Outcome |
|---|---|---|
| R6-1 | The office history sits down the page and has to be scrolled to | **Revisions becomes its own tab** beside Details, through the existing `FormDetailWithSLATabs` `extraTabs` seam. See AC H7. |
| R6-2 | Same problem on the portal | **Tabbed portal detail** in the portal's own idiom (no protected-side component crosses into the public bundle). See AC G10. |
| R6-3 | *"must be able to enjoy the same printing print / download PDF / Excel function as the main form, so it can be printed separately"* | **Any single revision exports as PDF and Excel** in the main form's own format, rendered from that revision's snapshot. See section P. |
| R6-4 | A printout should tell the whole story | **"Include revisions"** on the main export, shown only when it can do something, default on. See AC P4. |
| R6-5 | *"i want the tab to be nicer, like you see our products page, the tab is very nice"* | **Both tab strips adopt the existing `variant="line"` style**, the one the product detail page uses and 12 other pages already share. No new styling was written. See AC G10a. |
| R6-6 | *"i want the revise button to be on the right, same with the 2 of 3 revisions left, and I want it to be in gear button so it is not so attention seeking"* | **Revise moves into a right-aligned gear menu** on the submission detail, keeping the prominent button where a gear would read badly. See the rewritten AC B2a. |

## Round 7 decisions (live testing on PR #122, 2026-08-13)

Three more changes after the user tested round 6, all of them about a revision being
treated as a second-class copy of the form rather than the form.

| # | Report | Outcome |
|---|---|---|
| R7-1 | *"if include revision, then the latest revision don't need to be included, cause it will be the first one getting printed ma, if we print current revision again then will be double print"* | **The newest lineage entry gets no page (PDF) or sheet (Excel) of its own.** It IS the version the current form prints, so the document was repeating page 1. Its label, submitter and reason move onto the current form page / sheet. The report is about the DOCUMENT, so it lands on both exports, not on the PDF alone. See the rewritten AC P4a. |
| R7-2 | A revision's attachments could not be previewed from the office side | **Preview inside the snapshot view, on BOTH sides.** H6a's premise was wrong: the office timeline had no preview at all. See the rewritten AC H6a. |
| R7-3 | *"we using same printing function for all revisions"* (believed, not true of images) | **A revision page embeds its own photos**, from that version's own attachment set, through the same helpers the current form uses. See the rewritten AC P3. |

The governing choice in round 6 is that **no second document layout is created**. A revision prints through the same renderer the live form prints through, fed a different value source: the PDF services grew a snapshot reader, and the client-side Excel builders are handed a snapshot adapted into the entity shape they already take. A separate "revision layout" would drift from the form within one release and then the paper record would disagree with the screen.

Slug: `portal-submission-revisions`
Plan: `documentation/plans/PLAN-portal-submission-revisions.md`

**Scope (final):** generic engine with **three adapters wired and enabled** - `stock_inquiry`, `purchase_request`, `sponsorship_form`. `complaint` ships with a config row, disabled and flippable.

---

## Journey (Phase 0 - governing)

### Actor

A contact (salesperson / dealer) who already submitted a **stock inquiry** through the contact portal and now needs to change it. They arrive from their WhatsApp portal link or a bookmark, landing on `/portal/stock_inquiry/{id}`.

### What the system already knows about them

Everything. The portal token resolves the contact; the submission carries every field they typed, its current status, its attachments, how many revisions they have already used, and whether this form type permits a revision at this status. **Nothing on this journey is re-asked.** The only thing the system cannot know is *why* they are changing it - so that is the only thing it asks for.

### Steps

**Step 1 - They open their submission.**
They see the status pill and everything they submitted. If a revision is possible, one primary action: **Revise**, with the budget stated next to it in plain words ("2 of 3 revisions left"). If it is not possible, no button and one short line saying why ("This inquiry has been closed", "You have used all 3 revisions", "This form cannot be revised"). Never a disabled button with no explanation.

**Step 2 - They edit.**
The revise form opens **pre-filled with the current values** - same fields, same lookups, same attachment list as the original submission. They change what they need, add or remove attachments.

**Step 3 - The single decision: the reason.**
One required field, "What changed, and why?". Cannot be blank. This is the *only* new thing the journey asks for, because it is the only thing the system cannot derive.

**Step 4 - They confirm, knowing the consequence.**
A confirm dialog states it in the user's own terms, not ours:
> "Send revision 2? The purchasing team will stop work on the current version and this inquiry goes back for Project Sales approval. You will have 1 revision left."

**Step 5 - They are told where it now stands.**
Success state, and their submission now reads **"Revision 2 - Pending project sales approval"**.

**Step 6 - They can always look back.**
From step 1 and forever after, **Revision history** is one tap away: the original plus every revision, each with its reason, its timestamp, what changed since the version before it, and the attachments as they stood at that moment - previewable in place, never a raw new browser tab.

### What everyone else is told, automatically

| Who | How | What |
|---|---|---|
| The handler mid-work (assignee of the voided SLA stage) | In-app + email / WhatsApp per their prefs | "SI-xxxx was revised by \<contact\>. Your stage was voided - stop work. Reason: ..." |
| The new stage-1 assignee (Project Sales) | Existing assignment notification | Normal "assigned to you" - no new path |
| Any office user opening the inquiry | Banner at the top of the detail page | "Revision 2 submitted \<when\> by \<contact\>. Reason: ... Work restarted at Project Sales." |
| Any office user scanning the list | Column badge | "Rev 2" |

### What the contact holds at the end

A single inquiry, at revision N, whose full lineage they can read at any time without asking anyone.

---

## Acceptance criteria

Traceability: every AC names the journey step it serves.

### A. Revision policy (config) - serves step 1

- **A1** Global default lives in `system_settings`: `portal_max_revisions` (int, NOT NULL, default `2`) and `portal_revisions_enabled` (bool, NOT NULL, default `true` - kill switch). Both editable in **Settings**, and both added to **BOTH** manual serializer builders (GET dict AND `SystemSettingUpdate`), per the `system_settings` singleton rule.
- **A2** Per-form override lives in a new `portal_revision_configs` table, one row per portal submission type (`stock_inquiry`, `complaint`, `purchase_request`, `sponsorship_form`), with: `is_enabled`, `max_revisions` (NULL = inherit global), `allowed_statuses` (JSONB array), `restart_stage_code` (NULL = first stage of the type's SLA chain).
- **A3** Effective policy = `portal_revisions_enabled AND config.is_enabled`. **A missing config row means disabled** (fail closed).
- **A4** Effective cap = `config.max_revisions` if not NULL, else `system_settings.portal_max_revisions`. A cap of `0` means revisions off for that type regardless of `is_enabled`.
- **A5** Seeded by migration, **one row per portal type, all four present** so any of them is one toggle away:
 - `stock_inquiry` - **enabled**, `allowed_statuses = ["pending_project_sales","pending_purchasing","responded"]` (revisable **after** purchasing has responded - explicit user decision), `restart_stage_code = NULL`.
 - `purchase_request`, `sponsorship_form` - **enabled live from day one** (round 3), with their own chain's equivalent statuses. This supersedes the earlier "SI only this round" scope: all three adapters ship wired and on. The cost is carried knowingly - PR and SF bring line items, their own approval chains, their own PDF exports, their own stage-output fields to invalidate, and their own test matrices.
 - `complaint` - **disabled**, but the row exists and is flippable. The user's words: "complaint don't need this, but I just need it to be ready when the time comes." A missing row would mean re-running a migration to turn it on; a disabled row means ticking a checkbox.
- **A6** Admin UI: Settings gains a "Portal revisions" section - the two globals plus a table of one row per type (Enabled / Max / Allowed statuses multi-select / Restart stage). Editing is a modal, per the CRUD UX standard.

### A-bis. What a revision may change

- **AB1** The editable field set on revise is the type's existing portal edit whitelist (`_editable_fields`) **minus a frozen list**. One whitelist, one place, no fork.
- **AB2** For stock inquiry the **requestor** (`salesperson_contact_id` / `salesperson`) is **frozen** on revise. It is the CS pin routing key: letting a revision change it silently re-routes the inquiry to a different person's queue mid-life, which is a reassignment disguised as an edit. Changing the requestor stays an office action.
- **AB3** `respond_inbox_url` remains excluded, as on every other portal write path.

### B. Revise eligibility - serves step 1

- **B1** `GET /submissions/{kind}/{id}` returns a `revision` block: `{ enabled, allowed, used, max, remaining, blocked_reason }`. One call, no extra round trip.
- **B2** The Revise action renders **only** when `allowed` is true. When false, exactly one human sentence from `blocked_reason` renders in its place. Blocked reasons are distinct and specific: type disabled / status not permitted / cap reached / submission still a draft / submission voided.
- **B2a** (round 6) The action has **two presentations, one component**. On the submission detail it renders as a **right-aligned gear menu** (the shared `DetailActionsMenu`) holding a single Revise item, with the remaining-count text beside it: revising is the exception, not the errand the contact came for, and a primary button at the top of their own form competes with the form for attention. In the long-press preview card (B6) it keeps the **prominent button**, because there the card exists precisely to offer that action and a gear would hide it. Same component, a `variant` prop, so the two can never drift into different behaviour. The blocked sentence (B2) renders in place of either, right-aligned in the menu form.
- **B3** Remaining count is shown next to the action whenever `remaining` is finite ("2 of 3 revisions left"), on the same line as the action in both presentations.
- **B4** Server re-checks the full policy on `POST .../revise` and returns 422 with the same human sentence. The FE gate is a convenience, never the enforcement.
- **B5** A submission still in draft (`portal_draft_at IS NOT NULL`) is **not** revisable - it is editable, which is the existing path. Revision applies only to submitted work.
- **B6** The Revise action appears in **two** places, driven by one policy block: the submission detail page, and the **long-press preview card** (`SubmissionPreviewDialog`, opened from `PortalLanding`'s `onLongPress`). A contact who long-presses a row to peek at it can act from there without opening the record first. Same eligibility rules, same blocked sentence, in both surfaces.

### C. Counters - serves step 4

**Two separate concepts. Do not collapse them into one number.**

- **C0** `version_no` = **every** submitted version, for history. `revision_no` = **contact-initiated revisions only**, for the cap. A reject → resubmit advances `version_no` and leaves `revision_no` alone.
- **C1** The cap counts contact-initiated revisions only. An office-side reject → contact resubmit does **not** burn a revision (explicit user decision). The existing reject/reopen/resubmit behaviour is untouched.
- **C2** `revision_no` starts at `0` (original submission) and increments by exactly one per successful revise.
- **C3** `used = revision_no`, `remaining = max(0, cap - used)`. At `remaining == 0` the action is blocked with "You have used all N revisions".
- **C4** Every submitted version writes a history row, **including a resubmit after rejection** (`kind = "resubmission"`, no cap consumed, reason = the office rejection it answers). Without this the contact's history silently skips a version they actually sent.
- **C5** Two Revise submissions racing (double tap, retried request) must produce **one** revision. Enforced through the existing `idempotency_middleware` plus a server-side guard on `revision_no`: a revise carrying a stale `revision_no` is rejected, not applied twice.

### C-bis. Revision fence - protects step 5 from the office side

- **CB1** Once a revision voids a stage, no office action may land against the version it superseded. Office write endpoints on a revisable entity carry the `revision_no` the user was looking at, and the server returns **409** on mismatch with "This inquiry was revised while you were working on it. Reload to see revision N."
- **CB2** This is required, not defensive: the stock inquiry respond path today explicitly allows a send **from any status** (`procurement_service.py`, "Chat can be sent from any status"), so voiding the tracker alone does **not** stop a stale tab from messaging the contact and stamping `last_responded_*`.
- **CB3** Coverage: **every office write endpoint on every revisable form type** (Q7), not just stock inquiry. Read endpoints are unaffected. Implemented as one shared dependency so a new revisable form inherits the fence rather than re-deriving it.
- **CB4** The fence is generic; the set of *revisable* types is config-driven, so a type with `is_enabled = false` costs nothing at runtime.
- **CB5** The lifecycle `status` is **not editable through an edit endpoint** on any revisable form - it moves only through the workflow actions. `PUT /purchase-requests/{id}` and `PUT /stock-inquiries/{id}` both refuse a payload whose `status` would MOVE the record, with a 422 naming the actions to use instead. **Not** a silent drop: that answers an n8n / MCP caller who had been walking the lifecycle through this endpoint with `200` and nothing changed, which is the worst failure mode available. A payload echoing the record's CURRENT status moves nothing and still saves, so a read-modify-write round trip of the whole entity keeps working (same rule as O1c). Both schemas still declare `status` - removing the field would change nothing, since an undeclared field is ignored by default - so the refusal has to be explicit.

### D. The reason - serves step 3

- **D1** Reason is **required**, max 2000, with **no minimum length** (round 5). Blank or whitespace-only is rejected client- and server-side; any non-empty reason after trimming is accepted. The earlier "min 5 chars" floor is withdrawn at the user's request - it rejected honest short answers ("typo", "wrong qty") for no gain, since a contact intent on writing nothing useful defeats a 5-character floor anyway. Both sides answer with the same sentence, "Tell us what changed and why."
- **D2** The reason is stored on the revision row, is immutable, and is shown verbatim in: the office banner, the office Revisions tab, the portal history, and the handler notification.

### E. Confirm before sending - serves step 4

- **E1** Submitting a revision opens an `AlertDialog` (never `confirm()`) whose body states all three consequences in the user's terms: current work stops, where it returns to, and how many revisions remain.
- **E1a** The copy says **"the office"**, never "the purchasing team" (Q8). Purchase requests and sponsorship forms do not route to purchasing, so a purchasing-specific sentence is wrong on three of the four types. The restart destination is named from config, not hardcoded.
- **E2** Cancelling leaves the edited form intact - no data loss, no save.

### F. Restart the flow - serves step 5

- **F1** On a successful revise, every **active** form-SLA tracker for that entity is **voided** with reason code `revised_by_contact`, and an event-log row is written per tracker (naive-UTC timestamps wrapped through `_to_aware_utc()` before entering the event-log payload).
- **F2** Any pending SLA takeover request against a voided tracker is voided too, mirroring the existing escalation path.
- **F3** The entity status is set to the restart stage (`pending_project_sales` for stock inquiry) and the stage-1 start event is emitted, spawning a fresh tracker chain through the normal assignment path (including its normal assignment notification).
- **F4** A voided tracker is excluded from overdue scans, escalation, and every "active tracker" query. It remains readable as history.
- **F4a** A voided tracker is **excluded from open-tracker and breach KPIs** on the dashboards, and retains `void_reason = "revised_by_contact"` so the exclusion is explainable rather than invisible. Leaving them in inflates the breach count every time a contact revises; dropping them without a reason code makes real breaches vanish with no audit trail. Neither is acceptable.
- **F4b** A revision does **not** re-open or disturb conversation SLA. Only form-SLA rows are touched, filtered through `conversation_tracking_scope()`.
- **F4c** The query that **identifies** the stages a revision is about to void is the SAME query that voids them (`FormSLAOrchestrator._open_form_trackers`): pinned to `FORM_SLA_TYPES` and passed through the negated conversation scope. Two queries answering "which stages of this row are open" differently is how a form row ends up matched by a conversation-keyed lookup, which this repo has already been bitten by - so there is one query, not two.
- **F5** The revision transaction is atomic: snapshot + counter + status + tracker void either all commit or none do. The handler notification (F6) is a **post-commit side effect**: best-effort, catch-and-warn, never raises, never turns a successful revision into a 500.
- **F6** The assignee of each voided tracker is notified: in-app always; email / WhatsApp gated by that user's existing **assignment** notification preferences (`notify_email_on_assignment` / `notify_whatsapp_on_assignment`) (Q2). WhatsApp additionally requires a linked `RespondContact`, as everywhere else.
- **F6a** The notification is **revision-specific, not recycled assignment copy** (Q2 note). It carries: the document number at its new revision, which revision this is, who submitted it, the reason verbatim, which stage was voided, and - where cheap to compute - what changed. A recipient must be able to act on the message without opening the record to find out why their work stopped.
- **F7** The notification links to the **in-system** detail page (`/procurement-management/stock-inquiries/{id}`), not the public `?token=` view - recipients are internal staff.

### F-bis. Stage output that the revision invalidates

- **FB1** A revision can arrive **after** purchasing has answered (SI is revisable at `responded` by explicit decision). That answer was priced against the superseded version and must never be read as an answer to the new one.
- **FB2** On revise, every stage-output field the restart invalidates is **snapshotted into the revision row and cleared on the entity**. For stock inquiry: `purchasing_response`, `last_responded_by`, `last_responded_at`.
- **FB3** The cleared answer is not lost - it renders inside its own revision entry in the history and the Revisions tab, attributed to the version it answered.
- **FB4** The invalidated field list is **adapter-declared** (`invalidated_on_revise`), never hardcoded in the engine.

### F-ter. Who gets told when nobody is assigned

- **FT1** If a voided tracker has no assignee, the notification goes to that stage's **team** at the tracker's tier, resolved through `AccessAgentService.resolve_team_with_tier_fallback`. A revision must never fail silently into nobody's inbox.

### G. Revision history, contact side - serves step 6

- **G1** A `portal_form_revisions` row is written on the **original submit** as `revision_no = 0` (reason NULL), and on each revise as `revision_no = N` carrying the **post-edit** snapshot.
- **G2** For submissions that predate this feature, revision 0 is backfilled lazily from current state at the moment of the first revise, flagged `is_reconstructed = true`, and labelled "Original (reconstructed)" in the UI so nobody reads it as a verbatim record.
- **G3** The portal detail page shows **Revision history** always - including when there is exactly one entry. Never hidden on "no revisions"; the empty-ish state reads "Original submission only".
- **G4** Each history entry shows: label (Original / Revision N), timestamp, submitter, reason, **what changed vs the previous version** (field label, old value, new value), and that version's attachments.
- **G5** History is strictly read-only from the portal. No edit, no delete, no re-submit-from-old-version.
- **G6** An attachment removed during a revision is **unlinked, not destroyed**, whenever an earlier revision references it - so history previews never 404. Portal attachment delete becomes unlink-if-referenced.
- **G8** The history renders as a **timeline**, following the existing packing-list timeline pattern (`PackingListDetail.tsx`, which also carries it as its own tab) rather than inventing a new visual language for the same idea.
- **G9** (round 5) Every history entry whose payload carries a snapshot offers **"View full form"**, opening the **complete form as it stood at that version**, read-only: every field with its label, the line items, and the attachments as they were - including a file a later revision removed. G4's per-field diff answers "what changed"; G9 answers "what did I actually send". The diff alone cannot, because a field untouched by that revision never appears in it.
- **G9a** The view renders **strictly from that revision's own stored snapshot**, never reconstructed from the live row. Reading today's values under an older version's heading would be a lie told confidently, which is worse than not offering the view. The `snapshot` dict already persisted per revision (G1) is sufficient - no new endpoint, no new table.
- **G9b** The field **labels and their order come from the backend adapter** (`snapshot_fields`), the same field list that labels the diff. A second label map on the frontend would drift from the adapter the first time a field was renamed, and would then mislabel a historical record. Contact FK columns (`*_contact_id`) are omitted - the human name sits in the sibling field, and no UUID reaches a screen (cursor rule).
- **G9c** The view is **read-only**: no inputs, no restore-from-this-version, no re-submit. G5 is unchanged.
- **G10** (round 6) The portal detail splits into **Details** and **Revisions** tabs when revisions are enabled for that type, so the contact does not scroll past their own form to find the history. When the type is disabled the page renders exactly the flat card stack it renders today, with no tab strip at all - a contact who can never revise is never shown a tab that would only ever be empty. The gate is the type being `enabled`, NOT this record being `allowed`: a contact who has used their last revision keeps the tab and the history it holds. The portal uses the shared `ui/tabs` primitive rather than importing `FormDetailWithSLATabs`, which belongs to the authenticated bundle.
- **G10a** (round 6) Both tab strips - the portal's and the office's shared `FormDetailWithSLATabs` - use the repo's existing **`variant="line"`** underlined style with a lucide icon per tab, the idiom the product detail page uses and that 12 other pages already share. Neither strip gets bespoke styling: the portal had been a 50/50 pill grid and the office the default grey pill strip, both minority forms, and a record's tabs should look the same wherever you are in the system. This is styling only, so it lands for every page the office wrapper serves (tickets, complaints, stock inquiries, purchase requests, sponsorship forms) at once. `FormDetailExtraTab` carries an **optional** icon, rendered only when the caller has one, so a caller with nothing to draw gets a label-only trigger rather than filler.
- **G7** Because removal unlinks, the per-entity attachment cap (`_check_quota` counts live `EntityAttachmentLink` rows) keeps counting the **current** version only. A contact revising three times does not burn a 10-file budget on files they already removed. This is a consequence of G6 and must be covered by a test, not left to luck.

### H. Revision visibility, office side - serves "what everyone else is told"

- **H1** The stock inquiry detail page renders a **revision banner** at the top whenever `revision_no > 0`: "Revision N submitted \<when\> by \<contact\>. Reason: ... Work restarted at Project Sales." Shared component, sibling to `RejectionReasonBanner`/`VoidBanner`.
- **H2** The detail page gains a **Revisions** tab. Per the CRUD UX standard the tab **always renders**, with an explicit empty state ("No revisions - this is the original submission") when `revision_no = 0`.
- **H2a** Revisions is an **addition only**. Attachments, chat and every existing section stay exactly where they are today (review note) - no re-ordering, no re-grouping, no moving chat into a tab. The Phase 1 mock that showed a re-tabbed detail page was wrong and is not the target.
- **H3** The Revisions tab shows the same lineage as G4, plus the voided-stage context: which stage was voided by each revision and who was working it.
- **H3a** A form can sit with **two stages open at once** (a purchase request with project sales and approval), and a revision voids all of them and tells all of their handlers (F1/F6). So the revision row records **every** voided stage - `voided_stages_json = [{stage_code, assignee_user_id}, ...]`, newest first - and the history payload exposes it as `voided_stages: [{stage_code, assignee_name}]`. The scalar `voided_stage_code` / `voided_assignee_user_id` stay populated with the newest stage, which is the common single-stage case every existing timeline renders. Recording only the newest under-reports a cancellation two people were just told about.
- **H4** The stock inquiry **list** shows a "Rev N" badge, sourced from a denormalized `revision_no` column - no per-row query.
- **H5** Office users cannot create, edit or delete revisions. The office side is read-only on this data.
- **H6** (round 5) The Revisions tab offers the **same full-form view as G9**, from the **same shared component** (`RevisionSnapshotDialog`), so the office and the contact can never be shown different renderings of one stored version - the single most damaging way this feature could fail, since the two sides would be arguing about a record they see differently. It therefore lands for **every form type the shared timeline serves** (stock inquiry, purchase request, sponsorship form) in one change, not stock inquiry alone: all three office routes already read the same `list_revisions` payload.
- **H7** (round 6) H2's tab is delivered through the **existing `FormDetailWithSLATabs` `extraTabs` seam**, not a second tab mechanism: the wrapper already inserts entity tabs between Details and SLA Tracking, and the complaint page already uses it. Tab order is Details, Revisions, SLA Tracking. The tab is shown when the **type** is enabled **OR** this record already has a lineage, read from one small authenticated endpoint (`GET /api/v1/forms-management/revision-configs/enabled`) that returns the effective per-type map - the existing config routes are admin-gated and a detail page is not an admin screen. Enabled therefore always shows the tab, carrying H2's explicit empty state for a record with no revisions yet, because a tab that appears and disappears per record teaches the user nothing. Disabled still shows it for a record that HAS revisions: the kill switch governs whether new revisions can be **created**, and hiding history the contact can still see in their own portal (G10 gates on the type, not on this record) would leave the two sides arguing about a record only one of them can read - the exact failure H6 exists to prevent. The "has revisions" signal is the record's own denormalized `revision_no` (H4), which the detail page has already loaded, so a disabled type costs no extra request. H2a is superseded for this one panel only: the revisions panel moves out of the Details body into the tab, and every other section keeps its placement.
- **H7a** The enabled map is derived from the **same code path as the per-submission policy** (`type_policy`, shared with `resolve_policy`), so a tab can never appear for a type the engine would refuse to revise. A zero cap and a missing adapter both read as disabled, which is why `complaint` shows no tab today.
- **H6a** (rewritten round 7) Attachments inside the view are **clickable and open the shared `AttachmentPreviewModal`, on both sides**. The original rule (names only) rested on a claim that was false: the office `RevisionTimeline` offered no preview at all, so an office user could read a historical file's name and never see it, while the contact could - the two sides seeing different things about one version, which is the failure H6 exists to prevent. The auth difference is real and is handled by a **seam, not by dropping the capability**: the shared dialog takes optional `fetchBytes` and `attachmentDownloadUrl` props, the portal passes its token-authenticated pair (per I2), and the office passes only the download url so the modal's default JWT `apiFetch` applies. The download url is keyed on **attachment id** (per I2a) on both sides, so a file a later revision unlinked still resolves. The office timeline's own entry badges get the same preview, so the two surfaces match. Inline rendering needs the signed `url` the backend already returns per snapshot attachment (`_attachment_urls`); without it the modal falls back to its download card, unchanged.

### I. Attachment preview in the portal - serves step 6 and every portal screen

- **I1** Clicking a portal attachment opens the shared `components/common/AttachmentPreviewModal` **in place**. No `target="_blank"` new tab.
- **I2** The portal passes its own `fetchBytes` (portal token auth) - the modal's documented escape hatch for token surfaces with no JWT session. `apiFetch` is not used from the portal.
- **I2a** The portal preview / download route is keyed on **`attachment_id`, not `link_id`**. G6 removes the `EntityAttachmentLink` for an attachment dropped during a revision, so a link-keyed route would 404 on exactly the historical files this feature exists to show. Authorisation walks: token → contact owns the submission → the attachment appears in one of that submission's revision snapshots.
- **I3** Preview works for the same types the office side supports (image / PDF / video / Excel inline), with the same fallback card for unpreviewable types.
- **I4** Preview is available in all three portal places: the submission form's attachment list, the submission detail view, and each entry in revision history.
- **I5** Download from the portal fetches bytes through the portal-authenticated route and saves a blob - never a bare `<a download>` to a protected route.

### J. Genericity - serves the next form, not this one

- **J1** The revision engine (table, service, policy resolution, snapshot, void-and-restart) is keyed on `source_entity_type` and knows nothing about stock inquiries.
- **J2** Per-type specifics live in a small adapter: model class, snapshot field list, line-item serializer, restart status, start event, denormalized column names. `stock_inquiry` is the only adapter registered this round.
- **J3** Wiring a second form type must require: one adapter, one config row, one migration for its two denormalized columns, and its own FE banner/tab wiring. No changes to the engine.
- **J4** One knob per concept. The restart target is declared **once**, on the config (`restart_stage_code`, NULL = first stage of the chain); the adapter maps a stage to the status the entity should carry. The adapter does **not** also hold a `restart_status` constant - two sources for one decision drift apart the first time a chain changes.
- **J5** Neither new table carries a `company_id`. Both scope through their parent entity, which is already company-scoped; the portal reads them under a contact token where no company scope applies. Every query joins or filters by `(source_entity_type, source_entity_id)` and is therefore never raw-SQL-scoped. Stated explicitly so nobody adds a stray `CompanyScopedMixin` and fails the portal closed.

### P. Printing and export of a revision (round 6) - serves the documentation purpose

- **P1** Any single revision, chosen from the office Revisions tab, exports as **PDF and as Excel in the same format as the main form**. The format is guaranteed by construction, not by discipline: the PDF services grew a snapshot value source feeding the SAME layout functions, and the client-side Excel builders are handed the revision adapted into the entity shape they already accept. There is deliberately no separate revision layout to keep in step.
- **P1a** Every value comes from that revision's **stored snapshot**, never the live row - the same rule G9a states for the on-screen view, now on paper where it is harder to correct. Fields the snapshot cannot carry honestly are **blanked, not inherited**: `status` (the snapshot is written before the post-revision status restart, so it holds the superseded value), the purchasing comment/reply, the rejection/reopen/void reasons, and the approval block. Front end and back end blank the identical set; if they ever disagree the backend is right.
- **P2** The document **states which revision it is**: the heading carries the entry label, whether it is superseded, who submitted it and when, and the reason. The **filename is that version's own document number plus exactly one marker**, always present and never stacked, matched byte-for-byte by the Excel export of the same version: `-as-submitted` on a revision (`product-inquiry-SI-26-0184-R1-as-submitted.pdf`), `-original` on the version-0 entry, `-resubmitted-v<N>` on a resubmission (which carries the record's current revision number, C4). The plain current-form export and the include-revisions export keep the unmarked name (`product-inquiry-SI-26-0184-R2.pdf`). The marker is load-bearing on EVERY single-revision export, not only where the number repeats: a revision export and the live-record export of a record sitting at that same revision are two **different documents** (the live one carries the purchasing reply, the status and the approval block that a snapshot deliberately blanks), and they land side by side in My Downloads - one name for two documents is precisely the filing failure this AC exists to prevent. **Round 6 correction:** appending a `-rev<N>` marker to a filename already built from the record's CURRENT number produced `...-SI-26-0184-R2-rev1.pdf` - two revision markers meaning different things in one filename, leaving the reader to decode which version the document is. Dates on the document are rendered in **Malaysia time** (the stored timestamp is naive UTC), so the PDF, the Excel sheet and the on-screen timeline of one revision can never disagree by a day. A printout that does not name its own version is worse than no printout, because it will be filed as current.
- **P3** (rewritten round 7) A revision page **embeds its own photos and lists its own other files**, exactly as the current form does, from THAT version's attachment set - resolved by attachment id, so a file a later revision unlinked (G6) still renders. The earlier rule (names only, images for the current form only) made a revision page a list of filenames while page 1 carried the photos, which is not "the same printing function for all revisions": the whole point of P1 is that a revision is the same document with older values. Best-effort at every step, because a printed history must never fail over one file: a missing attachment row, an unfetchable object, or a failure to read the rows at all each degrade to the snapshotted **filename**, never to a failed render. The cost is honest and accepted - one query per revision page plus one storage download per image on it, on an export that already runs on the RQ worker off the request path.
- **P4** The main export offers **"Include revisions"**, shown ONLY when revisions are enabled for that type AND this record has at least one (`revision_no > 0`), and **defaulting to on**. When the option cannot do anything it does not appear at all rather than appearing disabled: an unusable control is a question the user has to answer about a feature they do not have.
- **P4a** (rewritten round 7) With the option on, the document reads **current version first, then every earlier version newest-first, EXCLUDING the newest lineage entry**, each starting a new page (PDF) or its own sheet (Excel), each headed by its label, submitter and reason. That order matches the purpose the user stated: what it is now, then how it got here. The exclusion is the correction: **the newest entry IS the current version**, so printing both put the same form on page 1 and page 2 and left the reader comparing two pages to discover they were identical. The newest entry's context is not lost with its page - **the current form page carries its label, who submitted it and when, and its reason**, in the same wording a revision page's heading uses. Consequences, all of them intended: a lineage that is only the original appends nothing and the document is exactly the current form (correct - the original IS the current form there); a resubmission lineage still sitting at `revision_no = 0` follows the same rule, since "newest" is a position in the lineage, not a revision number; and a **single-revision export (`revision_id`) is unaffected** - asking for the newest entry by id still prints it in full, because that is a different document (the snapshot without the office fields the live row carries, P1a).
 - **Both surfaces, one rule.** The PDF services and the client-side Excel builders apply it identically, and neither reimplements the selection: the backend states it once as `appended_revision_entries` / `latest_revision_entry` (`pdf_revision_support.py`) and the frontend once as `appendedRevisionEntries` / `latestRevisionEntry` (`lib/revision-export.ts`), each used by both of its exporters. In the workbook that means sheet 1 is the current form carrying the newest entry's version block (the same label / reason / submitted lines a revision sheet uses, via `revisionInfoRows`), then one sheet per earlier version newest-first. A workbook whose sheet 2 repeated sheet 1 is the same defect the user reported on paper, so leaving Excel alone would have been shipping half the fix.
- **P5** Export stays on the **office side only**. The portal has no export for the main form either, so "the same function as the main form" is satisfied vacuously there; adding a portal-only export path would be inventing a capability nobody asked for and doubling the surface that has to stay in format-step.
- **P6** The existing enqueue-and-poll pipeline is unchanged: the export routes take an optional body (`revision_id` / `include_revisions`, mutually exclusive, 400 when both), pass it to the same RQ task, and the artifact lands in My Downloads as before. Old queued jobs keep working because the new task parameters have defaults (the routes pass them by keyword; the parameters themselves are ordinary positional-or-keyword ones, so a job queued by an older release with three positional args still runs).

### N. Document number carries the revision (Q4)

- **N1** A revised document reads as `SI-26-0184-R2` - the revision is visible on the number itself, wherever the number appears: portal, list, detail, PDF export, notifications, chat messages.
- **N2** **The stored base number does not change.** `inquiry_number` stays `SI-26-0184`; the suffix is **derived** from `revision_no` at render time by one shared helper. This is the implementation of N1, not a softening of it: every lookup-by-number, every integration (n8n, MCP tools, Respond templates, imports), and every existing index would otherwise have to learn to strip a suffix, and each one that forgot would silently fail to find the record.
- **N3** `revision_no = 0` renders the bare number with no `-R0` suffix.
- **N4** One helper, used by every surface including the PDF services, so the suffix can never appear on one screen and not another.
- **N5** The suffix reaches **every outbound surface, integration payloads included** (round 3): screens, PDF body, PDF filename, portal copy, Respond.io messages, notifications, and external API responses.
- **N6** Therefore **every inbound lookup-by-number must tolerate a suffix** - strip a trailing `-R\d+` before matching.
 - **Correction (round 4):** an earlier draft justified this with the external view-link resolver. That was wrong - public view links are retired (the routes sit behind `require_public_view_links_enabled`, and the user confirms only the in-system view and the portal link are used now). `view_link.py` is not a reason to do anything.
 - The real reason is stronger. The **external API create endpoints** use the document number as a resubmit key: `POST /api/v1/external/stock-inquiries` -> `create_inquiry` -> exact match on `StockInquiry.inquiry_number` (`procurement_service.py:3441`), and the same shape for purchase requests (`:5409`). The contract is explicit: *"Use inquiry_number only to resubmit a rejected inquiry."*
 - The failure mode is worse than a missed lookup. An external caller that echoes back a number it read from a payload - now carrying `-R2` - **misses the existing row and inserts a duplicate** instead of updating the rejected one. Silent data duplication on a live integration path, not a visible 404.
- **N7** Stripping is centralised in the same module as the render helper, so the two can never disagree about the suffix format.

### O. Gate the response, not the conversation (round 3)

**Correction of record, verified in code.** The review note assumed responses are "not permitted after the record has closed even for today". They are. Neither response path has any status guard:

- `POST /stock-inquiries/{id}/update-and-reply` (`stock_inquiries.py:441`) guards only with `assert_can_act_on_form` (the handling lock). At **any** status - closed, rejected, voided - the message sends and `last_responded_by` / `last_responded_at` are stamped (`procurement_service.py:4024-4025`). Only the flip to `status = "responded"` is conditional (`:3922`).
- `POST /complaints/{id}/update-and-reply` (`complaints.py:1516`) has no status condition either; it sets `status = responded` unconditionally.

So "wide" is a **new restriction**, not a codification of today's behaviour, and it must be built and tested as such.

- **O1** A **response** write is rejected with 422 when the record's status is outside that type's allowed response statuses.
- **O1a** **Correction (round 5, verified):** the claim that stock inquiry and complaint are "the only two response surfaces in the system" is **false**. `grep -rn "update-and-reply" app/api/v1/` returns FIVE: stock inquiry, complaint, **purchase request**, and tickets (`/response/update-and-reply` and `/resolution/update-and-reply`).
 - **In scope:** stock inquiry and complaint **only**. These are the two types that actually carry a response column.
 - **PR / SF have no response surface to gate** (verified): `PurchaseRequestHeader` has no `purchasing_response`, no `technical_team_response` and no `last_responded_*`; `PurchaseRequestUpdateAndReply` adds only `reply_message`, which `update_request_and_reply` sends and **never stores** (`exclude={"products", "reply_message"}`). Their `update-and-reply` is an office header edit plus a chat send. Status-gating it would block messaging a contact about a closed request, which AC O2 forbids outright. A coordinator instruction to gate PR/SF was issued and correctly refused on these grounds.
 - The stale-office-write risk on PR / SF is real but belongs to a **different axis**: the revision fence (CB1/CB3), which already covers every office write on every revisable form. The status gate is not a substitute and would not close it.
 - **Out of scope:** tickets. Not a revisable type, not part of this feature.
 - A tripwire test asserts `purchase_requests` has no response column, so if one is ever added the gating decision has to be made consciously instead of silently skipped.
- **O1b** Gating the endpoint alone is **not sufficient**. On stock inquiry the frontend writes `purchasing_response` through the plain PUT first and only then calls `update-and-reply`, so an endpoint-only gate would still persist an answer on a dead record. The gate belongs on the **field write** as well, on every gated type.
- **O1c** A save that carries the response back **unchanged** is not a response write, and "unchanged" is judged on **both sides normalized**, never on the raw column. The complaint response passes through `_normalize_complaint_reply_body_for_storage` (which strips the legacy "There has been an update regarding your complaint ...: " preamble) on write only, so every row stored before that normalizer landed still carries the preamble - while the detail page and the edit form render, and therefore post back, the stripped body. Comparing bare-incoming against raw-stored read as a rewrite and 422'd an office save that only touched the customer's address. A genuinely different answer on a legacy row is still refused.
- **O2** **Ordinary chat is untouched.** Messaging a contact about a closed or rejected record keeps working exactly as today (user's explicit note). The gate is on the stage output, never on the conversation.
- **O3** **Correction (round 5, verified):** the split already exists. `POST /{entity}/{id}/conversation/send-message` is a pure chat send that never mutates the entity, is mounted on both types, and is what `SharedConversationComposer` calls. `update-and-reply` is therefore the **response** path, not the chat path. So O1/O2 do NOT require building a split - they require gating `update-and-reply` plus the response column, and leaving `/conversation/send-message` untouched. Simpler than this AC originally claimed.
- **O4** The revision fence (CB1) still applies on top: even inside an allowed status, a write carrying a stale `revision_no` is refused. Status gate and revision gate are independent checks.

### K. Non-goals (explicit)

- Complaints are **not** revisable, this round or by config default.
- No approval workflow *for* a revision (a revision is not itself approved; it re-enters the existing approval flow).
- No partial / field-level revision requests from the office side ("please change X") - that is a different feature.
- No revision of attachments alone without a reason.
- No diff on line-item **reordering** (only add / remove / value change).

---

## Open questions

**None blocking.** All eleven questions raised across rounds 1-3 are answered and folded into the ACs above. Implementation remains **on hold at the user's request** pending a wider conversation about the plan, not pending any specific answer.

Two things were decided against a stated belief that turned out to be wrong, and both should be re-confirmed once seen in the flesh rather than treated as settled forever:

1. **Section O** was chosen believing responses were already blocked on closed records. They are not - neither stock inquiry nor complaint has a status guard today. The decision stands, but it is a **new restriction on live behaviour**, so someone will notice it. Worth a heads-up to whoever handles those two queues before it ships.
2. **N5** was chosen believing no integration consumes these numbers. One does - not the view-link resolver (retired, correctly dismissed by the user in round 4) but the **external API create-or-resubmit path**, which keys off the number to decide whether to update a rejected record or insert a new one. N6 handles it. Flagged so "no integration uses this" is not carried into the next feature unchecked.

## Deferred (explicitly out of this round)

- **Complaint revisions** - config row ships disabled and flippable. "Ready when the time comes."
- Per-field revision requests from the office side ("please change X") - a different feature.
