# n8n integration spec - container status

**Status:** CRM side merged (PR #105). n8n side unbuilt.
**Audience:** whoever edits `sorento-consume-main` and `sub-semantic-parser`.
**Companion docs:** `PLAN-container-status-tracking.md` (decision log, D15 / D19 / D21 / D22 / D25a),
`container-status-tracking-acceptance-criteria.md`.

This is the contract, not a workflow design. It says what the CRM now emits, what n8n must do with
it, and which gaps are still ours to close. Where a decision was already taken in the PLAN, this
document repeats the outcome rather than reopening it.

---

## 1. Why n8n has work to do at all

Decision **D15** was reversed during review: there is ONE shipment tool, not a container-status
tool beside it. The CRM dumps every field the caller is entitled to see, and **n8n narrows**.

That split is deliberate and it is the whole of this spec:

| concern | owner | why |
| --- | --- | --- |
| may this contact see `gatepass_date`? | **CRM** | Server-side, on the contact's own grants. n8n's narrowing is a second layer, never the mechanism (D16). |
| the user asked for the ETA, so show the ETA and not 20 other dates | **n8n** | The CRM cannot know which of the returned fields answers the question. |
| is "container status list" a document request or a data question? | **n8n** (routing), **CRM** (resolution) | n8n classifies; the CRM resolves the label to a type UUID. |

**If n8n does nothing, nothing leaks** - the CRM already withholds. What happens instead is that a
contact who asks "when does GXYU5106903 arrive" gets a 20-field dump. The CRM prevents the leak;
n8n prevents the dump.

---

## 2. What the CRM emits today

### 2.1 `crm_incoming_stock_list` with `view=render`

Call it with `contact_id` + `space_id` (the Respond.io contact id and workspace) so the answer is
scoped to that contact's grants. Envelope:

```json
{
  "result_type": "incoming_stock",
  "intro": "Here is the incoming stock I found.",
  "items": [
    {
      "title": "SRT-WC-001",
      "fields": [
        {"label": "Product Code", "value": "SRT-WC-001"},
        {"label": "Container", "value": "GXYU5106903"},
        {"label": "ETA", "value": "2026-07-18"},
        {"label": "Gatepass", "value": "2026-07-22"}
      ],
      "flags": {"discontinued": false, "expired": false,
                "unallocated": false, "partially_allocated": false}
    }
  ],
  "attachments": [],
  "action_links": [],
  "last_updated_at": "2026-08-07T06:31:13",
  "has_result": true,
  "field_access": { "...see 2.3..." }
}
```

**`fields` is variable-length.** A field is present only when it is (a) entitled AND (b) non-empty -
empty pairs are dropped before the item is built. So an absent label means "not entitled OR not
reached yet", and the two are told apart only by `field_access` (2.3).

### 2.2 The label vocabulary

These are the exact `label` strings. Match on them; do not re-derive from the underlying column
names, which n8n never sees.

**Always present (identity - never gated):**

`Product Code` · `Product Name` · `Shipment` · `Container` · `Batch` · `Incoming Quantity` ·
`Warehouse Allocations` · `Unallocated Quantity`

**Gated (present only when entitled and filled):**

| label | underlying field | notes |
| --- | --- | --- |
| `ETA` | `estimated_arrival_date` | Ships **allowed** for everyone holding `incoming_stock_enquiries` - today's public answer |
| `ETA Delay` | `eta_delay_date` | |
| `CIDB Inspection` | `inspection_date` | |
| `CIDB Approval` | `approval_date` | |
| `Gatepass` | `gatepass_date` | |
| `Warehouse Arrival` | `warehouse_arrival_date` | |
| `Collection Informed` | `informed_collection_date` | |
| `Collection` | `collection_date` | |
| `Loading` | `loading_date` | |
| `ETC` | `etc_date` | |
| `ETD` | `etd_date` | |
| `Liner` | `liner_code` | |
| `China Forwarder` | `china_forwarder` | |
| `Malaysia Forwarder` | `malaysia_forwarder` | |
| `Consignee` | `consignee` | |
| `Delivery Warehouse` | `delivery_warehouse` | |
| `Free Days Available` | `free_days_available` | |
| `Location` | `loc` | |
| `Stacked` | `stacked` | |
| `COA Permit No.` | `coa_permit_no` | Note the trailing period |

Source of truth: `sorento_crm_mcp/presenters.py` `_CLEARANCE_PAIRS`. **If that tuple changes this
table is stale** - re-read it rather than trusting this copy.

### 2.3 The `field_access` block

Present only when something was withheld. Sibling of `items`, never inside a row:

```json
"field_access": {
  "denied": [
    {"field": "gatepass_date", "agent_code": "incoming_stock_enquiries",
     "outcome": "field_not_allowed",
     "reason": "This contact holds the agent, but this field is not allowed on it. Tick the field on the agent, or add a per-contact override."}
  ],
  "note": "These fields are omitted because this caller may not see them. Absent does NOT mean the value is unknown or not yet reached."
}
```

`outcome` is one of `field_not_allowed`, `agent_not_assigned`, `contact_not_found`. The three need
different admin fixes, which is why they are distinguished - see the PLAN's D38-revised.

**n8n must never turn a denial into a value statement.** "There is no gatepass date yet" is a lie
when the truth is "you may not see it". Preferred phrasing: *"I can't share the gatepass date -
please check with the office."* Do not quote `reason` at the contact; it is written for an admin.

---

## 3. What n8n must build

### N1 - requested-attribute matching (the main ask)

**Today:** `sub-semantic-parser` already emits `requested_attributes`, and its prompt already states
the purpose - *"the user asked about, so downstream shows only those - not the whole record"*. The
vocabulary is what is frozen: `incoming: eta`, one value (D25a).

**Required:**

1. The parser emits the attribute the user asked for, in the CRM's canonical field key
   (`gatepass_date`, `eta_delay_date`, ...) or a raw phrase the CRM canonicalises (see C2, unbuilt).
2. `sub-get-results` filters the returned `fields` to (identity fields) + (requested attributes),
   and answers from that projection.
3. **No requested attribute → do not dump.** Fall back to the identity block plus `ETA`. A user who
   asks "where is my container" wants a sentence, not a table of 20 dates.
4. A requested attribute that is **absent** from `fields`:
   - present in `field_access.denied` → say it cannot be shared (2.3)
   - not in `denied` → genuinely empty; say the step has not happened yet
   That branch is the entire reason `field_access` exists. Collapsing it loses the distinction the
   CRM went to some trouble to preserve.

**Test table** (paraphrases, not keywords - the parser is an LLM, so exercise it as one):

| user says | requested attribute | answer shape |
| --- | --- | --- |
| "when is GXYU5106903 arriving" | `estimated_arrival_date` | ETA only |
| "has it cleared CIDB" | `inspection_date`, `approval_date` | both, or "not yet" |
| "any delay on the ETA" | `eta_delay_date` | delay, else "no delay recorded" |
| "can I collect it" | `gatepass_date`, `collection_date` | denied → "check with the office" |
| "where is my container" | none | identity + ETA, one sentence |
| "who is the forwarder" | `malaysia_forwarder`, `china_forwarder` | both when filled |

### N2 - route document requests to the resources domain

"Send me the container status list" is a **document** request, not a data question. It must reach
`crm_resource_attachments_list`, not `crm_incoming_stock_list`.

```
crm_resource_attachments_list
  attachment_type_code = "Container Status"     # or attachment_type_id from resolve-entity
  contact_id           = <respond contact id>
  space_id             = <workspace space_id>
```

Three things to know, each of which has already caused a wrong answer:

1. **A narrowing filter is mandatory.** Without one of `attachment_ids` / `directory_id` /
   `attachment_type_id` / `attachment_type_code`, the tool returns an empty page **without calling
   the backend at all**. The MCP log shows no HTTP request, and the agent narrates the empty page as
   "there is no such document". `attachment_type_code` was added to that list for exactly this flow.
2. **`contact_id` + `space_id` widen, never narrow.** Container Status is not a dealer-facing type,
   so it is returned ONLY for a contact granted it (User Management → contact → Document types).
   Omit them and the response is the 9-file dealer baseline - correct, and not what the office
   asked for.
3. **URLs are unsigned by design.** `attachments[].url` is the CDN address
   (`https://<cdn>/import-sources/<uuid>/Container Status 2026.xlsx`); n8n signs on the way out.
   Pass `resolve_signed_urls=true` if a ready-to-open link is wanted instead.

Exactly **one** Container Status workbook is live at any time - each import trashes the previous, so
this call returns a single row. `Uploaded` and `last_updated_at` carry its date; `File ID` carries
the attachment UUID, which is what to quote when a human needs to find the row.

### N3 - the escalation enum

Add the new agent to the `escalated_agent` enum in `sub-get-results` (PLAN S9). Unchanged from the
original plan.

---

## 4. What the CRM still owes n8n

Both of these are **blockers for N2** as written, and neither is n8n's to fix.

### C1 - `attachment_type` resolution is exact-match only

`entity_resolver._probe_attachment_type` matches `lower(code)` or `lower(type_name)` against the
token, exactly. So:

| token | resolves? |
| --- | --- |
| `container status` | yes (type_name) |
| `container_status` | yes (code) |
| `container status list` | **no** |
| `container status report` | **no** |
| `shipping schedule` | **no** |
| `eta list` | **no** |

`container_status_document.KEYWORDS` already lists those aliases, and nothing reads it -
`attachment_types` has no keywords column. This is D21, unbuilt.

**Fix (CRM side):** give `attachment_types` a `keywords` JSONB column, seed it from `KEYWORDS`, and
extend the probe to match it - the same shape `contact_access_types.keywords` already uses for
"customer"/"homeowner" → `end_user`. Until then n8n must send the literal `"Container Status"`,
which means the routing words stay hardcoded in the parser prompt - the thing D22 set out to remove.

### C2 - `attribute` is not a resolvable reference type

D22's plan is that the parser emits the user's raw phrase and the CRM canonicalises it to a field
key, via `POST /api/v1/system/references/resolve` (a call consume-main already makes every turn).
`attribute` is not yet a registered type there, so today the mapping "gate pass" → `gatepass_date`
has to live in the n8n prompt.

**Fix (CRM side):** register `attribute` as a reference type over `GATED_FIELDS` +
`FIELD_LABELS`, returning `{field_key, label, resource}`.

**Until C1 and C2 land**, N1 and N2 are buildable with the vocabulary hardcoded in the parser
prompt. That works and is worth doing - it is just the 31KB-prompt-edit problem the PLAN wanted to
retire, so treat the hardcoded version as the interim.

---

## 5. Verification

Do not accept this on a mock. The MCP server answers with real data:

```bash
CRM_BASE_URL=http://localhost:8000 EXTERNAL_API_KEY=<key> python -m sorento_crm_mcp
# then call crm_incoming_stock_list with view=render, contact_id, space_id
```

Cases to run against a real contact, all of which were verified CRM-side and should now be verified
end to end:

1. Contact **with** the gatepass grant asks for it → the value appears.
2. Contact **without** it asks → no `Gatepass` label, `field_access.denied` names it
   `field_not_allowed`, and the reply says it cannot be shared rather than "not yet".
3. Contact **without the agent** asks → same, `outcome: agent_not_assigned`.
4. Every case above still returns `Product Code`, `Container`, `ETA`, `Incoming Quantity` - the
   answer itself is never gated, pinned CRM-side by
   `test_render_never_gates_the_answer_itself`.
5. Contact **granted** the Container Status type asks for the list → one attachment, correct URL.
6. Contact **not granted** it asks → no attachment, and a reply that does not invent one.

A wrong `space_id` resolves to no contact at all and reports `contact_not_found`. If every field
comes back denied, check the workspace before checking the grants.
