import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

/**
 * The scene's lifecycle with a mocked WebGLRenderer and a hand-driven requestAnimationFrame:
 * nothing is drawn while the tab is hidden, and unmounting disposes the renderer and removes the
 * window listeners.
 */
const renderer = vi.hoisted(() => ({
  render: vi.fn(),
  dispose: vi.fn(),
  setPixelRatio: vi.fn(),
  setSize: vi.fn(),
  getPixelRatio: () => 1,
}));
vi.mock('three', async (importOriginal) => {
  const actual = await importOriginal<typeof import('three')>();
  return {
    ...actual,
    WebGLRenderer: class {
      constructor() {
        return renderer as unknown as object;
      }
    },
  };
});

import { TownScene } from './TownScene';

const SNAPSHOT = {
  schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [{ key: 'k1', kind: 'shop', account_label: null, today_docs: 1, rank: 1 }],
  warehouses: [], reorder: { below_count: 0, set_count: 0 }, deliveries: { to_deliver: 0 },
  approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
};

let queue: FrameRequestCallback[] = [];
function flush(now: number) {
  const run = queue;
  queue = [];
  run.forEach((cb) => cb(now));
}
function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
}

beforeEach(() => {
  queue = [];
  Object.values(renderer).forEach((fn) => typeof fn === 'function' && 'mockClear' in fn && (fn as ReturnType<typeof vi.fn>).mockClear());
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => queue.push(cb));
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} });
  setHidden(false);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setHidden(false);
});

describe('TownScene lifecycle', () => {
  it('draws nothing while the tab is hidden, and draws again once it is visible', () => {
    setHidden(true);
    render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    flush(100);
    expect(renderer.render).not.toHaveBeenCalled();
    setHidden(false);
    document.dispatchEvent(new Event('visibilitychange'));
    flush(200);
    expect(renderer.render).toHaveBeenCalledTimes(1);
  });

  it('disposes the renderer and removes its window listeners on unmount', () => {
    const removed = vi.spyOn(window, 'removeEventListener');
    const { unmount } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    unmount();
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
    const names = removed.mock.calls.map((c) => c[0]);
    expect(names).toContain('pointermove');
    expect(names).toContain('pointerup');
    removed.mockRestore();
  });
});
