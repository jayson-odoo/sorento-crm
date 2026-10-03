# UAC: product ref collision (code-first, owner ruling 3 Oct)

Owner, 3 Oct: "when we match product, it is by product code, we don't really care about the source
ref." Product identity = company + normalised product code, for the product feed and for every
document line. `source_ref` is link/audit only: a ref hit never overrides a code match, never renames
a product, and never binds a line whose code names no product.

## Product feed
AC-1 (prod case) Mocha holds product `2001`; product `MKT4524SS-DIY` holds ref `AED_V2_MOCHA:2001`.
Push ItemCode `2001` (ref `AED_V2_MOCHA:2001`): product `2001` updated; `MKT4524SS-DIY` unchanged
(code, name, every column); no failure; ref stays on `MKT4524SS-DIY`; warning `ref_mismatch`. Same
outcome in dry run.

AC-2 (silent rename) No product `2004`; product X holds `AED_V2_MOCHA:2004`. Push ItemCode `2004`:
product `2004` created; X unchanged; ref stays on X (new product not linked); warning
`ref_mismatch`; no failure.

AC-3 Ref and code agree: product updated as today, no warning.

AC-4 Code owner has no ref and the pushed ref is free: product updated and linked under the pushed
ref (audit link, unchanged adopt behaviour). Code owner already holds a different ref: product
updated, stored ref kept (unchanged code-wins behaviour).

## Document lines (SO, PO, SPO, billing documents; DO/GRN already code-only)
AC-5 Line ref and code agree: binds that product, no warning.

AC-6 Line ref names product A, line code is owned by product B: binds B, warning `ref_mismatch`,
A untouched, no failure even when B holds no ref (the ref is not moved onto B while A holds it).

AC-7 Line code owned by no product: the existing unknown-product path for that document type
(SO/PO/SPO: retryable missing product; billing: `product_unresolved` warning, NULL product). The
ref is never used as a fallback, so a line can never bind the ref holder.

AC-8 Line sends no product code at all: the ref resolves as today (nothing to disagree with).

## Both
AC-9 Code comparison is case- and edge-whitespace-insensitive, same normalisation as the existing
code lookup.

AC-10 Same batch: two records hitting the same foreign ref both obey AC-1/AC-2.
