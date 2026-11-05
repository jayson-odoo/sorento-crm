# PLAN: Price tag combo format (rich description, LP/SP templates, designer preview image)

Status: Waiting on PR #2172 merge (mock v2 approved by the owner 5 Nov ~10:25 MYT; font Q1 (a) per crew). UAC + red test list written. Track: full (migration, shared editor change, security review).

Lane: PRICETAG-COMBO-FORMAT.

Owner feedback, 5 Nov 2026: description formatting close to the printed flyer; LP vs SP wording per template
(tie one template to LP or SP; a product/combo links one or more of each); designer picture uses the existing
preview function.

Card: `CARD-pricetag-combo-format-05nov.md` (posted as crew-ask, 5 Nov). Mock: `pricetag-combo-format-mock.html`.

Owner answers to v1 (5 Nov ~10:00 MYT): rich text = the app's engine, made complete with colour (shared
component, not a one-off); existing descriptions formatted by hand (no script); template price type
hand-selected LP / SP / LP & SP (existing templates start unset and stay offered on both until set);
combo photo thumbnail opens full size in `AttachmentPreviewModal`; designer changes dropped.

UAC: `pricetag-combo-format-acceptance-criteria.md` (AC-1..AC-43). Red test list (tester, Phase 2):
`pricetag-combo-format-test-list.md`. Slices: S1 shared editor, S2 sanitiser + write paths, S3 parser and
renderers, S4 product-page editors, S5 template price type, S6 per-type defaults, S7 line filtering,
S8 combo photo preview. One migration (S5 + S6 together).
