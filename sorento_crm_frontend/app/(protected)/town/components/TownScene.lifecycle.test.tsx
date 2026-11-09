import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

/**
 * The scene's lifecycle with a mocked WebGLRenderer and a hand-driven requestAnimationFrame:
 * nothing is drawn while the tab is hidden, and unmounting disposes the renderer and removes the
 * window listeners.
 */
const made = vi.hoisted(() => ({ instanced: [] as { count: number }[], sprites: 0 }));
const stacked = vi.hoisted(() => ({ calls: [] as { obstacles: { x: number; y: number }[] }[] }));
vi.mock('../lib/townFormat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/townFormat')>();
  return {
    ...actual,
    stackTags: (tags: never, margin: never, options: { obstacles: { x: number; y: number }[] }) => {
      stacked.calls.push({ obstacles: options.obstacles });
      return actual.stackTags(tags, margin, options as never);
    },
  };
});
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
  stacked.calls.length = 0;
  Object.values(renderer).forEach((fn) => typeof fn === 'function' && 'mockClear' in fn && (fn as ReturnType<typeof vi.fn>).mockClear());
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => queue.push(cb));
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} });
  setHidden(false);
  // a real canvas size, so the scene lays its labels out in a real view
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', { configurable: true, get: () => 900 });
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientHeight', { configurable: true, get: () => 620 });
});

afterEach(() => {
  delete (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).clientWidth;
  delete (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).clientHeight;
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

describe('TownScene keeps tags clear of every fixed label', () => {
  it('stacks the tags around the scoreboard, the "!" bubble, the depot sign, the approvals badge and the "+N" pill', () => {
    const lit = {
      ...SNAPSHOT,
      today: { ...SNAPSHOT.today, dealer_customer_count: 9 },
      shops: [{ key: 's1', kind: 'shop', account_label: null, today_docs: 2, rank: null }],
      reorder: { below_count: 5, set_count: 9 },
      deliveries: { to_deliver: 4 },
      approvals: { total: 2, purchase_requests: 2, quotation_documents: 0 },
    };
    render(<TownScene snapshot={lit as never} onSelect={() => undefined} />);
    const { obstacles } = stacked.calls[stacked.calls.length - 1];
    // the scoreboard, "!", "To deliver", the approvals badge and "+N more dealers"
    expect(obstacles).toHaveLength(5);
    const spots = new Set(obstacles.map((o) => `${o.x.toFixed(2)},${o.y.toFixed(2)}`));
    expect(spots.size).toBe(5); // five different places, not one repeated
  });
});

describe('TownScene fixed labels never cover the scoreboard or each other, at any turn', () => {
  const lit = {
    ...SNAPSHOT,
    today: { ...SNAPSHOT.today, dealer_customer_count: 9 },
    shops: [{ key: 's1', kind: 'shop', account_label: null, today_docs: 2, rank: null }],
    reorder: { below_count: 5, set_count: 9 },
    deliveries: { to_deliver: 4 },
    approvals: { total: 2, purchase_requests: 2, quotation_documents: 0 },
  };
  type Box = { x: number; y: number; w: number; h: number };
  const hit = (a: Box, b: Box) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;

  it('holds from 0 to 2 pi in steps of 0.1 rad', () => {
    const { container } = render(<TownScene snapshot={lit as never} onSelect={() => undefined} />);
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    canvas.dispatchEvent(new MouseEvent('pointerdown', { clientX: 0, bubbles: true }));
    const bad: string[] = [];
    for (let k = 0; k <= 63; k++) {
      const yaw = k * 0.1;
      window.dispatchEvent(new MouseEvent('pointermove', { clientX: (Math.PI / 4 - yaw) / 0.006 }));
      const [board, ...labels] = stacked.calls[stacked.calls.length - 1].obstacles as unknown as Box[];
      expect(labels).toHaveLength(4);
      labels.forEach((label, i) => {
        if (hit(label, board)) bad.push(`yaw ${yaw.toFixed(1)}: label ${i} covers the scoreboard`);
        labels.slice(i + 1).forEach((other, j) => {
          if (hit(label, other)) bad.push(`yaw ${yaw.toFixed(1)}: labels ${i} and ${i + 1 + j} overlap`);
        });
      });
    }
    window.dispatchEvent(new MouseEvent('pointerup', { clientX: 0 }));
    expect(bad).toEqual([]);
  });
});
