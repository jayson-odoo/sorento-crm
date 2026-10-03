# UAC: product ref collision

AC-1 (prod case) Company Mocha holds product `2001`; product `MKT4524SS-DIY` holds ref
`AED_V2_MOCHA:2001`. A product push for ItemCode `2001` updates product `2001`, leaves
`MKT4524SS-DIY` (code, name, every column) unchanged, records no failure, and carries warning
`ref_mismatch`. The ref stays on `MKT4524SS-DIY`. Same in dry run (no failure reported).

AC-2 (silent rename) No product `2004` exists; product X holds ref `AED_V2_MOCHA:2004`. A push for
ItemCode `2004` leaves X unchanged and creates product `2004`; the ref stays on X; warning
`ref_mismatch`; no IntegrityError.

AC-3 (agreeing ref) A ref whose product's code equals the pushed ItemCode still updates that
product (unchanged behaviour).

AC-4 (line, normal) An SO line with product_ref `AED_V2_MOCHA:2001` and ItemCode `MKT4524SS-DIY`
binds `MKT4524SS-DIY`, no warning.

AC-5 (line, collision) An SO line whose product_ref hits product A but whose ItemCode is owned by
product B binds B and carries `ref_mismatch`. If no product owns the ItemCode, it binds A and
carries `ref_mismatch`.

AC-6 Code comparison uses the same normalisation as the code-adopt path (case/whitespace).

AC-7 Same-batch: two records in one batch hitting the same foreign ref both obey AC-1/AC-2 (preload
maps do not leak the wrong id).
