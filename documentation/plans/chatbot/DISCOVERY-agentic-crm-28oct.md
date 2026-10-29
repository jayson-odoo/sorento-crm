# Agentic CRM discovery, 28 October 2026

Status: brainstorming with the owner. This is a research notebook, not an approved implementation plan or UAC. Codex plans; Claude implements after alignment.

## Owner decisions

- Start with internal CRM staff.
- Agentic mode must be toggleable per Respond contact (owner instruction, 28 October). The eligibility/routing decision therefore belongs to the contact, not only to the CRM assistant bubble. Initial rollout can enable selected internal staff contacts.
- Initial discussion explored sales performance; the owner subsequently broadened the target to the existing operations across the CRM, explicitly including form submission, approval, and rejection. Sales is an example, not the product boundary.
- Start in the chatbot console. WhatsApp is not required for the first delivery. Per-Respond-contact enablement still applies.
- Acting identity is the user linked to the Respond contact, governed by that user's existing role-based access (owner ruling). Contact selection does not grant the console operator's permissions to the agent. Preserve existing company, ownership, workflow-state, and approver-eligibility checks alongside RBAC.
- Understand instructions semantically in natural conversation, like the user's experience of working with Codex and Claude Code. No required command words, keyword triggers, or prescribed phrases for submission, approval, rejection, or other tasks. Prior example phrases were illustrative, not command syntax. Resolve intent and authorization from the request and conversation; ask only about genuine ambiguity or missing decisions.
- Agentic work needs a separately selectable, stronger reasoning model. The owner considers the current lightweight model inadequate for this work and named Gemini Flash and Claude Opus as candidates. Exact provider, model version, reasoning settings, and budget are not selected; verify current offerings and evaluate on CRM tasks before recommending a default. Do not infer an exact current model identifier from the owner's spoken shorthand.
- Use real operations users already perform in the system. The owner rejected an invented "follow-up list" workflow. Do not introduce a new work queue or equate an analysis recommendation with a real sales opportunity.
- The acting identity is settled. Execution-confirmation behavior, first exact journey, completion criteria, and implementation slices remain undecided.

## Source baseline and limits

The working checkout is `main` at `2280975f97` (22 September). Discovery also reads a separate source snapshot of local `origin/main` at `3a097ebbea` (28 October), extracted under `/private/tmp/sorento-agentic-discovery-20261028`. The checkout was not switched or updated. References below are relative to that October source snapshot unless stated otherwise.

PR #1959 was inspected read-only: span-pass production rollout and shared lookup vector warming are still described as work in progress. Prompt labels and runtime settings determine the active production behavior; this session did not inspect production configuration or execute live turns.

This is an architectural survey with deeper tracing of chatbot, assistant, MCP, sales, and selected SCM services. It is not a completed file-by-file audit of the monorepo. No application changes, tests, deployments, business writes, or customer communications were performed.

## Existing user journeys to build from

### Customer asks

Sales > Customer asks already lists a salesperson's customer enquiries. Staff open an enquiry, inspect the conversation, save a note, mark it Done, or Reopen it. Managers and team leaders have scoped views. The UI and routes already exist; an agent must work on those same records.

Evidence: `app/api/v1/sales/customer_asks.py`; `app/services/stock_ask_service.py`; frontend `components/stock-asks/AskConversationPanel.tsx`; `documentation/plans/sales/PLAN-sales-asks-todo-29sep.md` and its later UX rulings.

Agent opportunity, not yet approved: investigate an existing enquiry using its conversation and current CRM facts, then perform only the record changes the user actually requested. Reading an enquiry is not evidence that it has been resolved.

### Sales opportunities

Staff already create and edit opportunities, product lines, amounts, expected close dates, and stages. The service checks allowed stage transitions. Marking Lost requires a valid reason. A Won link to a sales order checks company, customer, and cancellation state.

Evidence: `app/api/v1/sales/opportunities.py`; `app/services/sales/opportunity_service.py::_apply_status_change`; frontend `sales/opportunities` pages.

Agent opportunity, not yet approved: locate the opportunity and the relevant order from a user's instruction, resolve ambiguity, apply the existing valid transition, and verify the saved relationship. Do not infer a deal is won from an optimistic conversation.

### Targets and sales analysis

Managers already inspect team/agent/dealer targets, drill into achievement and pipeline, set targets, and edit periods. Sales reporting has multiple bases. `app/services/sales/invoiced_sales.py` owns the invoiced calculation: invoices + cash sales + debit notes - credit notes, MYR net of tax, document date, cancelled documents excluded. Target achievement has its own configured basis; it must not be silently compared to a different sales basis.

Evidence: `app/services/sales/target_service.py`, `achievement_service.py`, `invoiced_sales.py`; `app/services/reports/`; frontend `sales/targets`, `sales/yearly-comparison`, `sales/top-selling-items`, `sales/sales-by-debtor-type`.

Agent opportunity, not yet approved: perform the manager's existing drill-down across periods, agents, customers, and products using the same report definitions. Separate measured contributors from causal hypotheses. Any subsequent write must address an existing authorized operation.

## Architecture findings

1. **The WhatsApp grounding pipeline exists.** `chatbot/direct_ingress.py`, `head/span_extract.py`, `head/lookup_lists.py`, `head/parser.py`, and `engine.py` implement ingress, mention extraction, matching, and parser context. Prompt-label gating matters. Keep the raw request and grounded candidates available to a future agent; a fixed intent label must not discard the rest of a multi-step objective.
2. **Message durability already exists.** `chatbot/inbox_queue.py` persists queued turns, serializes contact drains, recovers abandoned processing, and distinguishes unconfirmed sends. This is valuable existing infrastructure, but it represents message processing rather than a general business objective spanning multiple turns and actions.
3. **The CRM assistant already has an agent loop.** `ai_assistant_service.py::_run_agent_loop` calls tools iteratively; `_run_planner` is optional. Defaults in `config.py` are six iterations, three tool calls, and one RAG-selected tool. The guide reader is additionally bound. Increasing these limits alone does not supply durable task ownership or reliable execution.
4. **Tool availability is selected before the loop.** `_rag_select_tools` and `_run_agent_loop` bind the initial tool set. A business investigation needs a way to obtain additional permitted capabilities as new evidence makes them relevant. Evaluate a small task-appropriate set before designing a general discovery framework.
5. **Some writes and confirmation already exist.** `_serve_pending_confirmation` and `_resolve_pending_confirmation` persist a pending call, execute it on confirmation, and report its result. The latter does not resume a stored multi-step execution plan. Existing tests include `test_ai_write_confirm.py` and `test_ai_role_split.py`.
6. **Identity is a design constraint.** MCP authenticates with an API key which the current backend resolves through `integration_api_keys` / `integrations` to an integration's real act-as user (`integration_auth.py`, `dependencies.py`). The assistant performs additional real-user checks for named writes. Staff authentication uses opaque `user_sessions`, not the older JWT architecture described in the September checkout. CRM sales routes also enforce own-agent and company rules. The agent must preserve those rules while executing as the contact's linked user, not accidentally as the integration's user. A chat approval is not a permission grant.
7. **Existing external tools do not automatically fit internal users.** `crm_sales_opportunity_log` and its customer-options tool require Respond contact identity and workspace. The in-app assistant strips those fields from normal tool schemas. Trace and test the intended identity path before claiming this is a reusable staff write tool.
8. **Domain services remain authoritative.** Reports, sales calculations, status transitions, stock/coverage mathematics, and record updates already have owners. The model selects and sequences operations; it must not reimplement their business rules.
9. **Evaluation infrastructure exists.** The chatbot eval contract supports alternate engines. Extend evaluation to verified task outcomes, partial failure, changed permissions, retries, ambiguous entities, and interruption. Existing Q&A scores do not establish agent task success.

## Working design hypothesis, not a decision

Preserve the fast grounded Q&A path. Add bounded task execution for Respond contacts with agentic mode enabled when the request requires investigation or actions. Evaluate the existing internal assistant loop for reuse, without assuming the CRM bubble is the first delivery surface. The runtime owns the objective, relevant evidence, pending decisions, action results, and completion checks across turns. The model chooses the next useful step from authorized capabilities and adapts to tool feedback. The existing services decide what a legal operation is.

### Per-contact toggle

The October source already has `RespondContact.chatbot_allowed` in `app/models/access.py`, an `AI replies allowed` control in Contact Details > Chatbot, and a partial settings update at `PUT /api/v1/user-management/contacts/{id}/chatbot`. Its independent save avoids stale settings screens overwriting another switch. Reuse this location and update pattern for agentic eligibility.

Proposed behavior, pending journey/UAC alignment: the existing AI-replies gate remains authoritative; with replies allowed and agentic mode off, preserve current chatbot behavior; with both enabled, allow task execution as needed. Default the new toggle off for existing contacts. Enabling it grants no additional company, data, or action permissions. Recheck eligibility before subsequent task actions so disabling it can stop further work; define treatment of pending approvals and already-running operations during the journey discussion.

### Model roles

Keep the agent's reasoning model selection independent from the models used for span extraction and intent parsing. The grounding stages can retain their existing model choices. Evaluate the selected agent model on semantic understanding, multi-step tool use, missing-information handling, corrections, authorization boundaries, and verified task completion, together with latency and cost per completed task. Model tier alone is not evidence of task reliability.

Reuse the existing provider/configuration infrastructure where it supports the required tool and reasoning behavior. Proposed initial configuration: a system default for agentic reasoning; decide whether a contact override is needed when reviewing existing contact model settings. Avoid adding a multi-model escalation policy before evaluation demonstrates a need. Do not silently fall back to the lightweight parser model for business actions if the configured reasoning model is unavailable.

Expose progress and concise evidence-backed explanations, not private chain-of-thought. Store a task record only once the agreed journey requires persistence; avoid a new orchestration platform or multi-agent topology without evidence it is needed.

### Console-first operations across the CRM

Owner clarification: people should be able to perform the usual tasks they already do in the system agentically, including form submission, approval, and rejection. Plan for broad capability coverage through existing business operations, delivered in verifiable slices. Do not replace this scope with a new sales follow-up product or a single hard-coded workflow.

Verified foundations in the October snapshot:

- `catalog.py` already defines `crm_purchase_request_approve` and `crm_purchase_request_reject`, wrapping the existing approval-decision route. This establishes selected coverage, not universal action coverage or proven contact identity propagation.
- `WorkflowFormsService` exposes published definitions, create/update submission, `allowed_transitions_for_user`, and `apply_transition`. The latter validates the transition, records the acting user, and triggers notifications. Form-specific submission and approval requirements must still be inventoried.
- `FormActionService`, `form_action_dispatch.py`, and `form_actions.py` implement deferral, cancellation, execution, and selected undo paths. They preserve company scope and call existing services. Reuse these semantics where the corresponding UI action uses them; a tool must not bypass route-level authorization by calling a handler directly.
- `POST /system/chatbot/console/turn` and `console_service._build_envelope` use `is_test=True`. The existing text console is a dry-run surface. Media has separate metering/extraction effects, so do not describe the entire console as having zero side effects.

Proposed journey to refine: select an enabled contact in the console; give an ordinary task; the agent finds the form/record, reads its current state and applicable requirements, fills derivable fields, asks only for missing decisions, executes an authorized operation, and verifies the saved outcome. A submission and a business approval remain distinct operations, with their existing actors and workflow stages.

Proposed console design: keep the existing dry-run behavior and add an explicit execution mode. Exercise actual writes in a development/test environment before production use. Approval routes can trigger notifications and automations, including WhatsApp, even when the conversational entry point is the console; the treatment of these side effects must be decided explicitly, not silently assumed off.

Identity decision resolved by the owner: the Respond contact is linked to a user, and operations use that user's RBAC. The October source has `User.respond_contact_id` and a unique partial index on non-null values (`app/models/user.py`), plus existing own-record scope resolution through that link (`app/services/own_scope.py`). Resolve the identity on the server, expose only eligible capabilities, and enforce authorization again on execution through the same business boundary as the UI. Workflow transitions and record scope remain mandatory even when a permission slug is granted.

Implementation details still to settle: authorization for a console operator to execute as another selected contact, recording both operator and acting user, and the error behavior for an absent/disabled linked user. Recommended: refuse agentic execution for an invalid identity rather than falling back to the integration's act-as user. Preserve the existing chatbot behavior separately. A task that waits must recheck current authority when it resumes.

External background reading: Anthropic, [Building effective agents](https://www.anthropic.com/research/building-effective-agents), on the distinction between predefined workflows and model-directed tool use with environment feedback. This informs the hypothesis, not a framework or vendor choice.

## Delivery workflow checked

After the owner's development-process check, read the October `CLAUDE.md` completely, the current `.claude/skills/feature/SKILL.md`, `documentation/agents/chatbot-verification.md`, and the changes to governing `PRINCIPLES.md`. Earlier discovery had read local PRINCIPLES and AGENTS but only searched parts of CLAUDE.md. The current working artifact remains discovery notes, not an execution-ready plan.

Codex's planning deliverable: guided console journeys, resolved owner decisions, UAC first, then PLAN with concrete source paths, API/tool contracts, dependencies, per-AC test assertions, and execution slices. Files under `documentation/plans/chatbot/` are the contract. Review the plan in Lavish before implementation. Prefer existing services and the simplest design that satisfies the real journeys.

Claude's implementation sequence: Phase 1 console frontend against mocks; Phase 2 independent tester writes meaningful failing tests before the same lane coder makes them green and wires the real backend; Phase 3 code review, security review for this identity/action surface, and browser verification. One lane is one branch and one PR. Use the existing dev stack where appropriate, one frontend HMR server machine-wide, no unsolicited production builds. Postgres-only backend tests; real UI evidence and console conversation checks; generalisation evaluation on varied wording and multi-turn tasks. Real action tests need isolated data and assertions on saved state, because the existing dry-run console runner alone cannot prove mutations.

Current PRINCIPLES also requires long-running jobs to advance on the server independently of the browser. Any persistent agent task must therefore continue or enter a defined waiting state when the console tab closes; browser polling cannot be the only driver of execution. Merging and deploying are separate in current CLAUDE.md.

## Remaining design work

Semantic interaction requirement: keep the original request and relevant conversation available to the reasoning loop. Span extraction, entity matching, and parser output provide grounding; a fixed intent enum must not be the only representation of the user's objective. The model interprets the requested outcome, chooses permitted tools, observes results, and adapts its next step. Code enforces identity, RBAC, record scope, schema validation, allowed transitions, and execution consistency. Semantic matching does not make quoted text, attachments, or tool output an instruction from the user. Evaluate paraphrases, implicit references, corrections, multi-step requests, and genuine ambiguity rather than testing only prescribed command phrases. The owner's ruling rejects keyword-based authorization detection; it does not yet settle every confirmation or batch-action policy.

Choose an exact existing staff journey and define its requested end state. Then work through ambiguity, authority, interruption, and failure using that journey. Write the UAC first and implementation plan second, with concrete service/tool gaps and Claude execution slices. Keep the broader agent ambition separate from the first proving task.
