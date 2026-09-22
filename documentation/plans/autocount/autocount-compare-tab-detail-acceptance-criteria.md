# UAC: AutoCount pull Compare tab detail

Plan: `PLAN-autocount-compare-tab-detail.md`. Small fix track.

| ID | Criterion | Verified by |
| --- | --- | --- |
| CT-1 | An `is_active` difference shows `Active` / `Inactive` in Your Excel and AutoCount pull cells (and their tooltips), never blank, never `true`/`false`. | vitest, browser |
| CT-2 | Headline names both counts when they differ: `N items differ (M differences)`; just `N items differ` when equal. | vitest |
| CT-3 | Every code in `only_in_excel` is a grid row labelled `Only in your Excel`; every code in `only_in_pull` a row labelled `Only in AutoCount`. Stock rows split `code|location` into the Item Code and Location columns. | vitest, browser |
| CT-4 | Grid `recordCount` equals differences + only-in rows; Download differences writes exactly those rows with the same formatted values. | vitest |
| CT-5 | Difference column shows human labels (Description, Item Group, Item Brand, Price, Active, On Hand Qty). | vitest, browser |
| CT-6 | 100% match path unchanged: no grid, green headline. | existing vitest |
| CT-7 | Usable at 375px and 1280px, no horizontal page scroll. | browser |
