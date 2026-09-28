# Round 3 evidence: quotation page header dedupe (PR #1336)

agent-browser 0.27.0 against the lane dev server (HMR) and a freshly bootstrapped database with one
seeded project (Cabana Elmina Phase 2, developer Nadi Cergas Sdn Bhd) and one draft quotation
(PRJQ/0001). Reached by sidebar clicks from `/`: Project Sales > Pipeline > the project > Quotations
tab > the PRJQ/0001 row. No page scrolls sideways at 375 (`scrollWidth` 360).

| File | Shows |
| --- | --- |
| `prjq-1280.png`, `prjq-375.png` | Title PRJQ/0001 and the trail, then the Draft pill, the project title and the developer. No document number line under the breadcrumb. The card ends at Attn: no project title line under the TO block. Our Ref keeps the number, as the letterhead field it is. |
