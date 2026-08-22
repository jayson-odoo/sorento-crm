/**
 * SCM M5 Part B - Market advisory types (read-only signals viz + topic CRUD).
 *
 * These mirror the Phase-2 backend contract documented at the top of
 * `services/marketService.ts`. The market layer is ADVISORY-ONLY: a scheduled /
 * manual backend web-search produces cached `market_signal` rows shown read-only;
 * `market_research_topic` rows are user-configured. No number the LLM emits ever
 * mutates a quantity/ROP/SS (M5-D4) - this UI only reads signals and manages
 * topics. No UUIDs surface: `category_ref` resolves to a readable label, currency
 * codes and topic labels are already human-readable.
 */

/** Direction a signal's value is trending. For COST/price signals `up` is the
 *  adverse direction (cost rising) - the viz colours it accordingly. null when
 *  the extraction could not determine a direction. */
export type MarketTrend = 'up' | 'down' | 'flat' | null;

/** How often the research job re-runs a topic. `manual` = only on the "Run
 *  research" button, never scheduled. */
export type MarketCadence = 'daily' | 'weekly' | 'monthly' | 'manual';

/** Lifecycle of a research run. The backend job transitions running → completed |
 *  failed (mirrors the reorder-run pattern). */
export type MarketRunStatus = 'running' | 'completed' | 'failed';

/**
 * One cached market signal - the read-only viz unit. Produced by the research
 * job from a topic's web search, frozen at `captured_at`. Numbers are display-
 * only; nothing here feeds the deterministic engine.
 */
export interface MarketSignal {
  /** Stable row id (never rendered - row keys only). */
  id: string;
  /** The topic this signal was captured for - human label, never a UUID. */
  topic_label: string;
  /** Optional category this signal matches recs against (readable code/label). */
  category_ref: string | null;
  /** ISO-4217 currency code (e.g. "MYR", "USD"); null when not price-scoped. */
  currency: string | null;
  /** Extracted headline figure (index, %, rate); null when purely qualitative. */
  value: number | null;
  trend: MarketTrend;
  /** One-line plain-language read of the signal. */
  summary: string;
  /** Source the figure was extracted from - opened in a new tab for traceability. */
  source_url: string | null;
  /** Naive-UTC ISO string - format with `formatDateTimeInMalaysia` (raw string). */
  captured_at: string;
}

/**
 * A user-configured research topic. `search_prompt` is the free-form text that
 * actually drives the web search (M5-D6); `category_ref` + `currency` are the
 * optional structured keys used to match resulting signals to recommendations.
 */
export interface MarketResearchTopic {
  /** Stable row id (never rendered - used for edit/delete + row keys). */
  id: string;
  label: string;
  category_ref: string | null;
  currency: string | null;
  /** Free-form web-search prompt / keywords. */
  search_prompt: string;
  cadence: MarketCadence;
  is_active: boolean;
}

/** Create/update payload for a topic (no id; server assigns). */
export interface MarketResearchTopicWrite {
  label: string;
  category_ref: string | null;
  currency: string | null;
  search_prompt: string;
  cadence: MarketCadence;
  is_active: boolean;
}

/**
 * One research run's observability record. `signal_count` is how many fresh
 * signals this run captured (drives the completion toast); `topic_count` is how
 * many active topics it searched.
 */
export interface MarketResearchRun {
  /** Stable run id (never rendered). */
  id: string;
  status: MarketRunStatus;
  /** Naive-UTC ISO strings - format with `formatDateTimeInMalaysia`. */
  started_at: string;
  finished_at: string | null;
  topic_count: number;
  signal_count: number;
  /** Human error message when status = failed; null otherwise. */
  error: string | null;
}
