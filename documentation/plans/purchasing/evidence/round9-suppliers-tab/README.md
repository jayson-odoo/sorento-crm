# Round 9 browser evidence: product Suppliers tab as data grids (#1305)

agent-browser 0.27.0, headless Chromium (`/opt/pw-browsers/chromium-1194`), session `r9`.
Stack: backend on :8000 against the cloud lane database (`scripts.bootstrap_env` schema, the
`commercial_plus` bundle installed so the sidebar renders), frontend `npm run dev` on :3000.

Seed (direct SQLAlchemy insert): a superadmin; product `CB2548SS-BL-DIY`; supplier `400-0002`
XIAMEN TAIYANG TECHNOLOGY (primary, lead time 30, CNY 40.60, minimum order 100, multiple 10)
with two cost rows, 吊卡 CNY 40.60 from 1 Sep 2026 with no end and 彩盒 CNY 42.00 from 1 Sep 2026
to 31 Dec 2026; supplier `400-0009` NINGBO BETA HARDWARE with no cost rows.

Reached by sidebar clicks from `/` (Products > Products > All Products > CB2548SS-BL-DIY >
Suppliers).

| Shot | What it shows |
| --- | --- |
| `01-suppliers-grid-1280.png` | The supplier grid: Supplier code, Supplier name, Primary, Lead time (days), Unit cost, Currency, Minimum order, Order multiple, Their code; search box; no subtitle. |
| `02-cost-prices-open-1280.png` | 400-0002 clicked: the cost price grid under the row, Packaging method, Cost, Date start, Date end; 吊卡 CNY 40.60, start 1 Sept 2026, end "-"; 彩盒 CNY 42.00, 1 Sept 2026 to 31 Dec 2026. Page text holds no CPC code, "Always" or "no end". Page scrollWidth 1265 at 1280. |
| `03-no-cost-prices-1280.png` | 400-0009 clicked: the grid empty state, "No cost prices for this supplier." |
| `04-cost-prices-375.png` | 375: the open cost grid, scrolling sideways inside its card; page scrollWidth 360, no horizontal page scroll. |
| `05-cost-prices-dates-375.png` | 375: the cost grid scrolled to Date start and Date end. |

The month reads "Sept" here: `formatPlainDate` is `Intl` en-GB and this Chromium's ICU spells
September that way; the owner's browser may read "Sep". Unchanged by this round.
