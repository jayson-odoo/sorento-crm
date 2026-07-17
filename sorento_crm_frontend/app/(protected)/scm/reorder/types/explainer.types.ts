/**
 * SCM M5 Part A — semantic explanation / Q&A / market-advisory types.
 *
 * These are the FE contract for the Phase-2 endpoints documented at the top of
 * `services/explainerService.ts`. The M5 layer is PURELY a language surface on
 * top of the already-frozen deterministic recommendation (M3/M4): it never
 * recomputes or invents a figure — every number it speaks was frozen at run
 * time. When a question needs a number the recommendation doesn't carry, the
 * answer is the exact refusal string (never a fabricated value).
 */

/** `GET /recommendations/{id}/explanation` → one plain sentence from frozen numbers. */
export interface ExplanationResult {
  explanation: string;
}

/** `POST /recommendations/{id}/ask` → a bounded answer (or the refusal string). */
export interface AskResult {
  answer: string;
}

/** `GET /recommendations/{id}/advisory` → a market signal, or null when none matches. */
export interface AdvisoryResult {
  advisory: string | null;
}

/** Run-level AI overview — a short brief over the whole planning run. */
export interface RunOverviewResult {
  overview: string;
}

/** One entry in the in-dialog Ask transcript (local UI state only, not persisted). */
export interface AskTurn {
  question: string;
  answer: string;
  /** True when `answer` is the bounded-refusal string — styled distinctly. */
  refused: boolean;
}

/** One prior exchange forwarded to the run-chat so follow-ups resolve (M6-A). */
export interface RunChatTurn {
  question: string;
  answer: string;
}

/** One resolved per-line decision the assistant proposes from a plan instruction
 *  (M8-F16). `rec_id` is a REAL recommendation the FE Applies through the existing
 *  /accept · /reject · /adjust endpoints. `new_qty` is set only for an `adjust`. */
export interface ActionProposalLine {
  rec_id: string;
  sku: string | null;
  product_name: string | null;
  action: 'accept' | 'reject' | 'adjust';
  current_qty: number | null;
  new_qty: number | null;
  reason: string;
}

/** `action_proposal` on a chat response — a structured accept/reject/adjust card the
 *  human Applies in one confirm-gated click (M8-F16). Unresolvable references are left
 *  out of `lines` and named in `summary`. */
export interface ActionProposal {
  summary: string;
  lines: ActionProposalLine[];
}

/** `POST /reorder-runs/{id}/chat` → a grounded answer over the whole run. When the
 *  question reads as a market-trend ask, the backend auto-runs a live market scan and
 *  attaches `proposal` here IF the signal maps onto plan lines (M8-F6). When it reads as
 *  a plan INSTRUCTION, the backend resolves it into `action_proposal` (M8-F16). Both are
 *  null/absent for a plain grounded question. */
/** One product's THIS-run vs PRIOR-run figures (M8-F deterministic compare). Every
 *  number is a frozen engine value diffed in Python — the LLM never computes them. */
export interface PlanComparisonRow {
  sku: string | null;
  product_name: string | null;
  current_qty: number | null;
  current_funding: string | null;
  current_days_cover: number | null;
  current_net: number | null;
  previous_run_date: string | null;
  previous_qty: number | null;
  previous_decision: string | null;
  previous_days_cover: number | null;
  previous_net: number | null;
  qty_delta: number | null;
  direction: 'new' | 'up' | 'down' | 'same';
  reason: string;
}

/** `comparison` on a chat response — a deterministic product-by-product diff of this
 *  plan vs each product's most recent prior plan (M8-F). Rendered as a table; the answer
 *  prose never restates the numbers. */
export interface PlanComparison {
  rows: PlanComparisonRow[];
  compared_count: number;
}

export interface RunChatResult {
  answer: string;
  proposal?: MarketProposalResult | null;
  action_proposal?: ActionProposal | null;
  comparison?: PlanComparison | null;
}

/** A cached market signal returned by an ad-hoc search (M6-B). */
export interface MarketSignal {
  id: string;
  topic_label: string;
  category_ref: string | null;
  currency: string | null;
  value: number | null;
  trend: string | null;
  summary: string;
  source_url: string | null;
  captured_at: string;
}

/** `POST /market-search` → the signals a planning-time search found + its run row. */
export interface AdhocSearchResult {
  signals: MarketSignal[];
  run: {
    id: string;
    status: string; // completed | failed
    signal_count: number;
    error: string | null;
  };
}

/** One confirm-gated qty-uplift the market scan proposes for a run buy (M8-E5).
 *  `rec_id` is the recommendation the user confirms via /recommendations/{id}/adjust. */
export interface MarketProposalLine {
  rec_id: string;
  sku: string | null;
  product_name: string | null;
  old_qty: number;
  new_qty: number;
  unit_cost: number | null;
  cash_impact_delta: number | null;
  reason: string;
}

/** One citation backing a market signal (M8-F) — a url + optional page title. */
export interface MarketSource {
  url: string;
  title: string | null;
}

/** `POST /reorder-runs/{id}/market-proposal` → a proposal-only card. Nothing is
 *  written to any recommendation until the user confirms each line. */
export interface MarketProposalResult {
  signal_summary: string | null;
  source_url: string | null;
  /** Citation sources proving the signal is factual (several when available; falls
   *  back to the single legacy source_url). */
  sources: MarketSource[];
  lines: MarketProposalLine[];
}
