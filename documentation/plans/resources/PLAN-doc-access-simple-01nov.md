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
   `contact_access_type_service.py:92-95`), so in practice the type is the gate: 1104 of 1120 Technical
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

## Open (owner)

Card v1 questions Q1-Q5 in the crew ask. Build starts only after the mock and the answers come back.
