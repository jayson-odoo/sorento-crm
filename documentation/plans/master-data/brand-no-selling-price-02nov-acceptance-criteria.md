# UAC: brands whose promotions carry no selling price (CABANA-NO-SELLING-PRICE)

Plan: `PLAN-brand-no-selling-price-02nov.md`. Tests: `sorento_crm_backend/tests/test_brand_no_promo_selling_price.py`,
`sorento_crm_frontend/app/(protected)/master-data-management/brands/components/BrandFormDialog.noPromoSellingPrice.test.tsx`.

- **AC-1 n8n drop.** `POST /api/v1/external/promotions` with a line for a flagged brand's product stores
  `promo_selling_price`, `discount_amount`, `discount_percent` as null, whether the flyer sent a selling price or an
  explicit discount. The line, its group and its dealer discount are saved. A non-flagged brand's line is unchanged.
- **AC-2 editor refusal.** Adding or editing a promotion line with a non-blank price on a flagged brand's product
  answers 400 "<Brand> promotions carry no selling price."; clearing the price is allowed and also clears the
  derived discount. A non-flagged brand saves as before.
- **AC-3 readers.** A flagged brand's promotion line yields no offer on price tags / dealer kit (tag shows list price;
  a hand-typed line price or combo price still wins), is never treated as a free RM 0 combo part, and the
  promotion-products API (MCP + chatbot) and promotion detail return `promotion_price`, `discount_amount`,
  `discount_percent` as null. Flipping the flag on another brand hides its values with no data change.
- **AC-4 brand master.** Master Data > Brands (modal, form page, detail page) shows a "Promotions carry no selling
  price" switch, off by default, saved as `no_promo_selling_price`, and the brand list returns it.
- **AC-5 migration.** `bnsp_0001_brand_no_selling_price` adds the column, sets it for brand code CABANA, copies the
  old three values of every flagged-brand line into `promotion_products_selling_price_backup`, then clears them.
  Re-running the data step changes nothing and keeps the first backup. Downgrade restores the values, drops the
  backup table and the column.
