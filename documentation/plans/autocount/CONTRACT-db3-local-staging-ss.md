# CONTRACT: Shared Service side of the local db3 staging (lane AC-TEST-COMPANY)

What a **local** foundryx-shared-service (SS) copy must hold so a local CRM copy, seeded by
`sorento_crm_backend/scripts/staging/seed_db3_staging.py`, can test every AutoCount integration
against the AutoCount **db3** test book. Local only; nothing here touches prod SS or prod CRM.

**Verified vs inferred.** CRM-side facts are verified with a `file:line` reference. The SS repo
could not be read from the sandbox that wrote this, so SS table and setting names are **not**
given. Every SS item says what must be true and points at the existing SRT/db1 setup to copy.
Where this document says "same as SRT/db1", the SS operator copies that company's setup and
changes only the company code and the book.

## 1. Identity values (must match the CRM seed)

| Value | CRM side | SS side |
| --- | --- | --- |
| Company code | `companies.code = SRT_DB3` (seed default `--company-code`) | SS company code `SRT_DB3` |
| Book | rows arrive with `book = db3` | SS company bound to the **db3** connection ONLY (hapi `/api/db3/...`) |
| CRM -> SS key | `foundryx-esb` credentials `api_key` (seed env `STAGING_SS_API_KEY`) | an SS API key that can see company `SRT_DB3` |
| SS -> CRM key | `integration_api_keys` row on `foundryx-esb` (seed env `STAGING_SS_PUSH_KEY`, or minted and printed) | the `X-API-Key` SS sends on every push to the local CRM |
| CRM base URL | - | SS's CRM push target = the local CRM backend, e.g. `http://localhost:8000` |
| SS base URL | `foundryx-esb.config_json.base_url` (seed `--ss-base-url`) | where the local SS listens |

How the CRM names the SS company:
- Every pull and write sends `companyCode = companies.code`
  (`app/services/foundryx_autocount_client.py:173,236`;
  `app/services/scm/stock_debt_po_link_service.py:490,520,548,577,602`).
- Every push is resolved by its body `companyCode` (`app/api/v1/external/company_anchor.py:135-161`).
- The CRM never sends a book. The book only comes back inside `source_ref` (`{book}:...`), e.g.
  `db3:BR:300-T001:HQ`.

## 2. SS company `SRT_DB3`

- Company code `SRT_DB3`, with the db3 connection and no other connection. The hand-test clone DB
  `foundryx_service_qtso_ht` already has this company; copy that row.
- Writes allowed for this company (it is the test company). On #2173's branch the CRM maps
  `WRITE_COMPANY_NOT_TEST`, `WRITE_DISABLED` and `WRITE_NOT_ALLOWED` to "Changes to AutoCount are
  switched off here" (`claude/ac-qtso-crm-phase-2-1n1ffk`,
  `documentation/plans/autocount/PLAN-ac-qtso-crm-04nov.md`). If write-capabilities answers one of
  those reasons, this flag is the thing to check.
- The db3-only write guard (SS `guard.py` allowlist) stays on and unchanged. It is the brake that
  keeps db1/db2 safe.

## 3. Pushes: hapi db3 -> CRM ingest

Do the same as the SRT/db1 hourly poll, with `companyCode=SRT_DB3, book=db3`, reading
`GET /api/db3/...`. Target: `POST {CRM}/api/v1/external/ingest/{entity}`
(`app/api/v1/external/ingest.py:1000`). Deletions go to `.../{entity}/deletions` (:1177).

Envelope: `{"companyCode": "SRT_DB3", "book": "db3", "records": [...]}` (book validation `ingest.py:821-830`).
Proven on a seeded local copy: a `branches` push with this envelope landed in SRT_DB3 as
`db3:BR:300-T001:HQ`.

CRM ingest entities (`INGEST_PERMISSIONS`, `ingest.py`): products, product_categories,
units_of_measure, warehouses, suppliers, customers, sales_agents, brands, item_classes,
sales_orders, purchase_orders, shipping_orders, stock_balances, billing_documents,
delivery_orders, goods_receive_notes, branches, cancel_sales_orders, cancel_purchase_orders,
consignments, consignment_returns, ar_outstanding.

| hapi db3 endpoint (owner list, 5 Nov) | CRM ingest entity |
| --- | --- |
| `location` | warehouses (inferred) |
| `itembypage` | products (inferred) |
| `debtorbypage` | customers (inferred) |
| `creditorbypage` | suppliers (inferred) |
| `ItemGroup` / `ItemType` / `ItemCategory` | whatever the SRT/db1 poll maps them to (product_categories / products fields) |
| `ItemBrand` | brands (inferred) |
| `ItemClass` | item_classes (`app/services/item_class_service.py:1-2`) |
| `salesagent` | sales_agents (contract `PLAN-autocount-cross-repo-contract.md:97-101`) |
| `taxcode`, `terms` | whatever the SRT/db1 poll does; the CRM drops terms today (contract :388-408) |
| `itemuombypage` | units_of_measure (inferred) |
| `itembatchbalqtybypage` | stock_balances (inferred) |
| `branchbypage` | branches (contract :757, proven above) |
| `purchaseorder{bydocdate,byLastModified,Justnow}` | purchase_orders, or shipping_orders when `ShippingPO='T'` / DocNo `SPO...` (same split as SRT/db1) |
| `goodsreceivenote{...}` | goods_receive_notes (contract :628-712) |
| `salesorder{...}` | sales_orders |
| `deliveryorder{...}` | delivery_orders (contract :628-712) |

Order on a fresh copy: masters first (warehouses, products, UOM, brands, item classes,
customers, suppliers, sales agents, branches), then stock_balances, then documents (PO/SPO, SO,
GRN, DO). Document lines need their product and warehouse to exist first (contract :696-699).

## 4. Calls the CRM makes to SS (must answer for `SRT_DB3`)

| CRM call | Path on SS | CRM file |
| --- | --- | --- |
| Pull snapshots (products, stock_balances, delivery_orders, goods_receive_notes) | `POST /api/v1/autocount/snapshots`, `GET .../snapshots/{id}`, `GET .../snapshots/{id}/rows` | `foundryx_autocount_client.py:178,188,196` |
| Connection test | `GET /api/v1/autocount/snapshots/{nil uuid}` | `foundryx_autocount_client.py:274` |
| Write capabilities | `GET /api/v1/autocount/write-capabilities?companyCode=SRT_DB3` | `foundryx_autocount_client.py:234` |
| PO line link / unlink / relink / relocate / resume (#2168) | `POST /api/v1/autocount/po-links`, `.../po-links/unlink`, `.../po-links/relink`, `.../write-operations/{id}/resume` | `stock_debt_po_link_service.py:490,520,548,577,602` |
| Project QT / SO create, update, cancel, document read (#2173, not on main yet) | `/api/v1/autocount/quotations...`, `/api/v1/autocount/sales-orders...`, `GET /api/v1/autocount/documents/{kind}/{doc_key}` | branch `claude/ac-qtso-crm-phase-2-1n1ffk`, `project_autocount_write_service.py` |

## 5. Snippet for crew (adapt names to the SS schema)

Copy these from the hand-test clone `foundryx_service_qtso_ht` into the local SS database: the
`SRT_DB3` company, its db3 connection, and its write-allowed setting. Then:

```
SS company:        SRT_DB3   (connection: db3 only; writes allowed; guard allowlist unchanged)
SS -> CRM push:    base_url = http://localhost:8000   X-API-Key = <STAGING_SS_PUSH_KEY>
                   envelope companyCode=SRT_DB3 book=db3; same entity list + schedule as SRT/db1
CRM -> SS key:     an SS key whose company scope includes SRT_DB3  -> STAGING_SS_API_KEY
SS listens on:     http://localhost:<ss port>                      -> --ss-base-url
```

Acceptance on the local pair:
1. `GET /api/v1/autocount/write-capabilities?companyCode=SRT_DB3` answers with the PO-link ops
   enabled.
2. A `branches` push lands in the CRM under SRT_DB3 with `source_ref` starting `db3:`.
3. A CRM products pull from inside SRT_DB3 reaches preview.
