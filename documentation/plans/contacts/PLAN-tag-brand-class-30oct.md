# PLAN - TAG-BRAND-CLASS: allowed item classes under Brands, on tags and contacts

Status: Build (Phase 2 backend + frontend). Track: full (migration + contact access rule change).
Card: `CARD-tag-brand-class-30oct.md` (owner answers Q1 b, Q2 a, Q3 b, Q4 a, Q5 a; mock
`tag-brand-class-mock.html` approved 30 Oct 12:17 with the three proposals). UAC:
`tag-brand-class-acceptance-criteria.md`.

## 1. Journey

Owner: every Sorento and Mocha dealer must not see the SERENE item class. He opens the dealer tag
> Access settings > Brands, keeps All brands on, sets Allowed item classes to "No class, DIY",
saves, and applies the tag to its holders. The chatbot and MCP then never list, price or quote
stock for a SERENE product to those contacts. The contact Profile > Brands card shows the same
block.

## 2. Measured facts (main b07f3f2a)

See the card's "What exists today" table. Added here:

| Fact | Where |
| --- | --- |
| Scope carriers pass the frozenset of strings through untouched (session stamp, RQ args, turn ctx `scope_brand_ids`, brand guard, alternatives) | `chatbot/lanes/business/brand_guard.py:71-95`, `alternatives.py:94-101` |
| Every `brand_predicate` caller already passes `Product.item_class_id` | `company_scope.py:415`, `order_service.py:265`, `report_ask.py:704`, `contact_brand_scope.py:278,483` |
| Python twin callers query `Product.item_class_id` | `contact_brand_scope.py:202-257, 425-456` |
| Access copy carries `brand_classes` | `contact_access_copy_service.py:223, 269-281, 329-334, 364-366, 703-718, 802, 919` |
| Item class delete guard reads `brand_class_ids` | `item_class_service.py:150-174` |
| Tag writer prunes `brand_class_ids` | `contact_tag_apply.py:82-94` |
| Alembic head | `agp1_0001_agent_foundation` |

## 3. Design

- **D1 Storage.** `respond_contacts.allowed_item_class_codes` VARCHAR(50)[] NULL. NULL or [] =
  every class. Codes are stored upper-cased and trimmed. `__NONE__` stands for "No class".
  `brand_class_ids` stays in the schema, unread and unwritten (crew ruling b); a later cleanup
  PR drops it.
- **D2 Scope tokens.** The scope stays a frozenset of strings: a brand id per allowed brand (as
  today) plus `class:<CODE>` per allowed class code. `contact_brand_scope` returns None only when
  both lists are empty. The `<brand>/<class>` tokens are gone.
- **D3 Rule** (`brand_predicate`, the one place): brand part unchanged when the scope names a
  brand, TRUE when it names none; class part, when the scope names a class: `class_col IN (ids of
  item_classes whose upper(code) is listed)`, OR `class_col IS NULL` when `__NONE__` is listed.
  Brand part AND class part. The class part ignores company and brand (Mocha products have no
  brand). Python twin: the helpers read the class CODE through an outer join.
- **D4 Contact card API.** `GET/PUT /contacts/{id}/brands` drop `brand_class_ids`/`item_classes`
  and carry `allowed_item_class_codes: [code]` plus `item_class_options: [{code, name}]` (active
  classes, one per code, name from the first row by name; "No class" first). PUT refuses an
  unknown code with 422 `UNKNOWN_ITEM_CLASS` (a code is known when an item class row with it
  exists in the caller's company scope, or it is `__NONE__`).
- **D5 Tag section** `item_classes`: `"all"` or `[code]`, validated like the card. Merge across
  tags = intersect, `"all"` neutral, empty = conflict (the Brands rule). Reader: the contact's
  list, `ALL` when empty. Writer: `_w_columns` sets the column. The Brands writer no longer touches
  class data. Gate: `user_management.contacts.edit` (as Brands).
- **D6 Access copy** carries `item_classes` (codes) inside the Brands facet; the Brands text reads
  `All brands; classes: No class, DIY`.
- **D7 Delete guard.** Deleting an item class is refused (409) while products carry it AND some
  contact has an allowed list: the delete would turn those products into "No class" and change
  what those contacts see.
- **D8 FE.** One shared component `components/contacts/BrandClassAccessBlock.tsx` renders the
  class picker (SearchableMultiSelect, clearable, "All classes" placeholder, "No class" first,
  auto-ticked when the first class is picked). The contact Brands card uses it under its brand
  picker and loses the per-brand rows; the tag Brands row uses it under the All brands switch /
  brand pick list.

## 4. Tests (red first)

- `tests/test_allowed_item_class_scope.py` replaces `tests/test_item_class_scope.py` (the
  per-brand behaviour is retired): rule, All brands + classes, Mocha brandless, No class, future
  class, guards, line clauses, card read/write.
- `tests/test_item_class_scope_paths.py`, `tests/test_item_class_copy_access.py`,
  `tests/test_item_class_api.py` (delete guard), `tests/test_contact_brand_scope_api.py` updated.
- `tests/test_contact_tags_item_classes.py`: validate, merge, evaluate, apply.
- vitest: `BrandClassAccessBlock.test.tsx`, `ContactBrandScopeSection.test.tsx` updated,
  `ContactTagSettings` brands row.

## 5. Out of scope

Portal, staff screens, quotations (Q5 a). Dropping `brand_class_ids` (later cleanup PR).
