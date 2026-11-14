/**
 * ms_to_first_data is only reported for the document's first navigation (review fix N3): a shell
 * mounted later (a v1 -> v2 switch) or re-mounted in the same document sends null.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, renderHook } from '@testing-library/react';

vi.mock('next/navigation', () => ({ usePathname: () => '/first' }));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

let nowMs = 1000;

async function mountHook() {
  const { usePageView } = await import('./usePageView');
  return renderHook(() => usePageView());
}

function firstItem(): { ms_to_first_data: number | null } {
  // unmount flushes the queue
  const call = apiFetch.mock.calls.find(([, init]) => init?.method === 'POST');
  return JSON.parse(call![1].body).items[0];
}

beforeEach(() => {
  vi.resetModules();
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
  vi.spyOn(performance, 'getEntriesByType').mockImplementation(
    ((type: string) => (type === 'paint' ? [{ name: 'first-contentful-paint', startTime: 812.4 }] : [])) as never,
  );
  vi.spyOn(performance, 'now').mockImplementation(() => nowMs);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('usePageView ms_to_first_data', () => {
  it('reports the first paint for the document\'s first navigation', async () => {
    nowMs = 1500;
    (await mountHook()).unmount();
    expect(firstItem().ms_to_first_data).toBe(812);
  });

  it('sends null when the shell mounted long after the document loaded', async () => {
    nowMs = 5 * 60 * 1000;
    (await mountHook()).unmount();
    expect(firstItem().ms_to_first_data).toBeNull();
  });

  it('sends null for a re-mount in the same document', async () => {
    nowMs = 1500;
    (await mountHook()).unmount();
    apiFetch.mockClear();
    (await mountHook()).unmount();
    expect(firstItem().ms_to_first_data).toBeNull();
  });
});
