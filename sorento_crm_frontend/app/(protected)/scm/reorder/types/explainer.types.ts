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
