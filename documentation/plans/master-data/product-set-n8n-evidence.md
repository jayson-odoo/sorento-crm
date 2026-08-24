# Evidence run: a set code resolves and fans out, for n8n and for you

**Branch:** `feat/product-sets`, HEAD `d02991c8e` plus the two uncommitted fixes this document
proves. **Backend:** the running dev instance on `:8050` (`uvicorn --reload`). **Real set used:**
`SRTWC8608-RL`, company Sorento, 3 members - `SRTWCX8608-RL` (pedestal), `SRTWCY8608` (cistern),
`SRTWC8608-SC` (seat cover). No `WC7605` exists in this database; the task named it as an example,
this document uses the real row instead and says so here once.

This supersedes two findings in `n8n-contract-product-set-entity.md`:

- Surface 1, finding 1 ("`product` does not auto-expand to include `product_set`") - **fixed**,
  command 1 below.
- Surface 5 ("packing list create is UNTOUCHED... a set code lands in `skipped_product_codes`") -
  **fixed**, command 5 below.

**Later update, on top of PR #286 (`7a632df62`), also uncommitted at the time of writing:**
command 1's response now also carries `product_id` on every member and a populated
`company_id`/`company_name` on the match - see the note directly above that response for what
was and was not re-curled for this update.

## Env vars you need, without printing their values

- `EXTERNAL_API_KEY` - the shared integration key. Read it from your own `sorento_crm_backend/.env`
  (`grep EXTERNAL_API_KEY .env`); every command below assumes it is exported as `$EXTERNAL_API_KEY`.
- `EXTERNAL_API_KEY_ACT_AS_USER_ID` - server-side only. The backend resolves the API key to this
  real `users.id` for attribution (`created_by`). You never send this as a header; it has to exist
  in the backend's own `.env` or every `X-API-Key` call gets an anonymous/no-RBAC principal.
- No `contact_id` / `space_id` on any command below, so every call runs at **all-companies scope**
  (`X-API-Key` default - see the "Company scope" note on each surface in the contract doc). That
  is deliberate here, to show the real, unscoped behaviour a bare n8n call gets; commands 3-5 pin
  scope through the `attachment_id` they carry instead, the same mechanism production already uses.

```bash
export EXTERNAL_API_KEY=$(grep '^EXTERNAL_API_KEY=' sorento_crm_backend/.env | cut -d= -f2)
```

**Runtime state:** this run temporarily added `PRODUCT_SET_RESOLVE_ENABLED=true` to
`sorento_crm_backend/.env` (gitignored, local to this worktree) to capture command 1's ON
response, then removed the line again afterward - the flag is OFF on the running `:8050` backend
right now, same as it was before this run, and the same as the module's own committed default
(`PRODUCT_SET_RESOLVE_ENABLED` in `app/services/entity_resolver.py`). Reason it was reverted, not
left on: leaving it set in `.env` bled into the backend test suite too - `app/main.py` calls
`load_dotenv(override=True)`, and any test that imports `app.main` (several do, via `TestClient`)
picked up the same env var, breaking `test_the_default_really_is_off_in_the_module`'s assumption
that the module's default is off. To try command 1 yourself:

```bash
echo 'PRODUCT_SET_RESOLVE_ENABLED=true' >> sorento_crm_backend/.env
touch sorento_crm_backend/app/main.py   # forces the --reload worker to pick it up, no restart
```

and reverse both lines (delete the `.env` line, `touch` again) before running the backend test
suite, or `test_the_default_really_is_off_in_the_module` will fail for the same reason.

---

## 1. Set code, hint `product` - the requirement in your own words

```bash
curl -s -X POST http://localhost:8050/api/v1/system/references/resolve \
  -H "X-API-Key: $EXTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"SRTWC8608-RL","allowed_entity_types":["product"]}'
```

**Update to this response, later in the same branch:** two more fields were added after this
command was first captured - `product_id` on each member (Change 1) and a populated
`company_id`/`company_name` on the match itself (Change 2, `product_set` registered in
`_company_scoped_models`). `:8050` was not listening when this update was made (checked with
`lsof -i :8050`, nothing bound), so the response below was NOT re-curled; the `product_id`
values are the real per-member product ids already proven live in commands 3/4/5 below
(`SRTWCX8608-RL` = `0fb2507c-c6f3-47a1-ad10-296a3604aaea`, `SRTWCY8608` =
`732adbfb-06cb-499f-8cd3-88bd16678655`, `SRTWC8608-SC` = `ed83a177-81c0-46e7-9989-d484e54b9c9d`),
and `company_id`/`company_name` are Sorento's, the same company every other command in this
document runs against. Re-curl this command against a live `:8050` (flag on) before relying on
this exact byte shape.

Response (flag ON, `product_id`/`company_id`/`company_name` reconstructed as described above -
everything else is the real capture):

```json
{
  "tokens": ["SRTWC8608-RL"],
  "elapsed_ms": 56.47,
  "resolutions": [
    {
      "token": "SRTWC8608-RL",
      "resolved": true,
      "ambiguous": false,
      "matches": [
        {
          "entity_type": "product_set",
          "canonical_code": "SRTWC8608-RL",
          "uuid": "608d64d6-93fe-4fa7-a84b-70879589b84c",
          "match_field": "set_code",
          "match_tier": "exact",
          "similarity": null,
          "company_id": "00000000-0000-0000-0000-000000000001",
          "company_name": "Sorento",
          "display": {
            "name": "Washdown with rimless flushing, S-trap",
            "member_count": 3,
            "complete_sets": 1629,
            "limiting_member": "SRTWCX8608-RL",
            "members": [
              {"product_code": "SRTWCX8608-RL", "description": "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM) SRTWCX8608-RL", "quantity": 1.0, "available": 1629, "is_discontinued": false, "product_id": "0fb2507c-c6f3-47a1-ad10-296a3604aaea"},
              {"product_code": "SRTWCY8608", "description": "SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP).  SRTWCY8608", "quantity": 1.0, "available": 2051, "is_discontinued": false, "product_id": "732adbfb-06cb-499f-8cd3-88bd16678655"},
              {"product_code": "SRTWC8608-SC", "description": "SORENTO SRTWC8608-SC SEAT COVER ONLY", "quantity": 1.0, "available": 2044, "is_discontinued": false, "product_id": "ed83a177-81c0-46e7-9989-d484e54b9c9d"}
            ]
          }
        }
      ],
      "alternatives": []
    }
  ],
  "unresolved_tokens": []
}
```

One entity, `entity_type: "product_set"`, its members inside `display.members` - never a fan-out
of three top-level `product` matches. `allowed_entity_types: ["product"]` is exactly n8n's
existing hint; nothing about the request changed except this fix. Every member's `product_id`
is what n8n fans out with - pass that list straight into the existing per-product MCP tools'
`product_ids` param (`crm_inventory_stock_balance_list`, `crm_master_products_list`,
`crm_marketing_promotion_products_list`, `crm_incoming_stock_by_product`); no new MCP tool
needed.

## 2. Same call, flag OFF - today's behaviour, unchanged

```bash
# with PRODUCT_SET_RESOLVE_ENABLED unset/false in sorento_crm_backend/.env, then
# touch sorento_crm_backend/app/main.py to force the reload worker to pick it up
curl -s -X POST http://localhost:8050/api/v1/system/references/resolve \
  -H "X-API-Key: $EXTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"SRTWC8608-RL","allowed_entity_types":["product"]}'
```

Real response (flag OFF, captured mid-run by editing `.env` and forcing a reload, then restored
to ON before command 1's snapshot above was retaken to confirm it still works):

```json
{
  "tokens": ["SRTWC8608-RL"],
  "elapsed_ms": 249.05,
  "resolutions": [
    {
      "token": "SRTWC8608-RL",
      "resolved": false,
      "ambiguous": false,
      "matches": [],
      "alternatives": [
        {"entity_type": "product", "canonical_code": "SRTWCX8608-RL", "uuid": "762c9344-bdcb-4b07-8cfb-940bd596a350", "match_field": "product_code", "match_tier": "trgm", "similarity": 0.6666667, "company_id": "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f", "company_name": "Mocha", "display": {"product_name": "SRTWCX8608-RL", "is_variant": false, "brand": {"brand_id": "28445769-5687-436a-8c3f-a46a66c758a8", "brand_code": "SORENTO", "brand_name": "SORENTO"}}},
        {"entity_type": "product", "canonical_code": "SRTWCX8608-RL", "uuid": "0fb2507c-c6f3-47a1-ad10-296a3604aaea", "match_field": "product_code", "match_tier": "trgm", "similarity": 0.6666667, "company_id": "00000000-0000-0000-0000-000000000001", "company_name": "Sorento", "display": {"product_name": "SRTWCX8608-RL", "is_variant": false, "brand": {"brand_id": "438cab0b-ec83-4eae-bbcf-e1dc5bf7943c", "brand_code": "SORENTO", "brand_name": "SORENTO"}}},
        {"entity_type": "product", "canonical_code": "SRTWC8601-RL", "uuid": "f9edf11e-ffd1-4037-9628-e4042b17a0e4", "match_field": "product_code", "match_tier": "trgm", "similarity": 0.6, "company_id": "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f", "company_name": "Mocha", "display": {"product_name": "SRTWC8601-RL", "is_variant": false, "brand": {"brand_id": "28445769-5687-436a-8c3f-a46a66c758a8", "brand_code": "SORENTO", "brand_name": "SORENTO"}}},
        {"entity_type": "product", "canonical_code": "SRTWC8601-RL", "uuid": "0b537271-854f-4e14-a989-29572618a402", "match_field": "product_code", "match_tier": "trgm", "similarity": 0.6, "company_id": "00000000-0000-0000-0000-000000000001", "company_name": "Sorento", "display": {"product_name": "SRTWC8601-RL", "is_variant": false, "brand": {"brand_id": "438cab0b-ec83-4eae-bbcf-e1dc5bf7943c", "brand_code": "SORENTO", "brand_name": "SORENTO"}}},
        {"entity_type": "product", "canonical_code": "SRTWC8602-RL", "uuid": "bc299991-9340-4590-86b6-6cc58eb314c8", "match_field": "product_code", "match_tier": "trgm", "similarity": 0.6, "company_id": "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f", "company_name": "Mocha", "display": {"product_name": "SRTWC8602-RL", "is_variant": false, "brand": {"brand_id": "28445769-5687-436a-8c3f-a46a66c758a8", "brand_code": "SORENTO", "brand_name": "SORENTO"}}}
      ]
    }
  ],
  "unresolved_tokens": ["SRTWC8608-RL"]
}
```

`matches` is empty and `unresolved_tokens` names the code - exactly the failure mode the whole
feature exists to fix, and exactly what a `product`-hinted caller has always seen. The trigram
"did you mean" alternatives are a pre-existing, unrelated mechanism (nearest product codes) and
fire here only because nothing else matched.

## 3. Product-attachment linking with the set code

Setup (not a curl command - creating a row to attach a document to; a real upload is multipart and
not scriptable as a single copy-paste line, so this one step uses SQL instead of the API):

```sql
insert into attachments (id, original_filename, stored_filename, file_path, company_id)
values ('<new-uuid>', 'evidence.pdf', 'evidence.pdf', 's3://evidence.pdf',
        '00000000-0000-0000-0000-000000000001');  -- Sorento
```

```bash
curl -s -X POST http://localhost:8050/api/v1/external/product-attachments/ \
  -H "X-API-Key: $EXTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"attachment_id":"<new-uuid>","product_code":"SRTWC8608-RL"}'
```

Real response (single-link shape - the route has always returned the FIRST link it created, one
row, `order_by(product_code)` so "first" is stable call to call):

```json
{
  "attachment_id": "5d8b6215-40a8-4302-b950-88ef5c5dee06",
  "id": "0705a569-650e-4e4e-a478-d4f6a075614c",
  "company_id": "00000000-0000-0000-0000-000000000001",
  "product_id": "0fb2507c-c6f3-47a1-ad10-296a3604aaea",
  "is_primary": false,
  "linked_via_set_id": "608d64d6-93fe-4fa7-a84b-70879589b84c",
  "product": {
    "product_code": "SRTWCX8608-RL",
    "product_name": "SRTWCX8608-RL",
    "description": "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM) SRTWCX8608-RL"
  }
}
```

(Trimmed to the fields that matter; the real response also nests the full `attachment` and
`product` objects.) The API answers with the first link only - what actually got created is 3
rows, verified directly:

```sql
select p.product_code, pa.linked_via_set_id
from product_attachments pa join products p on p.id = pa.product_id
where pa.attachment_id = '5d8b6215-40a8-4302-b950-88ef5c5dee06'
order by p.product_code;
```

```
 SRTWC8608-SC  | 608d64d6-93fe-4fa7-a84b-70879589b84c
 SRTWCX8608-RL | 608d64d6-93fe-4fa7-a84b-70879589b84c
 SRTWCY8608    | 608d64d6-93fe-4fa7-a84b-70879589b84c
```

All 3 members, each stamped with the set's own id so the link can be found again if the set's
membership later changes (`ProductSetService._detach_set_fanout_links`).

## 4. Promotion linking with the set code

```bash
curl -s -X POST http://localhost:8050/api/v1/external/promotions/ \
  -H "X-API-Key: $EXTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "attachment_id": "<same-or-another-attachment-uuid-in-sorento>",
    "promotions": {"description": "example promo", "start_date": "2026-08-24", "end_date": "2026-12-31", "is_active": true},
    "promotion_products": [{"product_code": "SRTWC8608-RL"}]
  }'
```

Real response (trimmed to the promotion-products list - the full response also carries prices,
`promotion_type_*` classification and the group wrapper):

```json
{
  "promotion": {
    "description": "ZZT product-set n8n evidence promo",
    "id": "930b50d0-99a9-4ad0-a22f-4e60e9651b0e",
    "promotion_groups": [
      {
        "group_name": "Default",
        "promotion_products": [
          {"product_id": "0fb2507c-c6f3-47a1-ad10-296a3604aaea", "product": {"product_code": "SRTWCX8608-RL"}},
          {"product_id": "732adbfb-06cb-499f-8cd3-88bd16678655", "product": {"product_code": "SRTWCY8608"}},
          {"product_id": "ed83a177-81c0-46e7-9989-d484e54b9c9d", "product": {"product_code": "SRTWC8608-SC"}}
        ]
      }
    ]
  },
  "already_existed": false,
  "warnings": [],
  "unknown_product_codes": []
}
```

All 3 members land as `PromotionProduct` rows in one call, `unknown_product_codes` empty - before
this feature (and today, still, for promotions - promotions were never touched by this task's two
requirements) a set code landed in `unknown_product_codes` because promotions already went through
the shared resolver from an earlier slice (S2, `PLAN-product-sets.md` section 5). This command is
here because the task asked to prove it, not because it needed a code change in this pass.

## 5. Packing list create with the set code - the requirement-2 proof

```bash
curl -s -X POST http://localhost:8050/api/v1/external/packing-lists/ \
  -H "X-API-Key: $EXTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "packing_list": {
      "shipment_number": "PL-EXAMPLE-001",
      "attachment_id": "<attachment-uuid-in-sorento>",
      "shipment_date": "2026-08-24"
    },
    "packing_list_products": [
      {"product_code": "SRTWC8608-RL", "quantity": 5}
    ]
  }'
```

Real response (trimmed to `shipment_lines`):

```json
{
  "shipment": {
    "shipment_number": "ZZT-EVIDENCE-PL-001",
    "id": "b2c460a5-6c51-4bec-b6b7-b5ef157f4d79",
    "shipment_lines": [
      {"product_id": "0fb2507c-c6f3-47a1-ad10-296a3604aaea", "quantity_shipped": 5, "product": {"product_code": "SRTWCX8608-RL"}},
      {"product_id": "732adbfb-06cb-499f-8cd3-88bd16678655", "quantity_shipped": 5, "product": {"product_code": "SRTWCY8608"}},
      {"product_id": "ed83a177-81c0-46e7-9989-d484e54b9c9d", "quantity_shipped": 5, "product": {"product_code": "SRTWC8608-SC"}}
    ],
    "display_total_items": 15,
    "display_total_cartons": 3
  },
  "skipped_product_codes": [],
  "unknown_product_codes": [],
  "already_existed": false
}
```

Before this fix: `skipped_product_codes: ["SRTWC8608-RL"]`, no line created, `Surface 5` of the
contract note documented this as "UNTOUCHED... behaves exactly as it did before this feature."
After: one line per member, `skipped_product_codes` empty.

**The quantity question, answered explicitly:** the line said `quantity: 5` for the set code. Every
member line above reads `quantity_shipped: 5` - the SAME number, not split three ways and not
scaled by `ProductSetMember.quantity` (each member here happens to need 1 per set, so scaling would
not have shown a difference in THIS example, but the code does not scale regardless - see the
"packing-list quantity" section of the main report for the reasoning: nothing on a physical packing
slip says "how many complete sets" versus "how many of this one part," so multiplying by a per-set
count would be inventing a number nobody wrote on the document).

**The substring-tier question, decided, not open.** Command 5 above shows a genuine set code
fanning out to its members. It does not, by itself, show what happens when a packing-list line
carries a code that is merely a SUBSTRING of several real product codes and not a set code at
all - that risk is real and was raised, not overlooked: routing packing lists through the same
shared resolver means they gain the substring tier too, and on this surface a wrong match
creates a receiving line, inflating on-hand stock for the wrong SKU. The user was asked whether
to carve packing lists out of the substring tier and chose to keep the helper identical across
every surface instead, accepting the risk explicitly. This is settled, not a caveat still
waiting on an answer. Full reasoning and the worked `WC7601` example (5 sibling SKUs, one
receiving line each, full quantity on every line):
`documentation/plans/master-data/PLAN-product-sets.md` section 5 and
`documentation/plans/master-data/n8n-contract-product-set-entity.md` Surface 5.

## 6. A member code alone - it does NOT name its parent set (D13)

```bash
curl -s -X POST http://localhost:8050/api/v1/system/references/resolve \
  -H "X-API-Key: $EXTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"SRTWCY8608","allowed_entity_types":["product"]}'
```

Real response:

```json
{
  "tokens": ["SRTWCY8608"],
  "elapsed_ms": 42.47,
  "resolutions": [
    {
      "token": "SRTWCY8608",
      "resolved": false,
      "ambiguous": true,
      "matches": [
        {"entity_type": "product", "canonical_code": "SRTWCY8608", "uuid": "a6a0387e-a9ac-41fc-b07b-6e87291b334d", "match_field": "product_code", "match_tier": "exact", "company_id": "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f", "company_name": "Mocha", "display": {"product_name": "SRTWCY8608", "is_active": true}},
        {"entity_type": "product", "canonical_code": "SRTWCY8608", "uuid": "732adbfb-06cb-499f-8cd3-88bd16678655", "match_field": "product_code", "match_tier": "exact", "company_id": "00000000-0000-0000-0000-000000000001", "company_name": "Sorento", "display": {"product_name": "SRTWCY8608", "is_active": true}},
        {"entity_type": "product", "canonical_code": "SRTWCY8608-WEPLS", "uuid": "cf1a20ea-2386-4f0b-b164-3d48381b0039", "match_field": "product_code", "match_tier": "prefix", "company_id": "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f", "company_name": "Mocha", "display": {"product_name": "SRTWCY8608-WEPLS", "is_active": true}},
        {"entity_type": "product", "canonical_code": "SRTWCY8608-WEPLS", "uuid": "2008e12c-30e9-4801-8991-682c9cea8b92", "match_field": "product_code", "match_tier": "prefix", "company_id": "00000000-0000-0000-0000-000000000001", "company_name": "Sorento", "display": {"product_name": "SRTWCY8608-WEPLS", "is_active": true}}
      ],
      "alternatives": []
    }
  ],
  "unresolved_tokens": []
}
```

Every entry is `entity_type: "product"`. No `product_set` appears anywhere, and nothing in any
`display` block names `SRTWC8608-RL`. The `ambiguous: true` and the 4 rows are a SEPARATE, real,
pre-existing fact about this call - it is unscoped (no `contact_id`/`space_id`), the code exists in
both companies, and `SRTWCY8608-WEPLS` is a real sibling SKU that prefix-matches it. That noise is
orthogonal to D13; run the same call pinned to one company (`allowed_entity_types` plus a scoped
session, the way every production caller already is) and it collapses to exactly one `product` row,
still with no set mentioned.

---

## What was left in the database

Nothing. Commands 3, 4 and 5 each created rows (1 attachment + 3 `product_attachments`; 1
attachment + 1 promotion + 1 group + 3 `promotion_products` + 1 `promotion_attachments`; 1
attachment + 1 `inbound_shipments` + 3 `inbound_shipment_lines`) - all deleted after the responses
above were captured, verified by re-querying for zero rows matching the evidence attachment ids,
the `ZZT-EVIDENCE-PL-001` shipment number and the `ZZT product-set n8n evidence promo` description.
`product_sets`, `product_set_members`, `products` and `companies` counts are unchanged from before
this run (no set, member or product row was created or deleted - only link/junction rows were).
