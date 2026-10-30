# CARD - TAG-BRAND-CLASS: item classes on the tag Access settings, with or without All brands

Status: Plan (owner answered Q1-Q5 30 Oct ~11:50; mock `tag-brand-class-mock.html` awaiting his OK; no code). Lane TAG-BRAND-CLASS.
Track: full (new column + migration, contact access rule changes).

## Owner ask (30 Oct ~11:35)

"the ability for me to set class under each brand, should appear in tag also right, they are
unified ma, and when all brands are there, I also should be able to set the class also ma cause
for example sorento underneath got item classes, cause I want to set all sorento and mocha
dealer to not be able to access serene item class"

## What exists today (main b07f3f2a)

| Fact | Where |
| --- | --- |
| Contact brand access: `respond_contacts.brand_ids` ARRAY(UUID), NULL = every brand | `sorento_crm_backend/app/models/access.py:295` |
| Contact class access (ITEM-CLASS #1972): `brand_class_ids` JSONB `{brand_id: [class_id]}`, an INCLUDE list per picked brand | `app/models/access.py:296-299` |
| A class list only narrows a brand in `brand_ids`. With All brands (NULL) the contact is unscoped and any class list is ignored | `app/services/contact_brand_scope.py:72-110` (`_scope_tokens`, `contact_brand_scope` returns None when `brand_ids` is empty) |
| Include-list rule: inside a class-narrowed brand, a product with NO class is hidden | `contact_brand_scope.py:127-150` (`brand_predicate`) |
| Contact card UI: brand multi-select, then a "<brand> classes" picker under each picked brand ("All classes" placeholder) | `sorento_crm_frontend/components/contacts/ContactBrandScopeSection.tsx:45-104, 170-185` |
| Class options per brand = active classes some product of that brand carries | `app/services/item_class_service.py:71-89`; `app/api/v1/master_data/item_classes.py:48` |
| Item class master (ITEM-CLASS-MASTER #1988, contract 2.11): flat, no brand link; db1 has DIY + SERENE, db2 has DIY only | `documentation/plans/products/PLAN-item-class-master-29oct.md` section 1, D7 |
| Tag Access settings, Brands row: "All brands" switch or a brand pick list, nothing for classes | `sorento_crm_frontend/app/(protected)/user-management/contact-tags/components/ContactTagSettings.tsx:359-385` |
| Tag settings JSON `brands: "all" | [brand_id]`; validated by `_v_brands` | `app/services/contact_tag_settings.py:248, 477` |
| **How tags meet contacts:** tags never merge at runtime. Across a contact's tags, brands INTERSECT (`"all"` is neutral, empty result = conflict). Apply (preview, then write) makes the contact row equal the merged tag value; the runtime reads only the contact row | `contact_tag_settings.py:534-542, 586-587, 822-920`; `app/services/contact_tag_apply.py:375-466` |
| Applying a tag's brands today PRUNES the contact's class lists for brands the tag drops; a tag can never set a class | `contact_tag_apply.py:82-94` |
| Where brand (and class) access is enforced: the session stamp on X-API-Key + contact_id requests (MCP / n8n chatbot), the chatbot engine and business lane, entity resolver, SO / PO status lines, sales analysis, report ask, low stock, forecast, export tasks | `app/services/company_scope_resolver.py:255-269, 380-394`; `app/services/company_scope.py:407-415`; `product_in_scope_clauses` callers `order_service.py:1639`, `purchase_order_service.py:362,376`, `chatbot/so_status.py:96,128,385` |
| NOT enforced: staff screens (staff session), the portal (portal token gets company scope only), quotations | `company_scope_resolver.py:258-259` (docstring: "a staff session, a portal token ... is untouched") |
| Mocha has no brand rows (db2 has no ItemBrand), so a per-brand class rule never reaches a Mocha product | `contact_brand_scope.py:4-8`; PLAN-item-class-29oct.md section 4 (AC-11) |

## Why the real case does not fit today's rule

"Every Sorento and Mocha dealer, all brands, but no Serene" cannot be stored today, on a tag OR on
a contact:

1. With All brands the class list is ignored (`contact_brand_scope` returns None).
2. Picking SORENTO and narrowing it to "every class except SERENE" is an include list of DIY plus
   any other class. Every SORENTO product with NO class (AutoCount often sends "") would then be
   hidden (include rule, ITEM-CLASS Q3), and a class AutoCount adds next month would be hidden too.
3. Mocha products carry no brand, so no per-brand rule touches them.

So the ask needs an EXCLUDE rule: "hide these item classes", which works with All brands, keeps
products with no class visible, and lets new classes through by default.

## Proposed behaviour (pending answers)

- **B1 One control, two places.** The Brands block becomes one shared component used by the
  contact Brands card and the tag Access settings Brands row: brand pick (or All brands), then a
  "Hidden item classes" multi-select that shows in BOTH modes (All brands on, or brands picked).
- **B2 Rule.** A product whose item class is in the hidden list is out of scope for that
  contact, in every company and brand, branded or not. Products with no class and classes not
  listed stay visible. It stacks with the brand rule (brand allowed AND class not hidden).
- **B3 Tags.** Tag setting `hidden_item_classes: [class_id]`. Across a contact's tags the lists
  UNION (any tag hiding Serene hides it), the rule `excluded_warehouse_ids` already uses
  (`contact_tag_settings.py:582`). Apply writes the union onto the contact, preview first, as every
  other section does.
- **B4 Where "no access" bites:** everywhere brand scope bites today: chatbot / MCP answers
  (product search, price, stock, SO and PO status lines, packing list), sales analysis, report
  ask, low stock, forecast and chatbot exports. Not the portal, not staff screens, not quotations
  (brand scope does not reach them today either).
- **B5 Fewest steps for the real case:** Contact tags > the dealer tag (or a new "No Serene" tag)
  > Access settings > Brands > leave All brands on > Hidden item classes: SERENE > Save > Apply
  to holders (preview shows N contacts gaining "Hidden item classes: SORENTO SERENE SERIES").

## Examples (pending crew-data-request)

To fill from dev data before the mock (request posted on the PR): (1) the SERENE class rows per
company and how many products carry them, by brand; (2) how many SORENTO products have no class;
(3) existing tags that look like Sorento / Mocha dealer tags and their holder counts; (4) contacts
with a non-empty `brand_class_ids` today; (5) one dealer contact per company with its brands and
companies, to walk through B5.

## Questions (max 5, each with a recommendation)

- **Q1 Include or exclude?** (a) add a "Hidden item classes" exclude list; (b) keep only the
  per-brand include list and make it work with All brands. **Recommend (a):** the real case is an
  exclusion, an include list hides every no-class product and every future class, and it cannot
  reach brandless Mocha products.
- **Q2 Per brand or flat?** (a) one flat hidden list under the Brands block (any brand);
  (b) a hidden list under each brand. **Recommend (a):** AutoCount ItemClass has no brand link
  (contract 2.11 D7), Serene only sits on SORENTO, and (b) cannot express "all brands" or Mocha.
- **Q3 The existing per-brand include picker (#1972):** (a) keep it on contacts and mirror it on
  tags too; (b) retire it in favour of the hidden list. **Recommend (b) if no contact uses it in
  dev data (example 4), else (a):** two class rules on one card is the confusing part; one rule
  is the simplest thing that works.
- **Q4 Tag and contact disagree:** (a) the existing apply model: preview, then the tags' union
  overwrites the contact's hidden list; (b) the contact's own extra hidden classes survive an
  apply. **Recommend (a):** every other tag section works this way and the preview shows it.
- **Q5 Reach:** (a) same surfaces as brand scope today (B4); (b) also the portal product
  pickers. **Recommend (a):** the portal is not brand-scoped today; extending it is its own lane.

## Owner answers (30 Oct ~11:45 and ~11:50)

- **Q1 (b)** an ALLOW list of item classes that also works with All brands on. The side effect
  (no-class products and future classes are hidden unless allowed) is accepted: the owner manages
  it per tag and re-applies to the tag's holders.
- **Q2 (a)** one flat list under Brands, shown with All brands on or off, and it reaches
  brandless products (every Mocha-company product has no brand on dev).
- **Q3 (b)** remove the per-brand include picker from #1972 (no contact on dev uses it).
- **Q4 (a)** the existing apply model (preview, then the tags' value overwrites the contact).
- **Q5 (a)** the same surfaces as brand scope today.

## Decisions for the build (proposed in the mock, pending the owner's OK)

- **D1 Storage.** `respond_contacts.allowed_item_class_codes` TEXT[] (NULL = every class), and
  the tag setting `item_classes: [code]` inside the Brands section. Codes, not ids: AutoCount
  ItemClass is flat and the same code (DIY) lives in both books, so one option per code covers
  both companies. A reserved code `__none__` stands for "No class".
- **D2 Rule.** A product passes when its brand passes the brand rule (unchanged) AND, if the
  contact has a class list, its class code is in the list (no class passes only when "No class"
  is in the list). Not per company: the list applies in every company, branded or not.
- **D3 No class.** "No class" is the first option and is ticked for you when the first class is
  picked (it can be unticked). Why: almost every AutoCount item has no class today.
- **D4 New classes** are hidden until ticked (that is what an allow list means).
- **D5 Tag merge.** Across a contact's tags the class lists INTERSECT, as Brands do; an empty
  result is a conflict that is written by neither (`_m_regions`). Unset is neutral.
- **D6 Retire #1972's per-brand picker** (crew ruling 30 Oct, option b): `brand_class_ids` STAYS
  in the schema but nothing reads or writes it any more. The scope tokens `<brand>/<class>` go,
  the contact card loses its per-brand rows, and access copy carries the new column instead. No
  DROP in this lane: crew cannot prove the column is NULL on prod, and a drop needs the owner.
  Follow-up: a later cleanup PR drops the column once prod is checked.
- **D7 One shared FE block** "Brands + Allowed item classes", used by the contact Brands card and
  the tag Access settings Brands row.
