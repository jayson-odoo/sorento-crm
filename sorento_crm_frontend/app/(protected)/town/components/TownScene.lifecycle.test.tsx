import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

/**
 * The scene's lifecycle with a mocked WebGLRenderer and a hand-driven requestAnimationFrame:
 * nothing is drawn while the tab is hidden, and unmounting disposes the renderer and removes the
 * window listeners.
 */
const made = vi.hoisted(() => ({ instanced: [] as { count: number }[], sprites: 0 }));
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
    InstancedMesh: class extends actual.InstancedMesh {
      constructor(...args: ConstructorParameters<typeof actual.InstancedMesh>) {
        super(...args);
        made.instanced.push(this);
      }
    },
    Sprite: class extends actual.Sprite {
      constructor(...args: ConstructorParameters<typeof actual.Sprite>) {
        super(...args);
        made.sprites += 1;
      }
    },
    WebGLRenderer: class {
      constructor() {
        return renderer as unknown as object;
      }
    },
  };
});

import { TownScene } from './TownScene';
import { SCENE_TAG_CAP } from '../lib/townFormat';

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
  made.instanced.length = 0;
  made.sprites = 0;
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

describe('TownScene applies the crowding caps', () => {
  it('draws the 30 shops and 5 stalls at most, with at most SCENE_TAG_CAP shop tags, on a day of 60 lit stalls', () => {
    const shops = Array.from({ length: 30 }, (_, i) => ({
      key: `shop${i}`, kind: 'shop', account_label: null, today_docs: 1 + (i % 3), rank: i + 1, name: `Shop ${i}`,
    }));
    const stalls = Array.from({ length: 60 }, (_, i) => ({
      key: `stall${i}`, kind: 'stall', account_label: null, today_docs: 1 + (i % 7), rank: null, name: `Stall ${i}`,
    }));
    const crowded = {
      ...SNAPSHOT,
      today: { ...SNAPSHOT.today, dealer_customer_count: 90 },
      shops: [...shops, ...stalls],
    };
    render(<TownScene snapshot={crowded as never} onSelect={() => undefined} />);
    const shopMesh = made.instanced[0]; // the shops are the first instanced mesh the scene builds
    expect(shopMesh.count).toBeLessThanOrEqual(35);
    // fixed labels: low stock, to deliver, approvals, and "+N more dealers"
    expect(made.sprites - 4).toBeLessThanOrEqual(SCENE_TAG_CAP);
    expect(made.sprites - 4).toBeGreaterThan(0);
  });
});
