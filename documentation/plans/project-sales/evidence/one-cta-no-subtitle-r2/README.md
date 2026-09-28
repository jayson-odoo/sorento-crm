# Round 2 evidence: CRM-wide one CTA, no subtitle; progressive Register a project (PR #1336)

agent-browser 0.27.0 against the lane dev server (HMR) and a freshly bootstrapped database, every
page reached by sidebar clicks from `/`. No page scrolls sideways at 375 (`scrollWidth` 375).

| File | Shows |
| --- | --- |
| `pipeline-1280.png`, `pipeline-375.png` | Pipeline: title and trail only, one header CTA (Start). |
| `parties-1280.png`, `parties-375.png` | Parties: title and trail only, one header CTA (Add party). |
| `register-1-open-1280.png`, `register-1-open-375.png` | Register a project opens on Who and what; Details (optional) collapsed; no subtitle; Check beside Project title, off until 4 characters. |
| `register-2-check-1280.png` | Check pressed: "No existing project matches this title." inline under the field. No request was sent while typing. |
| `register-3-expanded-1280.png` | Developer, Project type, Project title and Template filled: Details opened by itself. No helper line under Project launch date. |
| `register-4-duplicate-1280.png`, `register-4-duplicate-375.png` | Same title again after registering it: Check shows the blocking match inline and Register reads "Blocked by an existing project". |
| `certificates-1280.png`, `certificates-375.png` | Master Data > Certificates, empty: "No data available" with no button in the empty state; Add Certificate stays in the toolbar. |
| `integrations-1280.png`, `integrations-375.png` | System > Messaging > Integrations: the description line under the title is gone; the empty state has no button. |
