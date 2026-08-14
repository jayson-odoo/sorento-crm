/**
 * ============================================================================
 * SCM M5 Part B - MARKET ADVISORY DETERMINISTIC MOCK STORE  (Phase 1 only)
 * ============================================================================
 * Backs the market-signals viz + topic CRUD + "Run research" button with NO
 * backend, so the whole UX (signals panel, stat tiles, run feedback, topic
 * modal-CRUD) can be prototyped and verified in isolation.
 *
 * Phase 2 deletes this file and flips `USE_M5_MARKET_MOCKS` to false in
 * `market/services/marketService.ts`; the same operations then hit the real
 * endpoints documented at the top of that service.
 *
 * State persists in `sessionStorage` (client only) so a topic added / a run
 * fired on the page survives a full reload; a fresh browser session starts from
 * the seed. Deterministic by construction: NO `Math.random`, NO `Date.now` -
 * ids come from monotonic counters and every timestamp is stamped from a fixed
 * base (`RUN_BASE` / seed literals), never the wall clock.
 * ============================================================================
 */
import type {
  MarketResearchRun,
  MarketResearchTopic,
  MarketResearchTopicWrite,
  MarketSignal,
} from '../types/market.types';

/** Phase-1 flag - flipped to false in Phase 2 (real endpoints now serve these). */
export const USE_M5_MARKET_MOCKS = false;

// v1 storage - bumping the key abandons any stale persisted shape.
const STORAGE_KEY = 'scm_market_mock_v1';

/** Fixed base time for signals a "Run research" produces - advances by counter,
 *  never by the clock, so repeated runs stay deterministic. */
const RUN_BASE_DATE = '2026-07-17';

interface StoreState {
  topics: MarketResearchTopic[];
  signals: MarketSignal[];
  topicSeq: number;
  signalSeq: number;
  runSeq: number;
}

// ── Seed topics (~4) ─────────────────────────────────────────────────────────
function seedTopics(): MarketResearchTopic[] {
  return [
    {
      id: 'topic-seed-1',
      label: 'Ceramic tile FX exposure',
      category_ref: 'ceramic-tiles',
      currency: 'USD',
      search_prompt:
        'USD/MYR exchange rate trend and its impact on imported ceramic tile landed cost over the last 30 days',
      cadence: 'weekly',
      is_active: true,
    },
    {
      id: 'topic-seed-2',
      label: 'Steel index (rebar & sheet)',
      category_ref: 'steel',
      currency: 'MYR',
      search_prompt:
        'Malaysia and regional steel price index movement for rebar and sheet steel, month on month',
      cadence: 'weekly',
      is_active: true,
    },
    {
      id: 'topic-seed-3',
      label: 'Container freight rates (Asia-EU)',
      category_ref: 'freight',
      currency: 'USD',
      search_prompt:
        'Shanghai Containerized Freight Index and Asia to Europe container freight rate trend this month',
      cadence: 'monthly',
      is_active: true,
    },
    {
      id: 'topic-seed-4',
      label: 'Sanitaryware demand outlook',
      category_ref: 'sanitaryware',
      currency: null,
      search_prompt:
        'Southeast Asia sanitaryware and bathroom fittings demand outlook and construction activity signals',
      cadence: 'manual',
      is_active: false,
    },
  ];
}

// ── Seed signals (~6) ────────────────────────────────────────────────────────
function seedSignals(): MarketSignal[] {
  return [
    {
      id: 'signal-seed-1',
      topic_label: 'Ceramic tile FX exposure',
      category_ref: 'ceramic-tiles',
      currency: 'USD',
      value: 4.72,
      trend: 'up',
      summary:
        'USD/MYR firmed to ~4.72, up ~2.1% over the month - imported tile landed cost rising; consider bringing forward USD-priced buys.',
      source_url: 'https://www.bnm.gov.my/exchange-rates',
      captured_at: '2026-07-16T01:15:00',
    },
    {
      id: 'signal-seed-2',
      topic_label: 'Steel index (rebar & sheet)',
      category_ref: 'steel',
      currency: 'MYR',
      value: 3180,
      trend: 'down',
      summary:
        'Domestic rebar eased to ~RM3,180/t, down ~1.6% MoM on softer regional demand - cost tailwind for steel-heavy SKUs.',
      source_url: 'https://www.meps.co.uk/gb/en/products/asian-steel-prices',
      captured_at: '2026-07-16T01:16:00',
    },
    {
      id: 'signal-seed-3',
      topic_label: 'Container freight rates (Asia-EU)',
      category_ref: 'freight',
      currency: 'USD',
      value: 3420,
      trend: 'up',
      summary:
        'SCFI Asia-EU leg climbed to ~USD3,420/FEU, up ~6% on Red Sea rerouting - inbound logistics cost pressure persists.',
      source_url: 'https://en.sse.net.cn/indices/scfinew.jsp',
      captured_at: '2026-07-15T01:20:00',
    },
    {
      id: 'signal-seed-4',
      topic_label: 'Ceramic tile FX exposure',
      category_ref: 'ceramic-tiles',
      currency: 'USD',
      value: null,
      trend: 'flat',
      summary:
        'Spanish and Italian tile export quotes broadly unchanged this month; no material EUR-side cost move to flag.',
      source_url: 'https://www.trademap.org',
      captured_at: '2026-07-14T01:10:00',
    },
    {
      id: 'signal-seed-5',
      topic_label: 'Steel index (rebar & sheet)',
      category_ref: 'steel',
      currency: 'MYR',
      value: 2960,
      trend: 'down',
      summary:
        'Hot-rolled sheet indications near RM2,960/t, down ~2.3% MoM - supports deferring price-protected steel purchases.',
      source_url: 'https://www.steelorbis.com',
      captured_at: '2026-07-13T01:18:00',
    },
    {
      id: 'signal-seed-6',
      topic_label: 'Container freight rates (Asia-EU)',
      category_ref: 'freight',
      currency: 'USD',
      value: null,
      trend: 'flat',
      summary:
        'Intra-Asia short-haul rates stable week on week; capacity adequate on regional lanes - no near-term freight shock expected.',
      source_url: 'https://www.freightos.com/freight-index',
      captured_at: '2026-07-12T01:22:00',
    },
  ];
}

function freshState(): StoreState {
  return {
    topics: seedTopics(),
    signals: seedSignals(),
    topicSeq: 0,
    signalSeq: 0,
    runSeq: 0,
  };
}

function load(): StoreState {
  if (typeof window === 'undefined') return freshState();
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoreState>;
      return { ...freshState(), ...parsed };
    }
  } catch {
    /* fall through to fresh */
  }
  return freshState();
}

let state: StoreState = load();

function persist() {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* sessionStorage unavailable - in-memory state still works for the session */
  }
}

function cloneTopics(): MarketResearchTopic[] {
  return state.topics.map((t) => ({ ...t }));
}

function cloneSignals(): MarketSignal[] {
  return state.signals.map((s) => ({ ...s }));
}

// ── Signal reads ─────────────────────────────────────────────────────────────

/** All cached signals, newest-captured first (drives the viz panel). */
export function mockListSignals(): MarketSignal[] {
  return cloneSignals().sort((a, b) => b.captured_at.localeCompare(a.captured_at));
}

// ── Topic CRUD ───────────────────────────────────────────────────────────────

export function mockListTopics(): MarketResearchTopic[] {
  return cloneTopics();
}

export function mockCreateTopic(body: MarketResearchTopicWrite): MarketResearchTopic {
  state.topicSeq += 1;
  const topic: MarketResearchTopic = { id: `topic-${state.topicSeq}`, ...body };
  state.topics = [topic, ...state.topics];
  persist();
  return { ...topic };
}

export function mockUpdateTopic(
  id: string,
  body: MarketResearchTopicWrite,
): MarketResearchTopic | null {
  const topic = state.topics.find((t) => t.id === id);
  if (!topic) return null;
  Object.assign(topic, body);
  persist();
  return { ...topic };
}

export function mockDeleteTopic(id: string): boolean {
  const before = state.topics.length;
  state.topics = state.topics.filter((t) => t.id !== id);
  const removed = state.topics.length < before;
  if (removed) persist();
  return removed;
}

// ── Research run ─────────────────────────────────────────────────────────────

/** Deterministic captured_at for a freshly-produced signal: fixed base date +
 *  the signal sequence as minutes past 09:00 (never the wall clock). */
function stampCapturedAt(seq: number): string {
  const mm = String(seq % 60).padStart(2, '0');
  const hh = String(9 + Math.floor(seq / 60)).padStart(2, '0');
  return `${RUN_BASE_DATE}T${hh}:${mm}:00`;
}

/**
 * "Run research": iterate the active topics and append a couple of fresh signals
 * (deterministic), returning a COMPLETED run whose `signal_count` = the new
 * signals produced. Mirrors the reorder-run terminal-completed shape so the hook
 * can drive running→complete feedback. No worker/polling in the mock.
 */
export function mockRunResearch(): MarketResearchRun {
  const active = state.topics.filter((t) => t.is_active);
  state.runSeq += 1;
  const startedAt = stampCapturedAt(state.signalSeq);

  // Produce one fresh signal for up to the first two active topics (deterministic).
  const produced: MarketSignal[] = [];
  const FRESH: {
    value: number | null;
    trend: MarketSignal['trend'];
    summary: string;
    source_url: string | null;
  }[] = [
    {
      value: 4.75,
      trend: 'up',
      summary:
        'Latest fixing nudged USD/MYR to ~4.75 - mild further upside; keep USD-priced tile buys under review.',
      source_url: 'https://www.bnm.gov.my/exchange-rates',
    },
    {
      value: 3150,
      trend: 'down',
      summary:
        'Rebar indications eased another ~1% to ~RM3,150/t - continued cost relief for steel-linked SKUs.',
      source_url: 'https://www.meps.co.uk/gb/en/products/asian-steel-prices',
    },
  ];

  active.slice(0, FRESH.length).forEach((topic, i) => {
    state.signalSeq += 1;
    const f = FRESH[i];
    produced.push({
      id: `signal-run${state.runSeq}-${state.signalSeq}`,
      topic_label: topic.label,
      category_ref: topic.category_ref,
      currency: topic.currency,
      value: f.value,
      trend: f.trend,
      summary: f.summary,
      source_url: f.source_url,
      captured_at: stampCapturedAt(state.signalSeq),
    });
  });

  state.signals = [...produced, ...state.signals];
  persist();

  const finishedAt = stampCapturedAt(state.signalSeq);
  return {
    id: `market-run-${state.runSeq}`,
    status: 'completed',
    started_at: startedAt,
    finished_at: finishedAt,
    topic_count: active.length,
    signal_count: produced.length,
    error: null,
  };
}

/** TEST/DEV ONLY - reset the store to its seed. */
export function __resetMarketMockStore() {
  state = freshState();
  persist();
}
