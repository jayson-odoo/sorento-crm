# SUPPLIER-COST-ACCESS browser pass (10 Nov 2026, sandbox DB sorento_ci, dev server, agent-browser)

Seed: `seed_cost_access.py` (ZZT data; logins zzt.sales@example.com / zzt.buyer@example.com). The `.test` TLD is
rejected by the login email validator, hence example.com. The seed also installs all tenant modules, else the
sidebar is empty on a blank DB.

Sales (no products.cost.view), 1280px: Overview shows List Price + Invoice Price only; tabs are Overview, Stock,
Attachments, Combos, Promotions, Variants, Audit Trail, Specifications, Lineage (no Suppliers, no Purchase History);
no Cost Price, no Last purchase price; Audit Trail reads "Cost price changed (values hidden)" by ZZT Buyer with
date; edit form tabs Basic Information, Pricing, Specifications, Attachments, Lineage; Pricing has List and
Invoice only; sidebar has no Procurement group. 375px: no horizontal scroll (scrollWidth == clientWidth).
API: GET product-suppliers/product/{id} 403 for Sales, 200 for Buyer.

Buyer (with it), 1280px: Procurement > Product-Suppliers in sidebar; Purchase History + Suppliers tabs; Pricing
Summary shows MYR 125.00 Cost Price and a Last purchase price card; Suppliers tab lists ZZT-SUP, 9.99; Audit
Trail "Cost price: 120.00 -> 125.00"; edit form has Suppliers tab and Cost Price input (125).

No page errors (`errors` empty after every step).
