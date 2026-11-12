# Behaviour card: AGENT-QUOTE-COMPARE (10 Nov 2026)

Owner question (prod, project page PPF2611004): "compare the two quotation for this project". 8 rounds, 152,593 tokens
in, ended "The agent could not answer: the model provider failed."

## Causes found (file:line, base 92a32cd6af)

a) Page id refused. The project page sends its UUID only inside `page_snapshot.path` (`/project-sales/<uuid>`,
   `sorento_crm_frontend/app/(protected)/project-sales/pipeline/components/PipelineBoard.tsx:118`), carried as a
   user note (`panel_service.py:166-212`, `loop.py:1771`). `seen_ids` starts empty each turn (`loop.py:1801`) and is
   filled only from tool results (`tools.py:1331`, `:931`), so the page's own UUID fails `_check_ids`
   ("Unknown id", `tools.py:704-705`). The wording proves a UUID was sent (a code gets the "not codes or names"
   message, `tools.py:700-703`).
b) The refusal sends the model to the wrong tool. "get ids from crm_resolve first" (`tools.py:705`), but
   `crm_resolve` cannot find projects (kinds: product, supplier, brand, customer, category, sales_agent,
   `tools.py:197-204`); its description says "Call this before any tool that takes an id" (`tools.py:331-333`). The
   model then guessed `term`, then `kind/text` (real args `terms`, `kinds`, `tools.py:338-339`); the refusal says only
   "Unknown argument(s): term." (`tools.py:842-844`, same pattern for MCP tools `tools.py:1259-1261`).
c) Final quotations call "error" = any non-4xx exception from the MCP call (`tools.py:1306-1314`). Reproduced one
   500 on dev: a `project_id` with a leading/trailing space passes every check (each layer strips only to check), then
   `quotations.py:144-145` drops `validate_uuid_path`'s cleaned value and Postgres raises `invalid input syntax for
   type uuid` at `project_service.py:1033`. Second candidate (UNVERIFIED): a JSON list in `project_id` passes
   `_id_args` (`tools.py:668-682`) and FastMCP rejects it (`server.py:1680`, `project_id: str`). Every other shape on
   PPF2611002/03/04/05/06/08 returned ok. The prod turn's `agent_tool` args (`loop.py:2049-2059`) and the backend log
   line "agent: tool crm_project_quotations_list failed" would say which; dev cannot (incident is prod-only).
d) Not a context overflow (about 19k tokens per call; Gemini flash, `loop.py:59`). The turn hit the round cap 8 /
   token cap 150k (`loop.py:2105-2111`, `Budgets` `loop.py:182-187`); `forced_final` (`loop.py:1818-1832`) makes one
   more model call with no guard; any provider error or `TimedOut` (a RuntimeError, `llm_call.py:112-118`) becomes
   `_ProviderFailed` (`loop.py:1656-1658`) and lands in `loop.py:2139-2140`: every fetched result in `ledger` is thrown
   away and the reply is the bare "could not answer" (`loop.py:2151`). Provider error text is not traced (`loop.py:1012`).
   The 152k came from 8 calls each resending ~15-19k of prompt + tool schemas, not from big results (results capped
   16k chars, `tools.py:28`). Fixing a-c makes this question ~3 rounds.
e) No agent tool returns quotation lines. `crm_project_quotations_list` returns one row per scope with totals, no
   lines, no revision letter (`project_quotation_service.py:1481-1501`; MCP strips `current_version_id`,
   `server.py:1421-1436`). The lines route exists (`quotations.py:491-506`) but is not API-key readable and has no MCP
   entry. `crm_query` has no quotation entity (`app/services/assistant_registry/*`).

## Proposed rules

R1 Page record id counts as shown: UUIDs in the open page's path seed `seen_ids` at turn start. Access is unchanged:
   the tool still runs as the user with the route's own checks; `seen` is only the made-up-id guard.
R2 An "Unknown id" refusal names where the id comes from (the page, or the finder for that record:
   `crm_projects_find` for `project_id`), never crm_resolve for a kind it cannot search. `crm_resolve`'s description
   lists what it can and cannot resolve.
R3 Every "Unknown argument(s)" refusal also states the accepted arguments and their shape (e.g. `crm_resolve takes
   {"terms": [text, ...], "kinds": [product|supplier|...]}`).
R4 Id arguments are forwarded clean: stripped and lower-cased UUID; a list sent to a single-id argument is refused
   ("one id"). Backend `list_quotations` uses the cleaned id (a 500 becomes a normal answer).
R5 New panel read `crm_project_quotation_lines` (in process, as the user, same READ slugs as the quotation routes
   `quotations.py:72`, project via `get_project_or_404`): `project_id` + optional `refs` (document numbers such as
   PRJQ-2026-0006, or an issued revision such as PRJQ-2026-0007-B). Returns per document/scope: ref, scope, version,
   total, and compact lines (code, description, qty, uom, list price, unit price, discount %, line total). The
   model compares and answers with one compact table. No refs = every document's current version.
R6 Never a bare failure after tools ran: if the final answer call fails, the reply is built in code: "I could not
   finish the answer (the model did not respond in time | the model provider returned an error). What I read: <tool
   labels>." plus any code-built table; status `limited`. The provider's error class and status go into the trace.

## Real examples (dev DB sorento_prod_1104)

| Project | Documents | What the owner should get |
|---|---|---|
| PPF2611002 | PRJQ-2026-0006 Master Bath v2, 2 lines, 430.00 (R1); PRJQ-2026-0014 Test, 1 line, 360.00 (A); QT-2026-0004 1 line, 360.00 (R1) | 3 documents: agent asks which two, or compares all three in one table |
| PPF2611008 | PRJQ-2026-0013 Main, 3 lines, 9,050.00 (A); QT-2026-0003 Main, 3 lines, 9,050.00 (R1) | "compare the two quotation": side by side, lines, same totals |
| PPF2611003 | PRJQ-2026-0007 Townouse, 1 line, 360.00, revisions A-D | "compare revision A and D": the issued revisions' lines |
| PPF2611005 | PRJQ-2026-0009 Area One 360 + Area Two 480 (grand 840, A); PRJQ-2026-0019 ZZT Block A, 3 lines, 12,300.00 | multi-scope document: totals per scope + grand total |
| PPF2611006 | PRJQ-2026-0011 Draft Area X/Y, 0 lines | empty edge: says the draft has no lines |

## Edge cases

- Project with one document: says there is only one; offers its revisions if several were issued.
- More than two documents and "the two": compares all in one table (or asks), never picks silently.
- A user with view_own only: same answer as the quotation screen gives them (same route rules).
- Lines over the 16k result cap: the tool caps rows and says how many more.

## Questions (recommendation first)

Q1 Revisions: (a) refs accept an issued revision (PRJQ-2026-0007-B) as well as a document, so "compare A and B"
   works (owner B14, 2 Nov: compares revisions); (b) current versions only. Recommend (a): `quotation_issue_scopes`
   already pins each revision's versions (`models/projects.py:1759`), no new data.
Q2 How lines reach the agent: (a) one in-process panel tool (R5), one call answers; (b) expose the lines route over
   MCP (route to API-key auth, new catalogue entry, MCP keeps `current_version_id`), 2+ rounds per comparison and a
   route permission change. Recommend (a).
Q3 Wrong argument names: (a) refusal states the exact shape (R3), no alias list; (b) also accept term/text/query as
   terms and kind as kinds. Recommend (a): no word lists, one self-correcting round.
Q4 After a failed final call: (a) code-built partial reply (R6); (b) (a) plus one retry of the final call. Recommend
   (a): a retry in a turn that already ran out of time fails the same way.
Q5 Cause (c): (a) fix both candidates now (R4) and crew reads the prod turn's `agent_tool` args / backend log line to
   confirm which it was; (b) wait for the prod trace before fixing. Recommend (a).
