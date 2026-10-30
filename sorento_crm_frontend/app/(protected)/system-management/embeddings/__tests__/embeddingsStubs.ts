/** Shared fixtures for the Embeddings screen tests (LOOKUP-EMBED-CENTRAL slice 5, AC-LEC-23). */
import { vi } from 'vitest';

Element.prototype.scrollIntoView = vi.fn();
(Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

export const GEM = 'gemini-embedding-001';
export const M3S = 'text-embedding-3-small';
export const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

export const overview = {
  setting: { provider: 'gemini', model: GEM, backfill_rpm: 20 },
  records_search_model: M3S,
  lookup: { texts_total: 502, texts_with_vector: 422 },
  records: [
    { source_type: 'promotion', documents: 4321, chunks_by_model: { [M3S]: 4300, [GEM]: 1250 } },
    { source_type: 'attachment', documents: 987, chunks_by_model: { [M3S]: 980 } },
    { source_type: 'product_spec', documents: 55, chunks_by_model: {} },
  ],
  guard: { target_model: GEM, ready: false, remaining: 3000, failed: 2 },
};

export const lookupWords = {
  list: 'category',
  rows: [
    {
      key: '5b0a2c1e-1111-4222-8333-944455556666',
      label: 'Water Closet',
      source: 'product_categories',
      group: null,
      words: [
        { text: 'Water Closet', home: 'label', has_vector: true },
        { text: 'toilet bowl', home: 'alias_column', has_vector: true },
        { text: 'tandas', home: 'alias_column', has_vector: false },
        { text: 'WC-CODE', home: 'code', has_vector: false },
      ],
    },
    {
      key: '6c1b3d2f-2222-4333-8444-a55566667777',
      label: 'Tap',
      source: 'product_categories',
      group: null,
      words: [{ text: 'faucet', home: 'alias_set', has_vector: true }],
    },
  ],
};

export const tryResult = {
  verdict: 'resolved',
  candidates: [
    {
      list: 'category',
      key: '5b0a2c1e-1111-4222-8333-944455556666',
      label: 'Water Closet',
      spelling: { score: 0.31, text: 'toilet', home: 'alias_column' },
      vector: { score: 0.83, text: 'toilet bowl', home: 'alias_column' },
      partial: 0,
      floors: { spell: 0.5, partial: 0.8, meaning: 0.6 },
      passed: true,
      signal: 'meaning',
    },
    {
      list: 'category',
      key: '6c1b3d2f-2222-4333-8444-a55566667777',
      label: 'Tap',
      spelling: { score: 0.1, text: 'tap', home: 'label' },
      vector: null,
      partial: 0,
      floors: { spell: 0.5, partial: 0.8, meaning: 0.6 },
      passed: false,
      signal: 'spelling',
    },
  ],
};
