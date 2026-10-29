# Agentic CRM acceptance criteria

Status: proposed for owner review, 29 October 2026. Codex plans; Claude implements. No implementation authorization is implied by this draft. Decisions already given by the owner are preserved; proposed policy is marked below. Evidence: EVIDENCE-agentic-actions-29oct.md, EVIDENCE-agentic-identity-29oct.md and EVIDENCE-agentic-runtime-29oct.md in this directory.

## Product outcome and guided journeys

Internal staff can delegate the work they already do in CRM through natural conversation in the chatbot console. Agentic eligibility is per Respond contact. The acting authority is the linked active User, including current company, ownership, module and workflow constraints. WhatsApp entry is a later channel. Broad CRM capability coverage is the destination; each action is admitted only after its existing business contract is mapped and tested.

Journey A (withdrawn from first-release scope pending evidence of actual use): A staff user describes a submission for an existing published Workflow Form. The agent finds the definition, reads its published schema, resolves supplied references and asks for missing required decisions. It creates the actual submission and shows its saved state and detail link. Creation validates required fields; it must not advertise an incomplete draft capability this form system does not have. Subsequent edits and transitions use the submission's pinned schema version.

Journey B: A staff user asks to approve or reject an existing purchase request. The agent resolves the current revision, checks state and eligibility, obtains a rejection reason if absent, performs the existing decision, then verifies its saved state. A triage action to send for approval is distinct from approval. A successful decision and successful notification delivery are reported separately.

Journey C: A task spans investigation and action. The user corrects a reference, asks a side question, or closes the console while work runs. The server preserves the objective and verified results. Resume uses current permissions and current record state; it does not repeat completed writes.

These are proving journeys for a reusable runtime, not phrase templates or a restriction of the product to two forms. Portal domain submissions, Workflow Forms and the generic Forms catalogue are separate systems and require separate adapters.

## Acceptance criteria

| ID | Observable behavior | Required proof |
|---|---|---|
| AC01 | Agentic mode can be enabled independently per contact, defaults off, and respects the AI replies gate. Existing chatbot behavior remains available. | Settings patch isolation and routing tests. |
| AC02 | Resolve workspace + external Respond ID to internal contact, then linked active User. Missing, disabled or ambiguous identity refuses execution. | Identity fixtures; no integration/operator fallback. |
| AC03 | Reads and writes enforce that User's current RBAC, module, company, ownership and domain rules. Console contact selection alone grants no authority. | Negative cross-user/company tests at dispatch and resume. |
| AC04 | Natural paraphrases, typos, multilingual instructions, pronouns and corrections work without required keywords. Original request remains available alongside grounding. | Held-out task variants graded by outcome. |
| AC05 | Discover actual schema and permitted actions; ask only for missing decisions. Never invent amounts, rejection reasons, attachment uploads or approval authority. | Missing-field, ambiguity and invalid-transition cases. |
| AC06 | Execute real submissions/decisions through shared guarded business operations. Preserve revision checks, locks, grace/cancel and notification semantics. | PostgreSQL state, actor and event assertions. |
| AC07 | Show saved record and current state; distinguish queued, committed, failed and uncertain outcomes. Model prose cannot establish completion. | Readback tests including false success and 202. |
| AC08 | Persist task progress through waiting, restart and closed tab. Corrections invalidate stale proposals; cancellation prevents subsequent actions. | Worker restart and multi-turn tests. |
| AC09 | Concurrent/replayed requests do not duplicate a business effect. Unknown outcomes are reconciled before retry. | Crash-before/after-commit and concurrent claim tests. |
| AC10 | Keep test console and real execution visibly distinct. No WhatsApp inbound history is required to start console work. | UI journey and dispatch-mode tests. |
| AC11 | Reasoning model settings are separate from span/parser models; preserve provider-native continuation and supported thinking configuration. No silent weak-model action fallback. | Provider round-trip contract tests. |
| AC12 | Task/tool/time/cost limits stop with accurate completed and remaining work. | Budget exhaustion and partial-batch tests. |
| AC13 | Audit operator, acting user, contact, task, action and result. Progress exposes concise evidence, not private reasoning. | Audit assertions and UI inspection. |
| AC14 | Tool output, documents and stored conversations cannot override the user's objective or grant permissions. | Injection and unauthorized-tool tests. |
| AC15 | Every added CRM capability has read requirements, guarded execution, verification and side-effect contract. Unsupported operations are identified honestly. | Capability matrix review per delivery slice. |

## Proposed policies requiring owner review

P1: A clear natural-language instruction authorizes the requested ordinary operation; no blanket confirmation after every tool call. Ask when scope or a business decision is missing. Retain existing domain confirmation/grace rules. Batch/destructive operations need an explicit reviewed policy before enablement.

P2: Initial real console execution is self-only: operator must be the contact-linked User. Cross-user execution requires explicit audited delegation, not merely console view access. Existing admin impersonation may inform a later adapter but is not automatically safe here.

P3: Real execution preserves existing workflow notifications. Test execution uses isolated records and notification sinks. Console-first describes entry channel, not suppression of business side effects.

P4: Cancellation takes effect before the next operation. Already committed actions remain visible and are reversed only through existing authorized undo, when supported.

These defaults are proposals, not owner rulings. Broader permission or approver defects discovered in existing routes must be resolved explicitly; the agent must neither amplify them nor invent a new policy silently.

## Owner correction and context design follow-up

The owner indicates Workflow Forms is probably not used. Its presence in code does not establish adoption. Remove it as the proposed first proving slice; retain only as a surveyed future capability. Ground the first slice in actual domain forms and their existing staff flows.

Read the owner-pasted Gemini blueprint. Adopt its durable execution, server-enforced authority, typed tool results and provider continuation principles where applicable. Do not import its greenfield async database rewrite, mandatory OAuth exchange infrastructure, five-table schema, multi-agent topology or backend-first delivery order without repo-specific need. Model/version/benchmark/statistical claims remain unverified and are not selection evidence.

Context contract: retain an access-controlled conversation log, but assemble bounded context per model call: trusted task instructions; current user message and recent exact conversation; a task summary with constraints and unresolved decisions; exact relevant earlier excerpts retrieved as needed; grounded entities with provenance; fresh authorized CRM facts; current permitted tool schemas; and the active tool-call/result sequence with required provider continuation metadata. Keep action receipts, identities and permissions authoritative in server state, not a lossy summary. Compact older dialogue by token budget, preserve corrections and unresolved choices, and retrieve original turns when precision matters. Never silently truncate required fields or pending decisions. Conversation history is evidence of user intent, not evidence of current business state. Separate test/live, contacts, workspaces and task scopes; recheck current access before retrieval.

## General analytics scope addition

Owner requests open-ended data analysis comparable to working with Claude Code, beyond fixed reporting routes. ANALYTICS-agentic-crm-29oct.md is the detailed design extension: authorized schema discovery, composable read queries, iterative evidence-based investigation, optional isolated computation and charts, and verifiable results. This is a core workstream alongside existing operational forms. Existing report definitions remain reusable sources of business meaning, not a ceiling on questions. Acceptance requires novel questions without a new per-question endpoint, correct joins/calculations, linked-user data isolation and honest incomplete/uncertain outcomes.
