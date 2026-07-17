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

/** `POST /reorder-runs/{id}/chat` → a grounded answer over the whole run. */
export interface RunChatResult {
  answer: string;
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
