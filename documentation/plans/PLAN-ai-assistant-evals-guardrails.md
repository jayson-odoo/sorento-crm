# PLAN - AI Assistant Guardrails + Evals (M3)

**Status:** GRILLED (2026-07-03, §9 resolved below). **Split into M3a (guardrails, runtime) + M3b (evals, offline)** - grillable/shippable independently.
**Depends on:** M1 prompt registry (prompt *version* = the unit an experiment runs) + M2 traces (promote real traces → eval examples; judge scores attach to spans).
**Owner:** jayson
**Date drafted:** 2026-07-03

---

## 1. Problem

M1 gives editability, M2 gives visibility - but you still tune **blind to whether output actually improved**, and there is **no gate** stopping a bad/hallucinated/low-confidence answer from reaching the user. Industrial systems (Shopify, Intercom, Grafana, Kodee) all have: a pre-send safety check, an offline eval loop, and an online quality monitor.

## 2. Goal

Activate the 3 remaining dormant role keys + build the eval harness:
- **`validator`** - confidence/safety gate BEFORE the answer ships. Low confidence → escalate/ask instead of answering (Intercom "escalate when uncertain"; Shopify N-stage gated: schema-check THEN semantic judge).
- **`clarifier`** - ask-vs-guess: when the query is underspecified, ask a clarifying question rather than hallucinate.
- **`judge`** - LLM-as-judge scoring for offline experiments + sampled online traffic.
- **Guardrails** - explicit confirmation on any write/destructive MCP tool (Kodee/Grafana both); read-only default.
- **Eval harness** - golden dataset + experiments + scores + A/B-with-regression-highlighting to gate prompt promotion.

## 3. Data model (draft - from research §5, LangSmith/Langfuse shape)

```
ai_eval_datasets      id, name, version(pinned baseline), description
ai_eval_examples      id, dataset_id, input(jsonb), expected_output(jsonb),
                      metadata, source_trace_id  <-- promote real M2 traces
ai_eval_runs          id, dataset_id, dataset_version, prompt_key, prompt_version,
                      created_at   (= one experiment: a prompt version over the set)
ai_eval_scores        id, run_id|trace_id|span_id, name(e.g. "faithfulness"),
                      value(numeric)|string_value(categorical),
                      data_type(NUMERIC|CATEGORICAL|BOOLEAN|TEXT),
                      source(EVAL|ANNOTATION|API), comment(judge reasoning)
ai_score_configs      name, data_type, min, max, categories  (standardize a score schema)
```

## 4. Evaluator layers (stack them)

1. **Heuristic/code** (deterministic): exact-match, regex, JSON-schema validity, length bounds. Cheap, not everything rides on an LLM.
2. **LLM-as-judge**: rubric + input + output-under-test (+ optional reference) → structured score + reasoning. Reference-free (relevance/faithfulness/policy) or reference-based (correctness).
3. **Human annotation** (source=ANNOTATION): single + pairwise.
4. **RAG-specific (RAGAS, ~0 - 1):** `faithfulness` (answer claims supported by retrieved context - hallucination detector, no ground truth), `answer_relevancy`, `context_precision`, `context_recall`. *(Confirm exact RAGAS v0.2 API names against live docs - rate-limited during research.)*

## 5. The tuning workflow (the payoff)

1. Build golden dataset (curated + promoted production traces, esp. thumbs-down). Pin version.
2. **Experiment A** = baseline prompt version over dataset → scores.
3. Edit prompt in M1 → **Experiment B** over the *same pinned dataset, same evaluators*.
4. **Compare A vs B:** per-example side-by-side (each version's output + scores) AND aggregate per-metric deltas, **regressions highlighted** (examples where B < A). Higher average is NOT enough - inspect individual regressions.
5. **Gate promotion** (M1 publish→production) on aggregate ≥ baseline AND no unacceptable per-example regressions. Eval-as-CI.
6. Promote = move the M1 `production` label to the winning version.
7. **Online loop:** run reference-free judges on *sampled* production traffic (async, cost-controlled); low-scoring / thumbs-down traces → new dataset examples. Golden set grows to reflect real failures.

## 6. Guardrails (draft)

- **Write/destructive tool confirmation** - any mutating MCP tool requires explicit user confirmation before execution (Kodee reinstall/restore precedent). Read-only is the default posture; the existing RBAC act-as scoping is the read-vs-write boundary.
- **Pre-send `validator` gate** - score the drafted answer for confidence/faithfulness; below threshold → clarify or escalate rather than send.
- **Escalation path** - for portal/contact-facing flows, "hand to human" when uncertain (Kodee `is_seeking_human_assistance` as the `router`'s first branch - may already partly live there).

## 7. LLM-judge pitfalls to design around

- Position bias → randomize/swap order, average both.
- Verbosity bias → state length-handling in the rubric.
- Self-preference bias → judge with a *different* model, hide model identity.
- **Always validate the judge against human labels before trusting it** (Shopify calibrated to Cohen's Kappa target; human baseline ~0.69).

## 8. Cheap quick-win (could pull earlier)

Kodee's lightweight loop, shippable without the full harness: LLM-judge score on sampled conversations {accuracy, completeness, tone, references} + topic-clustering of logs to find which question types fail + alert when judge pass-rate drops (Grafana). Consider as an M3-lite.

## 9. Resolved decisions (grill 2026-07-03)

Grounding facts: **no user-feedback signal exists** (only a deterministic `was_answered` bool). MCP is mostly read-only but has **2 genuine write tools** - `portal-tokens` (creates a portal link) + `it-support/tickets` (files a ticket); other POSTs (`lookup/resolve`, Outline `documents.info`) are read-only POST-body calls. Assistant audience = **internal staff only** (portal contacts use Respond.io/n8n, not this bubble).

### M3 split into two sub-milestones
| Sub | Scope | Deps |
|---|---|---|
| **M3a - Guardrails** (runtime, per-turn) | write-tool confirmation, validator (hedge/abstain), clarifier (ask-vs-guess) | light; write-confirm may pull earlier |
| **M3b - Evals** (offline, dev-time) | feedback UI, golden datasets, judge, A/B compare + advisory promotion gate | M1 + M2 live + curated dataset |

### M3a decisions
| # | Decision |
|---|---|
| Q2 write-confirm | Tag write tools `requires_confirmation:true` in catalog `ToolSpec` (deterministic; 2 tools today). Agent loop **halts** on a flagged call, persists pending `{tool,args,summary}` to conversation state, returns a structured `pending_confirmation`. FE bubble renders **Confirm/Cancel buttons** (no free-text yes-parsing); Confirm resumes the stored call, Cancel aborts. Read tools unchanged. Per-tool auto-approve override = future. |
| Q3 validator | **Hedge/abstain, NOT escalate** - staff are the humans, no handoff target. Below-threshold → answer explicitly flags uncertainty + points to verify/guide. **Faithfulness check** (reference-free): claims must trace to retrieved tool/guide output, else hedge. System-problems (not knowledge gaps) → offer the IT-support ticket path. Threshold configurable, start conservative, tune via M3b. |
| Q4 clarifier | **Lean assume-and-state**; ask only when ambiguity would change the answer AND a wrong guess is costly. Enumerable options (which of 3 PRs / which warehouse) → **buttons/chips**; free-form ambiguity → plain follow-up. **Max one clarifying round**, then answer with best assumption. |
| UX language | One structured-action language across all guardrails: uncertainty/questions = inline text; **any actionable next-step (file ticket, open guide, pick entity, confirm write) = a button**, never free-text parsing. |

### M3b decisions
| # | Decision |
|---|---|
| Q5 judge | **Independent cross-provider judge** (assistant on GPT-4o → judge on Claude Sonnet, or vice versa) - avoids self-preference bias. Own config `{judge_provider, judge_model, threshold}`, admin-editable, **warn if judge==assistant model**. Offline = strong model; online = cheaper + low sample. **Calibrate vs a small human-labeled slice** before it gates anything. Bias mitigations in the `judge` prompt (rubric handles verbosity; pairwise randomizes order for position bias). |
| Q6 feedback + seeding | **Build thumbs up/down + optional comment in the chat bubble** (M3b prerequisite - no signal exists today; also feeds M2's 90d retention of thumbs-down). Dataset seeding = **two curated sources, never auto-add**: (1) promote-from-trace (button in M2 trace view → set expected output), (2) thumbs-down → **review queue** an admin triages. Start ~20 - 50 hand-curated examples. |
| Q7 promotion gate | **Advisory, not hard-block** (initially). M1 publish dialog shows the A/B check (aggregate deltas + per-example regressions, highlighted); admin can override. No eval run → publish proceeds with a note. Tighten to per-key hard-block later once that key's dataset matures. |
| Q7 online sampling | **~10% sampled + always errors/thumbs-down**, async (off request path), cheap judge, sample-rate configurable. |
| Q8 eval UI | New **`evals/` sub-route** under `system-management/ai-assistant/` (sibling to `prompts/` + `usage/`): datasets → examples, run-experiment (prompt key+version over dataset), **experiment-compare view** (A/B per-example side-by-side + aggregate deltas + regressions highlighted - the key screen), thumbs-down review queue. |
| Q8 RAGAS | **In-house metric prompts** (`faithfulness`, `answer_relevancy`, + context precision/recall if needed) through the existing `get_provider` abstraction / `judge` infra. Avoids RAGAS's heavy langchain/datasets deps + config friction + unconfirmed v0.2 API names. |

## 10. Non-goals
- Multi-tenant per-tenant eval isolation (until real tenancy lands).
- Fine-tuning / model training - this is prompt + retrieval tuning only.

## 11. UAC - acceptance surface (the "satisfactory answers" bar)

Measured by the self-challenge harness (`sorento_crm_backend/scripts/ai_self_challenge.py`) over the acceptance question bank (§12). "Satisfactory" per category:

| # | Category | UAC |
|---|---|---|
| **U1** | how_to | Answer quotes concrete steps from the matched Outline guide with **bold UI labels + inline FE route links preserved**; no invented labels; if no guide matches → say so + (U8) offer to route, never hallucinate steps. |
| **U2** | data lookup | Binds the correct data tool (K=1), returns **real rows from this turn's tool call** (no invented ids/qtys/dates); names→UUIDs coerced so no INVALID_UUID. |
| **U3** | analytical/aggregate | Binds an **aggregation** tool (not a plain list), returns a **computed** number (count/sum/avg/rank) grounded in tool output - never the LLM eyeballing a truncated list. |
| **U4** | capability / how-to-use | Deterministic catalog answer (zero answer-LLM), grouped module→what-you-can-do→example questions. |
| **U5** | definition | Correct plain-language meaning; no fabricated system behaviour. |
| **U6** | vague / edge | Parser flags `needs_clarification` → **ONE** clarifying question; enumerable → FE chips; max one round then best-assumption answer. Never guesses when a wrong guess is costly. |
| **U7** | write (create/mutate) | `is_write_intent` → **confirmation gate**: agent halts on the flagged tool, FE Confirm/Cancel buttons, submit ONLY after explicit confirm. No accidental writes. |
| **U8** | any grounded answer | Validator faithfulness check: unsupported claims → hedge + point to verify/guide; genuine system problem → offer IT-support ticket. (Tuned via M3b before it gates.) |
| **U9** | missing capability | If no tool/guide can answer, the gap is **filled** (build the tool / write+push the guide), not papered over with a vague reply. |
| **U10** | every turn | Full M2 trace (parser → route → resolve → tool(s) → answer); tool errors surfaced, not silently swallowed. |

**Coverage rule (per user):** the bank must span how-to, data, analytical, how-to-use, definition, vague→clarify, and write→confirm - with **paraphrase variety per category** (not one canonical phrasing; anti-overfit). Re-run the harness after every gap-fill; a category regresses = blocker.

## 12. Acceptance question bank (living)

Seeded from `scripts/ai_self_challenge.py` `BANK` (33 Qs at baseline). Expand toward ~60+ with paraphrases and multi-turn flows. Categories + example spread:
- **how_to (≥8):** upload packing list; submit stock inquiry; send PR for approval; approve via email link; attach photo to complaint; OTP portal access; replace product attachment; flow a stock inquiry to purchasing.
- **data (≥8):** promotions now; Hanlim orders 2026; incoming shipments this month; DOs for X last month; stock on hand for <sku>; open complaints; order status <code>; who handled complaint <code>.
- **analytical (≥8):** total order value 2026 for X; avg delivery time; top N customers by order count; product with most complaints; complaints resolved last month; orders per month trend; revenue by customer; complaint rate by product.
- **how_to_use/capability (≥3):** what can you do; what can I ask; I'm new, how do I use this.
- **definition (≥4):** what does <status> mean; what is a GRN; DO vs SO; what is an SPO.
- **vague→clarify (≥5):** do the thing; show me the stuck one; the hanlim one; what about last month; close it.
- **write→confirm (≥5):** file a complaint about <x>; raise a stock inquiry; submit a PR; close complaint <code>; cancel order <code>.
- **multi-turn (≥3):** clarify→answer; form field-by-field→confirm→submit; data→drill-down follow-up.

## 13. Progress log
- **2026-07-05:** Harness + 33-Q bank built. Baseline run → gap map. **M3a Clarifier** BE live (parser `needs_clarification`→ one question + chips, one-round cap; 2 pytest, live-verified). Capability gaps closed: `crm_complaints_list` MCP tool (U2 "open complaints"), top-customers RAG fix. Order+complaint **analytics tools** in build (U3). Uncommitted.
