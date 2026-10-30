# UAC - TAG-BRAND-CLASS

Plan: `PLAN-tag-brand-class-30oct.md`.

- **AC-1** A contact with All brands and allowed classes "No class, DIY" is not shown a SERENE
  product by the chatbot / MCP (session criterion, output guards, line clauses), and is shown DIY
  products, products with no class, brandless Mocha-company products with no class, and Mocha
  DIY products.
- **AC-2** A class code AutoCount adds later is hidden from that contact until it is ticked.
- **AC-3** Brands and classes stack: SORENTO only + classes "DIY" shows only SORENTO DIY
  products (other Sorento-company brands stay out by the brand rule; other companies keep the
  per-company brand rule and get the class rule).
- **AC-4** No allowed list (NULL or []) means every class; the scope of a contact with neither
  brands nor classes is None (unscoped), so deploy changes nobody's access.
- **AC-5** One option per class code: DIY in two companies is one option and allows both.
- **AC-6** Contact Profile > Brands shows the brand picker and one "Allowed item classes" picker
  (no per-brand rows). Picking the first class also ticks "No class"; it can be unticked. Save
  stores the codes; an unknown code is a 422.
- **AC-7** Tag Access settings > Brands shows the same class picker under the All brands switch,
  with All brands on or off. The tag stores `item_classes: "all" | [code]`; an unknown code is a
  422.
- **AC-8** Two tags on one contact: the class lists intersect; nothing in common is a conflict
  that Apply never writes. "all" or unset is neutral.
- **AC-9** Apply preview lists "Allowed item classes: All classes -> No class, DIY"; apply
  writes it; a second apply changes nothing.
- **AC-10** Copy access carries the allowed classes with the Brands facet.
- **AC-11** Deleting an item class that products carry is refused while any contact has an
  allowed list.
- **AC-12** `brand_class_ids` is no longer read or written; a stale value in it changes nothing.
- **AC-13** Usable at 375px and 1280px.
