import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

/**
 * The scene's lifecycle with a mocked WebGLRenderer and a hand-driven requestAnimationFrame: nothing
 * is drawn while the tab is hidden, unmounting disposes the renderer and removes the listeners and
 * the labels, the crowding and port caps hold, reduced motion leaves nothing scheduled once drawn, and
 * a poll with a new invoice schedules frames for the one sale beat without replaying the fly-in.
 */
const made = vi.hoisted(() => ({ instanced: [] as { count: number; name: string }[] }));
const renderer = vi.hoisted(() => ({
  render: vi.fn(),
  dispose: vi.fn(),
  setPixelRatio: vi.fn(),
  setSize: vi.fn(),
  getPixelRatio: () => 1,
  shadowMap: { enabled: false, type: 0 },
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
/** Runs frames 50 ms apart until nothing asks for another (or gives up after `max`); returns how many ran. */
function settle(start: number, max = 400) {
  let now = start;
  let frames = 0;
  for (; frames < max && queue.length; frames++) flush((now += 50));
  return frames;
}
function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
}
function stubReducedMotion(reduce: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => ({ matches: reduce && query.includes('prefers-reduced-motion'), media: query, addEventListener() {}, removeEventListener() {} }),
  });
}
const mesh = (name: string) => made.instanced.find((m) => m.name === name);
const labelTexts = (container: HTMLElement) => Array.from(container.querySelectorAll('[data-town-label]')).map((el) => el.textContent);

beforeEach(() => {
  queue = [];
  made.instanced.length = 0;
  Object.values(renderer).forEach((fn) => typeof fn === 'function' && 'mockClear' in fn && (fn as ReturnType<typeof vi.fn>).mockClear());
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => queue.push(cb));
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation((() => null) as never);
  setHidden(false);
  stubReducedMotion(false);
  // a real canvas size, so the scene lays its labels out in a real view
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', { configurable: true, get: () => 900 });
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientHeight', { configurable: true, get: () => 620 });
});

afterEach(() => {
  delete (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).clientWidth;
  delete (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).clientHeight;
  delete (window as unknown as Record<string, unknown>).matchMedia;
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setHidden(false);
});

describe('TownScene lifecycle', () => {
  it('draws nothing while the tab is hidden, and draws again once it is visible', () => {
    setHidden(true);
    render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    flush(100);
    expect(renderer.render).not.toHaveBeenCalled();
    expect(queue).toHaveLength(0); // nothing is even scheduled while hidden
    setHidden(false);
    document.dispatchEvent(new Event('visibilitychange'));
    flush(200);
    expect(renderer.render).toHaveBeenCalledTimes(1);
  });

  it('disposes the renderer, removes its listeners and its labels on unmount', () => {
    const removed = vi.spyOn(window, 'removeEventListener');
    const removedDoc = vi.spyOn(document, 'removeEventListener');
    const { container, unmount } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    expect(container.querySelectorAll('[data-town-label]').length).toBeGreaterThan(0);
    const labelLayer = container.querySelector('[data-town-label]')?.parentElement as HTMLElement;
    unmount();
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
    const names = removed.mock.calls.map((c) => c[0]);
    expect(names).toContain('pointermove');
    expect(names).toContain('pointerup');
    expect(removedDoc.mock.calls.map((c) => c[0])).toContain('visibilitychange');
    expect(labelLayer.querySelectorAll('[data-town-label]')).toHaveLength(0);
  });

  it('keeps one renderer across snapshot polls', () => {
    const { rerender } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    rerender(<TownScene snapshot={{ ...SNAPSHOT, reorder: { below_count: 3, set_count: 9 } } as never} onSelect={() => undefined} />);
    expect(renderer.dispose).not.toHaveBeenCalled();
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
    const crowded = { ...SNAPSHOT, today: { ...SNAPSHOT.today, dealer_customer_count: 90 }, shops: [...shops, ...stalls] };
    const { container } = render(<TownScene snapshot={crowded as never} onSelect={() => undefined} />);
    expect(mesh('shops')?.count).toBeLessThanOrEqual(30);
    expect(mesh('stalls')?.count).toBeLessThanOrEqual(5);
    const tags = container.querySelectorAll('[data-town-label="tag"]');
    expect(tags.length).toBeLessThanOrEqual(SCENE_TAG_CAP);
    expect(tags.length).toBeGreaterThan(0);
  });

  it('sends at most 6 lorries to customers, and parks up to 10 when the snapshot names no customers', () => {
    const customers = Array.from({ length: 8 }, (_, i) => ({ key: i % 2 ? 'k1' : null, name: i % 2 ? null : `Away ${i}`, orders: 1 }));
    render(<TownScene snapshot={{ ...SNAPSHOT, deliveries: { to_deliver: 14, customers } } as never} onSelect={() => undefined} />);
    expect(mesh('lorries')?.count).toBe(6);
    cleanup();
    made.instanced.length = 0;
    render(<TownScene snapshot={{ ...SNAPSHOT, deliveries: { to_deliver: 14 } } as never} onSelect={() => undefined} />);
    expect(mesh('lorries')?.count).toBe(10);
  });
});

describe('TownScene draws the port (TOWN-V2)', () => {
  it('draws at most 6 ships and 12 late containers, and the port signs, for any number of shipments', () => {
    const busy = { ...SNAPSHOT, incoming: { incoming: 29, late: 70, next_eta: '2026-01-07', shipments: [] } };
    const { container } = render(<TownScene snapshot={busy as never} onSelect={() => undefined} />);
    expect(mesh('ships')?.count).toBe(6); // ships at anchor: incoming shipments
    expect(mesh('late containers')?.count).toBe(12); // red containers on the quay: late shipments
    expect(labelTexts(container)).toEqual(expect.arrayContaining(['Incoming: 29', '70 late']));
  });

  it('draws no port on a snapshot without incoming shipments', () => {
    const { container } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    expect(mesh('ships')).toBeUndefined();
    expect(labelTexts(container).some((t) => t?.startsWith('Incoming'))).toBe(false);
    cleanup();
    made.instanced.length = 0;
    const again = render(<TownScene snapshot={{ ...SNAPSHOT, incoming: { incoming: 3, late: 2, next_eta: null, shipments: [] } } as never} onSelect={() => undefined} />);
    expect(mesh('ships')?.count).toBe(3);
    expect(labelTexts(again.container)).toEqual(expect.arrayContaining(['Incoming: 3', '2 late']));
  });
});

describe('TownScene motion guard rails', () => {
  const sold = {
    ...SNAPSHOT,
    today: { ...SNAPSHOT.today, invoice_count: 4 },
    shops: [{ ...SNAPSHOT.shops[0], today_docs: 2 }],
  };

  it('under reduced motion schedules no frame once drawn, and a poll with a new invoice schedules frames for the beat', () => {
    stubReducedMotion(true);
    const { rerender } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    settle(0, 3);
    expect(renderer.render).toHaveBeenCalled();
    expect(queue).toHaveLength(0);
    rerender(<TownScene snapshot={sold as never} onSelect={() => undefined} />);
    expect(queue.length).toBeGreaterThan(0);
    // the colour and number change runs over several frames (a plain rebuild draws one), then stops
    expect(settle(1000)).toBeGreaterThan(5);
    expect(queue).toHaveLength(0);
  });

  it('a poll with the same invoices plays no beat', () => {
    stubReducedMotion(true);
    const { rerender } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    settle(0, 3);
    rerender(<TownScene snapshot={{ ...SNAPSHOT, reorder: { below_count: 4, set_count: 9 } } as never} onSelect={() => undefined} />);
    expect(settle(1000)).toBe(1); // the rebuilt town is drawn once, then nothing moves
    expect(queue).toHaveLength(0);
  });

  it('flies in on the first snapshot only: labels wait for the fly-in, then show at once on the next poll', () => {
    const { container, rerender } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    const states = () => Array.from(container.querySelectorAll<HTMLElement>('[data-town-label]')).map((el) => el.dataset.state);
    expect(states().every((s) => s === 'hidden')).toBe(true);
    rerender(<TownScene snapshot={sold as never} onSelect={() => undefined} />);
    expect(states().length).toBeGreaterThan(0);
    expect(states().every((s) => s !== 'hidden')).toBe(true);
  });
});
