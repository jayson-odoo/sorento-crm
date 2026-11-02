# PLAN: brands whose promotions carry no selling price (Cabana)

Status: Build (normal track: carries a migration with a data clear). Lane CABANA-NO-SELLING-PRICE.

## Why

Owner, 2 Nov 2026: Cabana products have no selling price. The n8n flyer reader hallucinated one
onto every Cabana promotion line, and price tags, the chatbot and MCP show it.

## Scope

1. Brand column `no_promo_selling_price` (bool, default false), admin-editable on
   Master Data > Brands. Migration sets it true for brand code CABANA.
2. Writers drop the selling price (and the discount derived from it) for such brands:
   external promotions API (n8n) and the promotion editor.
3. Readers never show a selling price for such brands: price tags (Selling mode,
   `dealer_kit/pricing.py::_offer_prices`, the one offer read under `resolve_prices`,
   `line_pricing`, `free_part_ids`), and `PromotionProductResponse` (promotion-products API and
   promotion detail), which is what MCP and the chatbot read.
4. Data migration clears `promo_selling_price`, `discount_amount`, `discount_percent` on those
   lines, backing the old values up into `promotion_products_selling_price_backup` so the
   downgrade restores them.

## Embeddings: no re-queue (finding)

`promotion_product` is outside the embedding keep set (`embedding_settings.py` RECORD_KEEP_SET):
the queue refuses it and search never serves it, so `embedding_worker.py`'s promotion-product
body is not what the chatbot reads and a re-queue would insert nothing. The `promotion`
embedding carries no prices. The chatbot reads prices via MCP from the promotion-products API,
which is masked (3).

## Single helper

`app/services/promo_selling_price.py::brand_has_no_selling_price(product)`. Trigger for anything
more (per-company or per-promotion rules): a second brand with a different rule.

## n8n (crew, owner publishes)

The flyer workflow should send `selling_price: null` for Cabana lines. The API drops it anyway.

Details and UAC follow in `brand-no-selling-price-02nov-acceptance-criteria.md`.
