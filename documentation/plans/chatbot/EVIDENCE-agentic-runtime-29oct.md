# Agentic CRM runtime investigation

Read-only investigation, 29 October 2026. Main evidence is commit `3a097ebbea`, extracted at `/private/tmp/sorento-agentic-discovery-20261028`. Paths below are relative to that root unless marked **Oct29**. The script evidence was read with `git show 3a097ebbea:<path>` because the snapshot omits scripts. A final delta check covers `98773e5aa9`; it does not replace the pinned baseline.

This is discovery for the parent agent, not an approved UAC or implementation plan. No application edits, live model calls, tests, deployment, or business writes were performed. Source review establishes implementation behavior, not production model/prompt settings or vendor compatibility for a newly selected model.

## Assessment

There is substantial reusable infrastructure: semantic grounding, contact-scoped conversational state, a real model/tool iteration loop, provider adapters, immutable prompt versions, traces, and durable incoming-message processing. The smallest credible extension is a console task runner using those foundations and existing business operations. Increasing the assistant's model size or loop count alone is insufficient.

The missing unit is a delegated business task that survives a turn: its requested outcome, authorized actor, pending decision, completed action receipts, unfinished work, and evidence of completion. The current assistant stops at prose or one pending tool call. Its tool transcript and tool outputs are transient. Existing inbox durability and stock quantity collection do not supply a general action ledger.

The owner has already settled internal staff, console first, per-contact enablement, linked-user RBAC, semantic instructions, and separately configurable reasoning. Form submission, approval, rejection, and the other existing CRM operations remain the product scope. No new sales follow-up product, prescribed phrases, or sales-only boundary is implied by this report.

## Existing seams and their limits

| Area | Verified source behavior | Reuse and limit |
| --- | --- | --- |
| Mention grounding | `sorento_crm_backend/app/services/chatbot/head/span_extract.py:97` resolves its own prompt/model and `:135` extracts typed spans. `head/list_resolver.py:344` resolves them; scoring supports exact, spelling, partial, and calibrated semantic signals (`:43`, `:68`, `:361`). | Reuse as evidence and entity candidates. Preserve ambiguity, raw user wording, and original objective. These results do not authorize an action. |
| Grounding assembly | `chatbot/engine.py:1317` loads visible rows, `:1408` runs the span call without a DB session open, `:1487` falls back to n-grams. `:5207` chooses span grounding and `:5310` invokes the parser. | Extract/retain reusable grounding seams rather than replacing the chatbot. Prompt markers decide activation; source presence does not establish active production behavior. The resolver's introductory comment saying it is not imported on the turn path is stale relative to these engine imports/calls. |
| Current turn plan | `chatbot/turn/plan.py:80` has domains/fetch/ask/denied/trace. `turn/fetch.py:59` calls `ctx.tool_runner(domain, spec)`; `:1` documents ordered domain fetches. | A useful typed fetch boundary. It represents a deterministic current-turn answer, not a dynamically maintained multi-step business objective. |
| Assistant agent loop | `ai_assistant_service.py:2314` obtains tools, invokes a model, executes tool calls, and feeds results into the next iteration. `:2602`, `:2807`, `:2865`. | Reuse provider/tool conversion, trace and result handling in a task runner. Avoid simply routing contact traffic into the entire existing in-app assistant service, whose identity and conversation assumptions differ. |
| Optional planner | `ai_assistant_service.py:584` is opt-in; `:596` creates plan text; `:2586` injects it into the loop. | It is advisory prose, not stored executable state. A separate planner call is not required to obtain dynamic reasoning; the next-action loop can plan and adapt. Do not add planner/executor/reviewer agents without evidence. |
| Capability selection | `ai_assistant_service.py:1432` retrieves candidates; `:1465` filters configured enabled tools; `:2360` binds selected schemas once, plus `user_guides_read`. Defaults are top K 1, 3 calls, 6 iterations (`app/config.py:357`, `:362`, `:364`). | A task may discover a need for a new tool after reading evidence. Start with a compact permitted capability set for supported operations; allow refresh/discovery within the permitted catalogue if required by the journey. More iterations cannot use a capability never bound. |
| Output processing | `ai_assistant_service.py:2813` detects tool error envelopes and records success; `:2869` truncates feedback to 6,000 characters. `:2646` treats model prose with no calls as completion. | Keep useful error feedback but add structured results and explicit completion verification. Successful transport, valid prose, or a tool's absence of an error is not proof of the requested saved outcome. Avoid silent truncation of rows/requirements needed for decisions; return paginated summaries and retrievable evidence references. |

All abbreviated service paths in the table are under `sorento_crm_backend/app/services/`.

### Memory is useful context, not an execution receipt

`chatbot/session_state.py:23` persists focus, open question, ideation, access levels, flyer state and reply language. Focus includes last displayed list and task collections (`chatbot/turn/state.py:183`, `:198`). This helps with references such as "the second one" and follow-up corrections.

The existing `Task` in `chatbot/turn/task.py:78` is explicitly an open collection of slots carried on focus. Its single production kind is stock quantities (`:12`), with open/parked/answered states (`:33`). Its lifecycle is useful precedent for interruptions, but it has no committed business action IDs, attempt journal, idempotency keys or arbitrary objective completion condition. Do not advertise this class as an already-existing general agent runtime.

Chatbot memory has contact/system levels (`turn/memory.py:35`), contact-and-test-world-scoped history (`:381`), deterministic summaries without figures (`:390`), and count-based retention (`:72`, `:120`). This is appropriate for recalling context while reading fresh business facts. It must not be the authority for current amounts, workflow state, permissions, or whether a write happened.

The internal assistant loads only the latest six user/assistant messages into its tool loop (`ai_assistant_service.py:2508`). `AIAssistantMessage` persists text and metadata (`app/models/ai_assistant.py:89`); it is not a complete recoverable provider transcript. A compact task summary can retain evidence references, constraints, pending decisions and action receipts, while provider continuation data is preserved separately where needed. Do not store private chain-of-thought as task state.

### A pending confirmation is not durable multi-step execution

The current write gate stores one tool name, arguments and summary and exits the loop (`ai_assistant_service.py:2771`). `_load_pending_confirmation` only accepts the latest assistant message; an intervening ordinary answer supersedes an older pending call (`:1940`). Confirmation dispatches that one stored call and reports it (`:1985`, `:2071`), without resuming a stored objective.

Current repeated-click protection marks metadata resolved before dispatch (`:1961`, `:2003`). The observed code performs a normal query/update/commit, not an atomic compare-and-set claim. The test at `tests/test_ai_write_confirm.py:176` proves sequential duplicate prevention only. Two requests that both loaded pending metadata before either marks it, or a process death between marking and dispatching, need separate coverage. Do not treat this as transactionally guaranteed action idempotency.

On any dispatch exception, current code says "Nothing was changed" (`ai_assistant_service.py:2097`). For a network timeout after the backend committed, that conclusion is not justified. An agent runner needs distinct failed-before-execution and outcome-unknown cases; unknown writes need reconciliation using operation ID/readback before retry.

The existing map of selected real-user write permissions (`:1817`) is defense in depth around a shared MCP act-as principal, as its own comment states (`:2030`). It is not an implementation of all contact-user RBAC, company, ownership or workflow eligibility. The new action boundary must use the linked user for the actual business check and audit, not merely check one permission before running as an integration user.

Another guard to tighten when reusing the loop: model-visible tools are the selected subset, but dispatch checks membership against every MCP catalogue tool (`:2356`, `:2737`). The runner must enforce the actual current, permitted, enabled capability set at dispatch. Tool schema exposure alone is not a guard. Tool write classification currently relies on name suffixes and exceptions (`:115`, `:139`); a reviewed capability contract should declare side effects and authorization requirements instead. This is about tool metadata, not introducing keyword requirements in user instructions.

### Incoming-message durability is already solved for a different unit

`chatbot/inbox_queue.py:1` documents persisted `chatbot.turns` rows, one contact drain, a Redis mutex heartbeat and send-order handling. The implementation has claim/checkpoint (`:556`, `:588`), recovery (`:898`) and sweep (`:1017`). It distinguishes uncertain outbound sends (`:675`, `:707`) rather than blindly repeating them. Reuse that operational lesson.

Its work item is an inbound message answered by one chatbot turn. A replay with no attempted reply POST may rerun the turn. Once arbitrary business writes exist inside such a turn, rerunning it is unsafe without a separate recorded action outcome. The inbox cannot infer whether a form was submitted before a crash merely from whether a conversational reply was sent.

`app/tasks/chat_turns.py:81` supplies a bounded in-process pool and `:208` starts inbox recovery. Existing scheduled tasks also run registered handlers in fresh sessions (`scheduled_task_service.py:395`). These are server execution mechanisms to evaluate for reuse; neither inspected path supplies a general agent step/checkpoint contract. Prefer existing deployment/process infrastructure with a persisted run and action journal before introducing a new workflow platform.

The governing `PRINCIPLES.md:261` requires long-running jobs to advance on the server independently of an open browser. The console is a viewer and input surface, not the driver of every transition.

## Model and provider assessment

Independent agent model configuration can reuse provider/key resolution, prompt registry and tracing. The current per-contact model ladder applies broadly to parser/clarifier/code-reader calls (`contact_llm_choice.py:1`); simply using that ladder for the new agent would couple the expensive reasoning role to lightweight grounding. Its missing-key fallback (`:48`) also silently chooses the default model. The agent reasoning role should be explicitly separate and refuse/enter a clear unavailable state when no approved reasoning configuration can run, rather than silently execute business actions on the parser's model.

The prompt registry already exposes per-key provider/model (`ai_prompt_registry.py:1576`) and reasoning effort (`:1601`). Immutable prompt versions and movable labels are implemented at `:1519`. Reuse these concepts with an explicit reasoning role, recording the chosen provider/model, answered model, prompt versions, reasoning setting, budget and usage per task attempt. Existing `AIAssistantConfig` has dedicated encrypted keys for providers (`app/models/ai_assistant.py:33`).

| Adapter | Code actually supports | Gap before treating a reasoning model as interchangeable |
| --- | --- | --- |
| OpenAI | Tool schema/call round-trip and explicit reasoning effort (`llm_provider.py:442`, `:472`, `:495`); reports reasoning tokens. | The assistant loop does not pass effort (`ai_assistant_service.py:2602`), and has a fixed 2,048 token cap. Validate chosen model/API's tool, token and continuation contract. |
| Anthropic | Converts tools and tool-result blocks; extracts text/tool-use (`llm_provider.py:717`, `:892`, `:899`). | `reasoning_effort` is accepted but ignored, explicitly pinned by `tests/test_llm_provider.py:1526`. No thinking configuration is sent in `:884`; native thinking/other content blocks are dropped from the normalized response and reconstructed history. Stronger Claude choice is not proof that reasoning settings or continuation are wired. |
| Gemini | Function declarations, tool-result conversion, thinking budget/level mapping and reasoning usage (`llm_provider.py:1030`, `:1254`, `:1538`, `:1640`). | Normalization keeps only call name/args with synthesized IDs (`:1577`), then reconstructs function-call parts (`:1316`), losing native part metadata such as thought signatures. The current round-trip test (`tests/test_llm_provider.py:1009`) covers name/args/results only. The adapter rejects combined tools plus JSON output mode (`llm_provider.py:1525`), so design the loop's structured control contract accordingly. |

`ChatResult.raw` retains the provider response and its docstring says it can support native continuation (`llm_provider.py:25`). However, the assistant creates a fresh normalized assistant message without `raw` (`ai_assistant_service.py:2657`). A provider-aware continuation representation is therefore a concrete reuse extension. Preserve opaque required continuation blocks/signatures exactly and confidentially; do not display them as reasoning. Whether a specific candidate requires a given field must be checked against its current official API documentation and integration tests. This review does not recommend a vendor version.

`chatbot/llm_call.py:140` already provides bounded retry/deadline handling for model requests. Reuse or adapt its policy for task budgets and cancellation checks. Do not apply model-call retry policy to mutations. Existing provider mocks and cassettes are useful for offline contract tests, with later approved, budgeted model comparisons on the same CRM scenarios.

## Smallest credible extension, for parent decision

1. **Console entry and identity.** Keep existing dry-run console behavior (`chatbot/console_service.py:450`); add an explicit execution path. Resolve enabled contact -> linked active user server-side, and record both console operator and acting user. The parent identity investigation must settle operator delegation rights. Reject missing/invalid identities; do not fall back to integration identity. Existing business services remain authoritative.
2. **Reasoning context.** Pass original instructions and relevant conversation alongside grounded candidates, current task facts and permitted capabilities. Do not force arbitrary objectives through the chatbot's fixed intent enum. Semantic interpretation chooses an operation; schemas, authorization, record state and business rules decide whether it can run.
3. **One bounded next-action loop.** The model chooses a permitted read/action, asks for a genuinely missing decision, or proposes completion. Observe typed tool outcomes and adapt. A compact capability set can expand when evidence requires it, but dispatch must revalidate eligibility, actor, scope and parameters. No hard-coded "submit/approve" phrase gate. The user's instruction authorizes the task semantically; confirmation policy remains an owner decision.
4. **Persist only necessary execution state.** For tasks that survive a question/approval/restart, use a run record and action journal, or equivalent existing persisted structures if a detailed implementation trace proves they fit. Record objective, contact/user/operator, configuration versions, current status, pending decision, revision/cancel marker and evidence refs. Each attempted action needs immutable operation ID, intended parameters/preconditions, claim/attempt state, outcome, result IDs and verification. State transitions must be atomic and server-driven. Do not make conversation memory or trace text the transaction ledger.
5. **Execute and reconcile.** Prefer a service action boundary shared with the UI and preserving its guards. Local DB mutations can record receipts in the same transaction where feasible. External/async operations require stable operation IDs and readback/reconciliation. Record partial success honestly; resume unfinished steps without repeating successful actions. When an action's outcome is unknown, reconcile before asking the model to try again. Do not promise automatic rollback of already-completed business operations.
6. **Interrupt/resume.** Associate follow-up instructions with the task; allow corrections, side questions, missing information and cancellation. Check cancellation/config/authority before the next side effect. A running operation may complete before cancellation takes effect, and the UI should show that receipt. Waiting for a human is a normal state, not a crashed turn. Resume from state and receipts, not from reinterpreting old prose as if nothing ran.
7. **Verify completion.** Operation results should distinguish succeeded, rejected, pending async, failed and unknown; include saved record IDs/current state, validation failures and next permitted options. For submission, verify a saved submission and its actual workflow stage. For approval/rejection, verify transition, actor and persisted target state. If downstream notifications remain pending, state that accurately. Only mark the task complete when the agreed requested outcome is evidenced.

This proposes runtime structure, not new CRM user workflows. Deliver capability coverage in real existing operation slices; each slice needs read requirements, execute boundary and verify outcome. A generic unrestricted HTTP/SQL tool is not a substitute for those contracts.

## Verification work to include in UAC/PLAN

Reuse the existing engine abstraction: `sorento_crm_backend/scripts/chatbot_eval/engine.py:20` defines Outcome; `:33` defines `Engine.turn`; `:148` loads alternate engines. The current HTTP engine is explicitly dry-run (`:69`) and automatically retries transport errors/statuses (`:95`), so an action engine must supply operation idempotency and reconciliation before adopting those retries. Its current output grades answer/trace/state, not saved business mutations.

`documentation/agents/chatbot-verification.md:97` defines dev/hidden generalisation, varied wording, layer scoring and budgets. Preserve that approach and add task completion assertions from isolated PostgreSQL fixtures. The dry-run console alone cannot prove a form action occurred.

Essential scenarios:

- Natural paraphrases, typos, mixed languages, pronouns, "same as before" and no command words; compare requested end state, not a prescribed tool sequence.
- A real submission with derivable fields, genuinely missing required information, user correction, saved draft versus submitted distinction, and a valid final readback.
- Approval/rejection with valid eligibility; forbidden company/ownership/role/approver; state changed by another person between read and action; revoked permission or disabled contact before resume.
- User asks an unrelated question while a task waits, then resumes; cancellation between steps; correction invalidates stale proposed parameters; closing/reopening browser does not lose work.
- More than one tool needed after an unexpected result; tool absent from current bound/allowed set; unregistered or disabled tool returned by model; read-only/dry-run enforcement at dispatch.
- Duplicate concurrent execution requests, worker crash before action, crash after commit before receipt delivery, network timeout with committed action, and recovery with exactly one durable business effect.
- Partial batch success and rejected later item; accurate completed/remaining list; no blind rollback or replay.
- Quoted documents/tool output containing instructions; preserve user objective and actor boundaries rather than granting those instructions authority.
- Adapter transcript round-trips for multiple tool calls including repeated same-name calls; provider-native continuation fields; thinking configuration; truncation/refusal; timeout; unsupported setting; missing provider key. No silent lightweight-model fallback for actions.
- A model says "done" before any action, receives HTTP success with an error envelope, or stops on budget: task status must reflect evidence and remaining work.

Useful existing tests to extend include `tests/test_ai_role_split.py:122`, `tests/test_ai_write_confirm.py:138`, `:176`, `:193`, `tests/test_ai_assistant_turn_cache.py`, `tests/test_llm_provider.py:1009`, `:1406`, `:1526`, `tests/chatbot/test_inbox_queue_recovery.py`, `test_span_extract.py`, and `test_list_resolver.py`. Presence of those tests is not a claim that they ran in this audit.

## October 29 delta

The parent requested a check against `98773e5aa9`. Material findings from that diff:

- **Oct29** `llm_provider.py:1482` adds Gemini explicit context caching. `:1670` enables it only when `prompt_cache_key` is present. It caches system/tool payloads and falls back uncached on cache problems. This can improve cost/latency, but does not preserve reasoning continuation or task state. `ai_assistant_service.py` is unchanged and does not pass a cache key in the inspected loop.
- **Oct29** `chatbot/head/lookup_lists.py:924` adds a per-model shared vector file with file locking and atomic writes, reducing duplicate worker warm-ups. Earlier notes describing that code as absent/pending need updating; production prompt activation is still unverified.
- **Oct29** `lookup_lists.py:437` adds optional row IDs for brand/salesperson/category grounding and `:441` retains exact salesperson matches beyond the usual cap. Parser `ROW_ID_ASK` gates this behavior. Useful grounding improvement, not general action authorization.
- REPORT-UNIFY extends existing report handling and introduces `pending_delivery`/`unpaid` bases in the parser. Reuse the current report services if a task needs analysis rather than copying old report branches. This does not change the broad product scope.
- No diff to `ai_assistant_service.py`, prompt registry, inbox queue or the normalized Gemini transcript converters was found. The principal execution and reasoning configuration gaps above remain.

## Decisions still needed from the owner, after concrete journeys

The parent should align on the first exact existing form/action and requested end state, semantic delegation versus confirmation policy (especially batches), operator authority to act as another contact's user, treatment of workflow-triggered notifications, and what cancellation means for an operation already in progress. These do not require deciding a new orchestration framework. Model selection needs current official capability checks plus CRM outcome evaluations, not a tier-name assumption.
