# UAC - AutoCount Item Class (ITEM-CLASS)

Plan: `PLAN-item-class-29oct.md`. Owner answers 29 Oct: Q1 (a), Q2 (a), Q3 as proposed, Q4 (a).

## Sync (shared service + CRM ingest)
- **AC-1** The shared service maps AutoCount `ItemClass` to `item_class_code` on every product row,
  right after `item_type_code`, on the push payload and the pull snapshot; blank or absent
  ItemClass is omitted, never `null`. Existing product tasks get the row (module Alembic 0034,
  `update_tenant` from below 0.20.0, an empty task keeps its first-save preset seed).
- **AC-2** A CRM product push with an unknown `item_class_code` back-creates one item class
  (code = name = value), links the product and warns `item_class_created`; the same code in any
  case/spacing reuses the row; absent leaves the stored link untouched, blank clears it (crew
  ruling 29 Oct, security M1: the class narrows access, so a class AutoCount cleared must not
  linger); classes are per
  company; `GET /external/contract` lists the field and the warning.

## Reference data, list, form
- **AC-3** Reference Data > Item Classes: DataGrid list (code, name, product count, status, search),
  modal create, detail page with in-place edit (the Brands pattern), deferred hard delete. Duplicate code (any case) is a 409.
  Delete clears the product link and is refused (409) while a contact is limited to the class.
  Gated by `master_data.item_classes.{view,add,edit,delete}`; every role holding the matching
  `master_data.brands.*` slug is granted it by the migration.
- **AC-4** Products list: Item Class column after Brand, sorted server side by class name (no
  class last), multi-select filter (`item_class_id`).
- **AC-5** Product form and detail: optional clearable Item Class select after Brand (View = Edit);
  an unknown class id is a 422.

## Contact access by class within brand
- **AC-6** Contact Profile > Brands: each chosen brand whose products carry at least one class
  gets an optional "<brand> classes" multi-select ("All classes" when empty). Save stores
  `{brand_id: [class_id]}`; classes of brands no longer chosen are dropped; an unknown class is a
  422.
- **AC-7** A brand with no class list keeps every product of that brand, including products with
  no class. A brand limited to classes shows only products of those classes; its products with
  no class are hidden. Other brands and other companies are unaffected (per-company rule).
- **AC-8** AC-7 holds everywhere brand scope applies, through the one rule
  (`contact_brand_scope.brand_predicate` + its output-guard twin): chatbot product search /
  quote / stock answers, line totals (orders, PO, incoming stock, reports), complaints, portal /
  MCP calls carrying a contact, and report/export jobs that carry the scope to the worker.
- **AC-9** A class list for a brand the contact is not allowed is ignored (it never grants a
  brand); a contact with no brand list stays unscoped; a stale class id hides that brand's
  products (fail closed).
- **AC-10** Nothing changes for any existing contact on deploy (`brand_class_ids` NULL).
- **AC-11** db2 (Mocha) items carry no brand, so a class limit only takes effect where a brand
  exists; unbranded companies stay unrestricted as today.
