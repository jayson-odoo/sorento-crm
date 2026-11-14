# PLAN: Give the AI agent the right tools, and feed it only what it needs (AGENT-CONTEXT-BUDGET)

Status: Plan v2.1, 14/11/2026 (invoice lookup added to slice 4, owner idea 14/11). Owner decisions taken 14/11/2026 19:27 (section 8). Slice 1 is built by lane
TARGET-ACHIEVED-PERF; slice 2 (short tool menu, size M) is next in this lane on its own branch and PR.
Track: each slice in section 7 is its own lane (S or M); the tool menu slice is M.
Read from `main` eefbcc3c. Paths: BE = `sorento_crm_backend/app/`. Every figure below is from stored
agent turns or from the code; nothing real (names, prices, phones) is in this doc (public repo).

---

## In one paragraph

Today the agent is handed a menu of about 54 tools on every single step of a question, and that menu is
about 92 % of everything it reads. It is like handing someone the whole phone book each time they
ask for one number. At the same time it is missing some of the tools it needs: it cannot look up an
order inquiry, a quotation by its number, a record's history, or a product's spec. And the one sales
question the owner tried ("sales for my dealers this year vs targets") is slow because the target
figures are filtered after the whole table is loaded. The plan: **(1)** give it a short, well-described core
toolset plus a "find more tools" step, the way Claude Code itself works; **(2)** add the missing lookup
tools, each giving a short answer and each built on the function the screens already use; **(3)** pre-feed
only the record in focus plus a short summary; **(4)** then watch every question against time and size
targets (no hard cut-off that ends an answer early, owner 14/11).

---

## 0. What we measured (60 recent agent turns, extract from crew, 14/11/2026)

The extract held 60 console agent turns (all test turns; no live WhatsApp or panel turns fell in the
window) from the last 21 days. Token counts are the provider's own. "Chars" are characters.

| Per question (turn) | Median | p90 | Worst |
|---|---|---|---|
| Time to answer | 15 s | 44 s | 55 s |
| Input tokens, whole question | 39,700 | 91,600 | 172,900 |
| ...of which served from the provider's cache | 22,700 | 75,700 | 120,300 |
| Output tokens (thinking + answer) | 1,300 | 6,900 | 8,400 |
| Model calls | 4 | 6 | 8 |
| Input tokens, biggest single step | 22,400 | 32,600 | 35,700 |
| Tool menu sent with each step (chars) | 95,200 | 97,800 | 100,600 |
| Tools on the menu | 53 | 54 | 56 |
| Instructions (system prompt, chars) | 8,050 | 8,440 | 8,470 |
| Earlier conversation resent (chars) | 0 | 2,260 | 4,280 |
| Data the tools returned, whole question (chars) | 1,760 | 8,000 | 10,850 |
| Time inside tools, whole question | 0.15 s | 1.4 s | 20 s |

What each part of one step costs (staff panel, all permissions; from the code, chars / 4 = tokens, estimated):

| Part of one step | Chars | Tokens (est.) | Share of step 1 |
|---|---|---|---|
| Tool menu (54 tools) | 99,300 | 24,800 | 92 % |
| - of which 21 older catalogue tools, mostly repeated parameter text | 63,100 | 15,800 | 58 % |
| - of which the list of data areas inside the query tool | 4,050 | 1,000 | 4 % |
| Instructions | 8,400 | 2,100 | 8 % |
| - of which the user-guide rules, added to every question, sales included | 3,080 | 770 | 3 % |
| Earlier conversation | 0 to 4,300 here | 0 to 1,100 | small today |
| Data returned by tools | median 1,760 per question | ~440 | small today |

What this tells us:

1. **The tool menu is the cost, not the data.** Tool results and history are small. Capping tool results or
   squeezing history would save little. **Measured on the same tool** (projects list, 13 turns with a short
   menu of 29 tools vs 6 turns with the full 53): biggest step 13,400 vs 30,700 tokens, whole question
   30,000 vs 61,300 tokens, answer 11.2 s vs 13.5 s.
2. **Time is the model's time.** In 56 of 60 turns more than 99 % of the wait is the model. It grows with
   the number of steps and with how much the model writes: a proposal comparison writes 4,400 output tokens
   (median) and takes 37 s.
3. **The sales-vs-target turns are the exception** (4 turns): 10-20 s inside the query tool,
   100,000-140,000 input tokens, 3 of 4 hit the time limit. Cause: target figures for every agent and period
   (up to 2,000) are computed and only then filtered (`services/assistant_registry/computed.py:347-362`).
   The instructions also send the model round in circles: "resolve every name first", "show invoiced,
   delivered and ordered" (the loop then refuses the second one, `services/chatbot/agent/loop.py:2301`),
   "use the report tool" (the biggest tool, 9,700 chars, which keeps the full menu on).
   A gap or % the model works out itself is then rejected by the figure check
   (`loop.py:709-724`), which costs one more full step.
4. **Prompt caching already works for this setup**: 56 % of input tokens were served from cache. Keeping
   the start of each step identical (instructions + core tools) protects that.

Caveat: the extract's "owner case" flag sits on a contacts batch turn (n=31); the four query turns n=52-55
match the sales-vs-target shape. Per-step JSON for all 60 turns is on crew's machine.

---

## 1. What each assistant is given today, and what it can fetch

All agent surfaces run through one loop (`services/chatbot/agent/loop.py:1523`). They differ in who is
asking and which tools stay open.

| Surface | Pre-fed today | Tools it can call |
|---|---|---|
| CRM AI panel (staff, agent rollout) | Instructions; up to 6,000 chars of the screen's text; record facts only on complaint, stock inquiry, purchase request and sponsorship pages (`services/record_context_service.py:123-126`); every earlier turn since the last summary, with its attached-file text again (`services/chatbot/agent/memory.py:135-147`); pictures on every step (`loop.py:1962`) | All the user's permitted tools: about 54 (`chatbot/agent/tools.py:114-149`, `writes.py:487-512`) |
| Proposal comparison | Not its own surface: the panel on a project page. The project comes from the page address (`services/chatbot/panel_service.py:170-175`) | The quotation-lines tool (`tools.py:389-417`, `quotation_lines.py:86`) plus the panel's tools. **No product spec or stock beside it** |
| Chat console (operator acting for a contact) | Earlier bot replies of the run (`console_service.py:700-725`) | As WhatsApp, narrowed to what BOTH operator and contact may see |
| WhatsApp bot, customer | Instructions only, history | 9 customer tools, each behind a per-contact switch (`tools.py:153-166`); no list price, no targets, no order status tools |
| WhatsApp bot, linked staff user | Instructions, history | Panel tools minus the panel-only ones |
| Old AI assistant (users without the agent rollout) | Instructions, the whole screen text, record facts, a guide | Top 3 admin-enabled catalogue tools picked by keyword (`services/ai_assistant_service.py:1207-1214`) |

## 2. Questions it cannot answer today, or answers slowly

| Question | Today | Gap |
|---|---|---|
| Product spec (size, material, description) | Not in the product data the agent can query (`services/assistant_registry/products.py:40-50`); the product finder returns code, name, brand, category only (`tools.py:1245-1254`) | **Missing** on every surface; the catalogue tool that has dimensions is not offered (`sorento_crm_mcp/catalog.py:58`) |
| List price | Panel: the query tool, product list price | WhatsApp customer: none |
| Stock | Raw rows per product per warehouse | **Too coarse**: no "total available per code" answer |
| Sales order status | Status word only | The bot already works out "partly delivered" (`services/chatbot/so_status.py`); the agent cannot |
| Order inquiry status | none | **Missing** |
| Quotation by its number | Only via the project (title or project code, `api/v1/projects/projects.py:269`) | **Missing** |
| Invoice by number or customer | Only as rows of the query tool's billing data; no own-dealers rule (`services/assistant_registry/finance.py`) | **Too coarse**: no "show me invoice X with its lines"; no PDF copy is stored (header + lines only) |
| History of a record | Only the four record kinds above, only with that page open | **Missing**: no History tool anywhere |
| Sales vs target | Works but slow (section 0, point 3) | **Too slow**, filters after the full load |
| Sales figures | Three tools bypass the one shared sales function: order analytics "total value" on delivery orders (`api/v1/order_management/orders.py:1008-1016`), the older sales report (SO lines), summing order totals in the query tool | Breaks the standing rule "every sales figure from the one shared sales function" |

The agent's own "I have no tool for this" notes and the unanswered-question tables were not in the
extract (free text); they are the first input for the eval prompts of slices 3-5.

---

## 3. Proposed toolset (tools first)

Shape, copied from how Claude Code works: a **short core menu** the agent always sees, each tool with one
clear job and a short answer; a **"find more tools" step** that loads the rest by meaning when needed; and
the general **query + describe** pair to crawl any data area. Every tool is built on the function the
screens already use (one function, reused), and checks the asker's permission inside.

| Tool (working name) | Answers | Returns (short) | Built on (reuse) | Surfaces | Permission |
|---|---|---|---|---|---|
| Product lookup | spec, list price, cost (if allowed), active, brand, category, by code or name | one compact card per product, up to 10 | ONE product reader replacing four (`tools.py:1198-1232`, `assistant_registry/products.py`, catalogue `crm_master_products_list`, `crm_find`) | panel, console, WhatsApp | cost only with `products.cost.view` (`products.py:12,44`); WhatsApp customers get spec + list price, never cost (D3) |
| Stock lookup | available, on hand, next arrival, per code, optionally per location | one line per code (+ per location on ask) | existing stock balance + incoming stock services (`api/v1/inventory/stock.py:241`) | panel, console (staff) only | `inventory.stock.view`. WhatsApp customers keep the existing chatbot stock route, which controls stock visibility (owner 14/11) |
| Document by number | any number: sales order, delivery order, invoice, quotation, order inquiry, purchase request, complaint | type, status, delivery progress, customer, dates, link | `so_status.py` (progress), the list services of each document | all (WhatsApp: own documents only, as today) | the document's own view / view-own slug |
| Invoice lookup (owner 14/11: "give me invoice") | an invoice (also cash sale, debit and credit note) by its number, or a customer's invoices by customer and period | the invoice header (number, date, customer, agent, amount) and its item lines; a customer's list capped with "more" | the stored AutoCount invoices (`models/finance.py:63`, `BillingDocument` + `BillingDocumentLine`) and `invoiced_sales` for amounts (one sales function) | panel, console, linked user; WhatsApp customer: own invoices only (to confirm in slice 4's card) | `finance.billing_documents.view`, own dealers only unless "see all" (D2) |
| Record history | "who changed what, when" on one record | the History tab's entries, newest first, capped with "more" | the backend behind the shared History tab | panel, console | same as the record |
| Sales vs target | target, achieved, gap, % per agent or dealer | one row per owner, gap and % computed by the server | target achievement service (`services/sales/...achievement_service.py:641-762`) over `invoiced_sales`, filters pushed into SQL | panel, console, linked user | `sales.targets.view` / `view_own` |
| Query + describe (kept) | anything else in a data area | as today (cards past 10 rows) | as today | as today | as today |
| Find more tools (new) | "I need a tool for X" | names + one line each, then the chosen tool's full form | the existing tool registry (`tools.py:114`) | all | only tools the asker may use |

Retired or merged (no second copy of logic): order analytics "total value" stops answering sales (sales go
through `invoiced_sales` only); the four product readers become one. The old AI assistant is out of
scope here; it should later move onto the same loop (a separate decision, not in this plan).

## 4. Pre-feed only the minimum

| Pre-fed today | Proposed | Saving (tokens per step) |
|---|---|---|
| Up to 6,000 chars of screen text | The record in focus as short facts (number, status, customer, totals) for every record page, not just four; screen text only on pages with no record | up to ~1,500 (estimated) |
| User-guide rules in every question (3,080 chars) | Moved into the guide tool's own description | ~770 (measured chars) |
| List of tools the user may not use (0-1,600 chars) | Kept short: one line naming the areas, not every tool | up to ~400 (measured chars) |
| Attached-file text resent on every later turn | Sent on its own turn; later turns keep a one-line note plus the summary | file-sized (estimated) |
| Every turn since the last summary | Last 4 turns word for word plus the summary (history is small today, so this guards future long chats) | small today (measured) |

## 5. Budgets and rules (second)

| Rule | Today | Proposed | Tokens saved | Seconds saved | Risk to answer quality |
|---|---|---|---|---|---|
| Core menu + find-more-tools | 54 tools, ~24,800 tokens every step | ~12 core tools, ~6,000 tokens; others loaded on demand | ~17,000 per step (measured on the projects-list pair) ; median question 39,700 -> ~20,000 (estimated) | ~2 s median (measured pair), more on long questions | Medium: the model must ask for a tool it does not see. Guard: the find step matches by meaning; eval set below |
| Sales vs target: filters in SQL, gap and % from the server, instruction conflicts removed | 100-140k tokens, ~50 s, 3/4 timed out | 2 model calls | ~100,000 per question (estimated) | ~35 s (estimated; tool time 10-20 s measured) | Low: same figures from the same function |
| Steps per question | up to 8, then a forced final answer | Design goal 4 for questions, 6 for bulk changes and comparisons, reached by better tools, never by cutting off. Only a runaway-loop safety stop stays, at today's 8 steps | p90 6 -> 4 calls (estimated) | ~7 s per step avoided (median 3.4 s per call measured) | None from a cut-off: the stop is far above normal use and still gives a full best answer from what was found, never a "limit" message |
| Input size | 150,000 per question, counted over all steps (`loop.py:2487`) | Targets 12,000 per step and 40,000 per question, logged and alerted when exceeded; the 150,000 safety stop stays | from the core menu, not from a cap | - | None: nothing is cut |
| Tool answers | up to 16,000 chars each | new lookup tools return compact cards (~1,000-2,000 chars); 16,000 stays for comparison | small (results are small today) | - | Low |
| Retries that cannot help | the query cap counts "describe" and refused calls (`loop.py:2292`); 5th call in a step refused | count only real queries; describe free | one step on some questions (3 of 60 had refused calls) | ~4-7 s on those | None |
| Thinking effort per step | medium on every step | low for single lookups, medium kept for comparisons and multi-part (owner 14/11 set medium for comparisons) | output tokens on lookups (estimated -30 %) | 2-5 s on lookups (estimated) | Low-medium; checked on the eval set before it ships |
| Summary of older chats | same model as the answer | a lighter model (side call only) | cost, not tokens | ~1-3 s when it runs (estimated) | Low |
| Keep the start of each step identical | menu changes after step 1, breaking the cache | core menu fixed, loaded tools appended at the end | keeps 56 % cache hit, likely higher (estimated) | small | None |

Targets after all slices (to check with the same extract): **median 10 s / p90 25 s; median 20,000 /
p90 40,000 input tokens per question; 4 steps or fewer unless it changes data.** These are targets and
alarms, not cut-offs (owner 14/11: "I would rather wait if it is within reason than you say hit limit").
A question over a target still gets its full answer; it is logged and shows in the weekly readout.

---

## 6. Quality guard: the agent must not get worse

1. **Baseline first, at US$0:** before slice 1, crew replays the frozen owner-FAIL set for the agent
   (crew's eval data dir, `documentation/agents/chatbot-verification.md:108-133`; agent engine
   `scripts/chatbot_eval/engine.py:148`) in recorded mode and keeps the scores plus tokens and seconds per case.
2. **Offline tests on every slice (US$0):** `tests/chatbot/agent/test_agent_bulk_w4_owner_fail.py`,
   `test_agent_owner_feedback.py`, `test_agent_proposal_insights.py`, `scripts/chatbot_eval/gold/*.jsonl`
   (sales targets: 16 rows), plus two new eval prompts per new tool (standing rule), each with a typo, a
   greeting and a non-English phrasing.
3. **Live x1, capped US$0.50**, per slice, on the frozen set's dev part, crew ledger, asked first. Pass =
   no case that passed in the baseline now fails, and tokens / seconds per case are not higher.
4. **Live x3 before the slice's merge** (crew's hidden run, about US$2 a run, owner's call), same pass rule.
5. Every slice's crew-done reports the 60-turn table of section 0 again on its eval run: median / p90 / worst.

## 7. Work order (small, hand-testable slices)

| # | Slice | Size | Hand test | Target |
|---|---|---|---|---|
| 1 | **Sales vs target, fast and right** (built by lane TARGET-ACHIEVED-PERF, not this lane): filters in SQL, gap and % from the server, instruction conflicts fixed, query cap counts real queries only | S-M | Panel: ask "how are my dealers' sales this year against their targets?", then "and last year?", then a typo version | answer in 2 model calls, under 35,000 tokens, under 15 s, no timeout; figures equal the targets screen |
| 2 | **Short tool menu + find more tools** | M | Panel: ask a stock question, a complaint question, a contact change; each still works | first step under 10,000 tokens; p90 question under 45,000 tokens; frozen set not worse |
| 3 | **Product lookup and stock lookup**, panel incl. proposal comparison; one product reader | M | On a project page: "compare the two quotations", then "what is the size of the first item?", "what is its list price?", "how many are in stock?" | each follow-up 1 tool call, under 8 s; cost shown only to cost holders |
| 4 | **Document by number + invoice lookup + record history** (SO progress, order inquiry, quotation number; invoice by number or by customer and period, permission-scoped) | M | Panel: type a quotation number, an order inquiry number, "give me invoice <number>", "invoices for <customer> last month", "who changed this SO and when?" | 1 tool call each, under 8 s; invoice lines and amount equal the stored invoice; a salesperson without "see all" gets only their own dealers' invoices; history equals the History tab |
| 5 | **Pre-feed minimum**: record facts for project, SO, quotation and product pages; guide rules moved; file text not resent | S-M | Open a sales order, ask "what's the status?" then change page and ask about the new record | instructions + page facts under 4,000 tokens per step |
| 6 | **Targets and monitoring, no cut-offs**: each question's steps, tokens and seconds checked against the targets; over-target questions logged with their cause and alerted; the runaway-loop safety stop (8 steps / 150,000) answers with a full best answer from what was found and never says "limit"; thinking effort per step; summary of older chats on a lighter model | S | Ask a long multi-part question: it answers in full (no "limit" words), and it shows in the over-target log | p90 under 25 s on the eval set; zero replies containing a limit message |
| 7 | **WhatsApp customer toolset** per D3: product lookup with spec + list price (no cost), own documents' status; stock stays on the existing chatbot stock route | M | From a test contact: spec of a product, its list price, "is it in stock?" (answered by the existing stock route, same as today), status of own order by number | 1 tool call each; stock answers unchanged; nothing beyond the contact's switches |

Each slice is one lane, one PR, its own UAC written after this plan is approved.

## 8. Decisions taken (owner, 14/11/2026 19:27)

Owner's words: "D1 ok, D2 b yeap, D3 hmm i think stock check all those still is chatbot route, cause we
need to control the visibility of stock, list price is fine, D4 hmm i think limiting quite bad la, I would
rather wait if it is within reason than you say hit limit, imagine if I ask you and you say hit limit I
also angry".

| # | Question | Decision |
|---|---|---|
| D1 | How the agent sees its tools | **(c)** short core set always, plus a "find more tools" step |
| D2 | Salesperson sees only own dealers' sales | **(b)** own dealers only unless the "see all" permission, same as the targets screen |
| D3 | WhatsApp product facts for customers | **New option**: spec + list price yes. Stock stays on the existing chatbot stock route (it controls stock visibility); no new agent stock tool on WhatsApp |
| D4 | Budgets | **No hard cut-offs** that end an answer with "hit limit". Budgets are targets + monitoring (log and alert when exceeded) and design goals for slices. Only a runaway-loop safety stop remains, far above normal use (today's 8 steps / 150,000 tokens), and it still gives a full best answer |
| D5 | Order | No answer; crew takes the recommended order: 1, 2, 3, then 4, 5, 6, 7. Slice 1 goes to lane TARGET-ACHIEVED-PERF |

---

## 9. Owner standing rules that apply

Each slice's reviewer ticks these with file:line: "Understanding comes from the semantic parser"
(the find-more-tools step matches by meaning, never a word list); "Every sales figure from the one shared
sales function"; "Reuse functions, not only components" (one product reader, document lookup reuses
`so_status.py`); "Replies one fact per line as Label: value"; "Replies never show internal ids";
"The bot states only what the data holds"; "A capped list ends with Reply more"; "Every new list screen
and record action can be read and done by the assistant (two eval prompts)"; "A chat fix is checked on
varied real phrasings and follow-ups"; "When the ask is unclear the bot asks one short question";
"A value that cannot be worked out shows -"; "Every date reads dd/mm/yyyy".

## 10. Sources

- Turn extract: crew data request on PR #2419, 60 turns, 14/11/2026 (masked numbers only).
- Static attribution and surface inventory: read-only analysis of `main` eefbcc3c (file:line above).
- Earlier: AGENT-PANEL-FIXES (11/11/2026, 89k-token panel turns); root cause of the commission timeout
  (filters applied after the full query, `computed.py`; query cap counting describe, `loop.py:89`).
