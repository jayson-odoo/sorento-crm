# PLAN: brands whose promotions carry no selling price (Cabana)

Status: Plan (small fix track candidate, but carries a migration, so normal track). Lane CABANA-NO-SELLING-PRICE.

## Why

Owner, 2 Nov 2026: Cabana products have no selling price. The n8n flyer reader hallucinated one
onto every Cabana promotion line, and price tags, the chatbot and MCP show it.

## Scope

1. Brand column `promotions_carry_selling_price` (bool, default true), admin-editable on
   Master Data > Brands. Migration sets it false for brand code CABANA.
2. Writers drop the selling price (and the discount derived from it) for such brands:
   external promotions API (n8n) and the promotion editor.
3. Readers never show a selling price for such brands: price tags (Selling mode), chatbot index,
   MCP presenter.
4. Data migration clears `promo_selling_price`, `discount_amount`, `discount_percent` on those
   lines, backing the old values up into a table so the downgrade restores them, then re-queues
   embeddings for the affected products.

## n8n (crew, owner publishes)

The flyer workflow should send `selling_price: null` for Cabana lines. The API drops it anyway.

Details and UAC follow in `brand-no-selling-price-02nov-acceptance-criteria.md`.
