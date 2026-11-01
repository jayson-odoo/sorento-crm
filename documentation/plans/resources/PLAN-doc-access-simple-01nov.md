# PLAN: DOC-ACCESS-SIMPLE - one place to set who can read a document type, with a "who can read this?" preview

Status: MOCK v1 + CARD v1 FILED 1 Nov (Waiting:owner). Nothing built. Track: full (re-sized L on the card: one
migration + one new screen + an access-control rule change; security-reviewer required).

Lane: `crew/doc-access-simple`. Follows `PLAN-agentic-knowledge-w1-01nov.md` section "Access control lane" (:151-158)
and owner ruling W-Q5 (a) (`PLAN-agentic-knowledge-p2-31oct.md:129-135`): no per-contact type grant for AI reads;
a contact with no access code reads no document.

Owner, 1 Nov ~00:15: document access control must become "easier, straightforward, more flexible".

## Today: what decides whether a reader gets a document (origin/main 1fc0fab923)

`BE` = `sorento_crm_backend/app`, `FE` = `sorento_crm_frontend/app/(protected)`.

### The settings

| # | Setting | Stored in | Set on screen | Read by |
|---|---|---|---|---|
| 1 | Type **AI can read**: Off / Staff only / Dealers / Everyone | `attachment_types.ai_audience` (`BE/models/resources.py:87`, CHECK :104) | Attachment Types > edit dialog, a SearchableSelect (`FE/resource-management/attachment-types/components/AttachmentTypeFormDialog.tsx:41-45,428-441`). Not a column in the list (`AttachmentTypesList.tsx:62-99`). | AI only |
| 2 | File **Access levels** (list of access codes) | `attachments.access_levels` JSONB, default `["dealer","end_user"]` (`BE/models/resources.py:192`) | Upload dialog, file detail, Files modal, bulk "Adjust access levels" (`AccessLevelsMultiSelect.tsx:30`, `BulkAttachmentAccessLevelsDialog.tsx:149`) | AI (contacts), promotions |
| 3 | Contact **Access types** (codes) | `respond_contact_access_types` (`BE/models/access.py:92-115`), catalogue `contact_access_types` (:67-85) | Contact edit dialog checkbox chips (`FE/user-management/contacts/[id]/components/ContactEditDialog.tsx:302-345`), access sheet import | AI (contacts), promotions |
| 4 | Contact **Companies** | `respond_contact_companies` (`BE/models/company.py:79-83`) | Contact edit | AI company scope |
| 5 | Type **Shared** | `attachment_types.is_shared` (`BE/models/resources.py:84`): new uploads get `company_id NULL` | Attachment Types dialog (`AttachmentTypeFormDialog.tsx:389`) | company scope |
| 6 | Linked CRM user | `users.respond_contact_id` | User edit | switches the contact to the staff path |
| 7 | Type **Direct access** + per-contact **Document types** grants | `attachment_types.is_direct_access` (`BE/models/resources.py:57`), `contact_attachment_types` (`BE/models/access.py:521`) | Grants: contact page `ContactAttachmentTypesSection.tsx:51`. Direct access: no screen found (only that section reads it) | file SENDING (MCP list), not AI |

### The rule that combines them

- **Contact on WhatsApp** (`BE/services/knowledge_service.py:671-713`, called from `BE/services/chatbot/agent/tools.py:924`):
  codes = the contact's ACTIVE codes (`BE/services/chatbot/agent/access.py:171-188`); none -> no document (:693-694).
  A file is read when
  `(type = Everyone AND file levels ∩ codes ≠ ∅) OR (type = Dealers AND file levels ∩ (codes − {end_user}) ≠ ∅)`
  (:695-703), and the file's company is one of the contact's companies or NULL (shared)
  (`BE/services/embedding_service.py:54-79`; a contact with no company gets an empty scope and reads nothing,
  `BE/services/company_scope_resolver.py:331-351`).
- **Staff** (Console agent, AI side panel; also a contact with a linked active CRM user, `access.py:83-90,151`):
  permission `resource.attachments.view` + type not Off (`knowledge_service.py:41,44,645,659`). The file's access
  levels are NOT checked.
- **Sending a file** (MCP `crm_resource_attachments_list`, pinned `direct_access_only=true`,
  `sorento_crm_mcp/sorento_crm_mcp/server.py:177`): types with Direct access UNION types granted to the contact
  (`BE/services/resources_service.py:970-985`, `BE/services/contact_attachment_access.py:1-22`). Ignores the AI
  setting AND the file's access levels.

### Pain points

1. **"Dealers" is not dealers.** It means "any code except the literal `end_user`" (`knowledge_service.py:695`).
   On dev (28 Oct copy) that silently includes `sorento_office`, `mocha_office`, `cabana_office` (47 / 52 / 39
   contacts) and any code an admin adds later.
2. **Two ANDed settings, on two screens, neither shows the other.** The type says Dealers, the file says
   `["end_user"]`: nobody outside reads it, and no screen says so. 308 Product Photos files and 105 Promotion files
   carry `["end_user"]` only.
3. **The file levels default to every active code** (`BE/api/v1/resources/attachments.py:1086-1087`,
   `contact_access_type_service.py:92-95`), so in practice the type is the gate: 1105 of 1120 Technical
   Specifications files carry all 7 codes. Narrowing a type to dealers today means editing the type, not 1120 files,
   but the type only offers four fixed buckets, not per-brand codes.
4. **Company scope is invisible.** Direct Access is a Shared type, yet 9 of its 15 files belong to Sorento (uploaded
   before the switch): a Mocha-only dealer misses the Cabana / Sorento warranty policies though the codes match.
   27 of 495 contacts have no company and read nothing.
5. **Three "who gets this type" ideas that do not talk:** AI can read (#1), Direct access (#7, no screen), and the
   per-contact Document types grant (#7) that governs sending, not AI. The contact page's grant section looks like
   it controls reading; it does not (owner ruling W-Q5 (a)).
6. **No preview anywhere** answers "who can read this?" or "what can this contact read?" (no FE hit for either).

Dev data (sorento_dev_1028, read only): 8 codes (7 active, `nl_dealer` inactive); 22 types, all `ai_audience =
off`; 495 contacts, 60 with no code, 27 with no company, 0 with the agent on. Most common shapes:
`{cabana_dealer, dealer, end_user}` in Sorento (129), `{end_user}` (150 over 3 company sets),
`{end_user, mocha_dealer}` in Mocha (19).

## Proposal (mock v1, `documentation/mockups/DOC-ACCESS-SIMPLE/index.html`)

ONE page, **Resource Management > Document Access**: a matrix, one row per document type, one column per active
access code plus **Staff**. A tick = the AI may read that type for contacts holding that code (staff: for users who
may view Resources). Each ticked cell shows how many of the type's files the code actually reaches, so a file that
narrows is visible. **Preview as** (a contact picker in the header) marks every row with what that contact reads
and why not. A row opens a side sheet: the same ticks, the type's files with their access levels and the
preview verdict per file, and the type's "Sent as a file" settings.

Rule after the change (one sentence): **a contact reads a file when one of the contact's access codes is ticked on
the file's type AND is in the file's access levels, and the file is in one of the contact's companies or shared.**
Staff: the Staff tick + `resource.attachments.view`. Sending files is unchanged.

Data: `attachment_types.ai_readers` JSONB (list of codes, plus `staff`) replaces `ai_audience`; backfill keeps
today's behaviour exactly (off -> [], staff -> [staff], dealer -> staff + every active code except end_user,
public -> staff + every active code). Details after the owner approves the mock.

## Behaviour card v1 (filed 1 Nov with mock v1)

### Rules

1. One page, Resource Management > Document Access (`config/menu.config.tsx:859-878`, after Attachment Types):
   one row per document type, one tick per ACTIVE access type plus Staff. View needs
   `resource.attachment_types.view`; a tick needs `resource.attachment_types.edit`
   (`BE/api/v1/resources/attachment_types.py:28,86`).
2. Contact reads document D of type T when a code is in (contact's active codes) AND (T's ticks) AND (D's access
   levels), and D's company is one of the contact's companies or D is shared. No access type, or no company: nothing.
3. Staff (Console agent, AI side panel, a contact linked to an active CRM user): T has Staff ticked AND the user
   holds `resource.attachments.view` (unchanged permission, `knowledge_service.py:41,645`).
4. Each ticked cell shows "reach/total" in amber when some of T's documents do not carry that code.
5. Preview as a contact: per row "Reads X of Y" plus why not (no shared access type, other company), or the first
   gate that stops everything (No access type, No company, Not ticked, Staff only, Off, runs as staff).
6. The type sheet lists the documents with their access levels (editable, `AccessLevelsMultiSelect.tsx:30`) and a
   per-document verdict for the previewed contact, plus "Sent as a file".
7. The Attachment Type dialog loses "AI can read"; "Escalate to" stays there.

### Examples (dev copy sorento_dev_1028; contacts masked, each a real shape)

- **CONTACT A** (Sorento Dealer, Cabana Dealer, End User; Sorento; 129 contacts share this shape), Direct Access
  ticked for every code: reads 13 of 15; Iborn and Mocha Pricetag Templates carry only Mocha codes.
- **CONTACT C** (Mocha Dealer, End User; Mocha; 19), Direct Access: reads 5 of 15. 8 are Sorento-company files
  in a Shared type (uploaded before the switch): "Other company: Sorento". 2 carry no Mocha code. Invisible today.
- **CONTACT B** (End User; Sorento; 80), Technical Specifications ticked for the three Dealer codes: reads 0 of
  82 ("Not ticked for End User"); tick End User: reads 82.
- **CONTACT D** (Sorento Office only; Mocha + Sorento; no CRM user; 4), Certification on today's "Dealers":
  reads 120 of 121, because office counts as dealer (`knowledge_service.py:695`). On the new page that is a visible
  Sorento Office tick (Q2).
- **CONTACT E** (no access type, no company; 3): "No access type", reads nothing (W-Q5 (a)).

### Edge cases

- Linked active CRM user: runs as staff (W-Q1 (a), `agent/access.py:83-90`), the preview says "Runs as Staff user".
- Agent switch off for the contact: the preview still computes and shows "Agent on WhatsApp: Off" (0 of 495
  contacts have it on in the dev copy).
- Inactive access type (NL Dealer): no column; it is ignored in file levels, as today (`agent/access.py:171-188`).
- Staff unticked, a code ticked: contacts read, staff do not (today impossible: every non-Off audience includes
  staff, `knowledge_service.py:44`).
- First tick on an Off type queues its unread files as today (`resources_service.py:589-593`); removing the last
  tick hides the chunks, as Off does today.

### Questions (at most 5)

- **Q1 Model.** (a) a tick per access type + Staff per type, documents still narrow; (b) keep the four buckets in
  the dialog, add only the preview, and make "Dealers" mean the three Dealer codes. **Rec (a)**: per-brand control
  at the type, without editing file rows (1105 of 1120 Technical Specifications files carry all 7 codes), and the
  rule says exactly who reads.
- **Q2 Carry-over on deploy.** (a) tick for tick as today reads: Dealers -> Staff + every active code except End
  User (the 3 Office codes come out ticked, visibly); Everyone -> Staff + all; Staff only -> Staff; (b) Dealers ->
  Staff + the three Dealer codes only (office contacts without a CRM user lose those types). **Rec (a)**: deploy
  changes nobody's access; untick Office on the page if wanted. UNVERIFIED: which types prod has on (dev is all Off).
- **Q3 New access type added later.** (a) new column, unticked everywhere; (b) auto-ticked where every other code
  is ticked. **Rec (a)**: no silent widening; today a new code silently joins every Dealers and Everyone type
  (`knowledge_service.py:695,701`).
- **Q4 Saving a tick.** (a) saves at once, toast names the count ("Technical Specifications: End User can now read
  82 documents."), untick undoes; (b) Edit + Save with a who-gains summary. **Rec (a)**: one click, the count is
  the summary.
- **Q5 Sending files** (Direct access + per-contact Document types, MCP list). (a) rule unchanged; the page shows
  it ("Sent as a file") and the sheet gets the Direct access switch (no screen sets it today); (b) sending follows
  the same ticks. **Rec (a)**: W-Q5 kept sending separate, and (b) changes what dealers receive today; it can be
  its own lane.

## Open (owner)

Mock v1 + card v1 in the crew ask. Build starts only after the owner approves the mock and answers Q1-Q5.
