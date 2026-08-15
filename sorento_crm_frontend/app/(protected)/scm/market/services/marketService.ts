/**
 * ============================================================================
 * SCM M5 Part B - Market advisory feature service
 * ============================================================================
 * Layering: hooks (useMarket) → THIS service → lib/api-client → backend.
 *
 * Phase 1: every fn branches on `USE_M5_MARKET_MOCKS` (from marketMockStore) and
 * serves the deterministic mock - NO backend. The real `apiFetch` +
 * `extractApiError` branch is written but unhit until Phase 2 flips the flag.
 *
 * ── PHASE-2 BACKEND CONTRACT ────────────────────────────────────────────────
 * All endpoints mount under `require_module_enabled_with_api_key("scm")`.
 * The market layer is ADVISORY-ONLY (M5-D4): no endpoint here writes a
 * quantity/ROP/SS/rank - signals are cached web-search output, read-only.
 *
 * 1) Cached market signals  (read-only viz)
 *    GET /api/v1/scm/market-signals
 *    → 200 { data: MarketSignal[] }        // newest captured_at first
 *    Each signal: { id, topic_label, category_ref, currency, value, trend,
 *                   summary, source_url, captured_at }.
 *    `captured_at` is a naive-UTC ISO string (render via formatDateTimeInMalaysia).
 *    Auth: `scm.dashboard.view`.
 *
 * 2) Kick off a research run  ("Run research" button + scheduled_task)
 *    POST /api/v1/scm/market-research/run
 *    → 202 { run: MarketResearchRun }       // status "running" (async worker)
 *      OR 200 { run: MarketResearchRun }     // status "completed" if run inline
 *    Iterates active topics → Anthropic web search → schema-forced extraction →
 *    new `market_signal` rows + a `market_research_run` log. Cache signals; never
 *    search per recommendation (M5-D7). Auth: `scm.reorder.run`.
 *
 * 3) Poll a run's status  (UI polls until status ∈ {completed, failed})
 *    GET /api/v1/scm/market-research/runs/{run_id}
 *    → 200 { run: MarketResearchRun }
 *      { id, status, started_at, finished_at, topic_count, signal_count, error }.
 *    Auth: `scm.dashboard.view`.
 *
 * 4) Topic config CRUD  (`market_research_topic`)
 *    GET    /api/v1/scm/market-topics            → 200 { data: MarketResearchTopic[] }
 *    POST   /api/v1/scm/market-topics            body MarketResearchTopicWrite
 *                                                 → 201 { topic: MarketResearchTopic }
 *    PUT    /api/v1/scm/market-topics/{id}       body MarketResearchTopicWrite
 *                                                 → 200 { topic: MarketResearchTopic }
 *    DELETE /api/v1/scm/market-topics/{id}       → 204 (hard delete)
 *    `search_prompt` is the free-form web-search text (M5-D6); `category_ref` +
 *    `currency` are optional structured match keys. Auth: `scm.policy.manage`.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  MarketResearchRun,
  MarketResearchTopic,
  MarketResearchTopicWrite,
  MarketSignal,
} from '../types/market.types';
import {
  USE_M5_MARKET_MOCKS,
  mockCreateTopic,
  mockDeleteTopic,
  mockListSignals,
  mockListTopics,
  mockRunResearch,
  mockUpdateTopic,
} from '../lib/marketMockStore';

// ── Signals ──────────────────────────────────────────────────────────────────

/** Cached market signals for the read-only viz panel (newest first). */
export async function listMarketSignals(): Promise<MarketSignal[]> {
  if (USE_M5_MARKET_MOCKS) return mockListSignals();
  const res = await apiFetch('/api/v1/scm/market-signals');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load market signals'));
  const body = (await res.json()) as { data: MarketSignal[] };
  return body.data;
}

// ── Research run ─────────────────────────────────────────────────────────────

/** Small deterministic delay so the mock's running→complete feedback is visible
 *  (not random - a fixed duration). */
const MOCK_RUN_DELAY_MS = 900;
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Kick off a research run. Returns the run record the hook then reads/polls. */
export async function runMarketResearch(): Promise<MarketResearchRun> {
  if (USE_M5_MARKET_MOCKS) {
    await delay(MOCK_RUN_DELAY_MS); // let the running state paint before completing
    return mockRunResearch();
  }
  const res = await apiFetch('/api/v1/scm/market-research/run', { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start market research'));
  const body = (await res.json()) as { run: MarketResearchRun };
  return body.run;
}

/** Poll a run's status (Phase 2 - unhit under mocks, which return terminal). */
export async function getMarketResearchRun(runId: string): Promise<MarketResearchRun> {
  if (USE_M5_MARKET_MOCKS) {
    // Mock runs complete synchronously; there is nothing to poll.
    throw new Error('Mock research runs return a terminal run - no polling.');
  }
  const res = await apiFetch(
    `/api/v1/scm/market-research/runs/${encodeURIComponent(runId)}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load research run'));
  const body = (await res.json()) as { run: MarketResearchRun };
  return body.run;
}

// ── Topic CRUD ───────────────────────────────────────────────────────────────

export async function listMarketTopics(): Promise<MarketResearchTopic[]> {
  if (USE_M5_MARKET_MOCKS) return mockListTopics();
  const res = await apiFetch('/api/v1/scm/market-topics');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load research topics'));
  const body = (await res.json()) as { data: MarketResearchTopic[] };
  return body.data;
}

export async function createMarketTopic(
  body: MarketResearchTopicWrite,
): Promise<MarketResearchTopic> {
  if (USE_M5_MARKET_MOCKS) return mockCreateTopic(body);
  const res = await apiFetch('/api/v1/scm/market-topics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create research topic'));
  const out = (await res.json()) as { topic: MarketResearchTopic };
  return out.topic;
}

export async function updateMarketTopic(
  id: string,
  body: MarketResearchTopicWrite,
): Promise<MarketResearchTopic> {
  if (USE_M5_MARKET_MOCKS) {
    const updated = mockUpdateTopic(id, body);
    if (!updated) throw new Error('Research topic not found');
    return updated;
  }
  const res = await apiFetch(`/api/v1/scm/market-topics/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update research topic'));
  const out = (await res.json()) as { topic: MarketResearchTopic };
  return out.topic;
}

export async function deleteMarketTopic(id: string): Promise<void> {
  if (USE_M5_MARKET_MOCKS) {
    if (!mockDeleteTopic(id)) throw new Error('Research topic not found');
    return;
  }
  const res = await apiFetch(`/api/v1/scm/market-topics/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete research topic'));
}
