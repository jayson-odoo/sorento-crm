import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

/**
 * Input on the town (TOWN-V2 UAC 1, 4, 12) with a mocked WebGLRenderer. The one seam is the ray cast:
 * `Raycaster.intersectObjects` reports a hit on the shop mesh while `aim.on` is set, so the scene's
 * own picking, tooltip and lightbox code runs unchanged.
 */
const aim = vi.hoisted(() => ({ on: false }));
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
    Raycaster: class extends actual.Raycaster {
      intersectObjects(objects: import('three').Object3D[]) {
        const shops = objects.find((o) => o.name === 'shops');
        return aim.on && shops ? ([{ object: shops, instanceId: 0, distance: 1 }] as never) : [];
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

const SNAPSHOT = {
  schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [{ key: 'k1', kind: 'shop', account_label: 'A/C I', today_docs: 2, rank: 1, name: 'ZZT Tiling SDN BHD [A/C I]' }],
  warehouses: [], reorder: { below_count: 0, set_count: 0 }, deliveries: { to_deliver: 0 },
  approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
};

let queue: FrameRequestCallback[] = [];
function settle(start: number, max = 400) {
  let now = start;
  let frames = 0;
  for (; frames < max && queue.length; frames++) {
    const run = queue;
    queue = [];
    run.forEach((cb) => cb((now += 50)));
  }
  return frames;
}
let mediaListeners: ((e: { matches: boolean }) => void)[] = [];
const mediaRemoved = vi.fn();
function stubMedia(reduce: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: reduce && query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => mediaListeners.push(cb),
      removeEventListener: mediaRemoved,
    }),
  });
}
function pointer(type: string, target: EventTarget, pointerType: 'mouse' | 'touch', extra: Record<string, number> = {}) {
  const event = new MouseEvent(type, { bubbles: true, clientX: 300, clientY: 300, ...extra });
  Object.defineProperty(event, 'pointerType', { value: pointerType });
  Object.defineProperty(event, 'pointerId', { value: extra.pointerId ?? 1 });
  act(() => {
    target.dispatchEvent(event);
  });
}

beforeEach(() => {
  queue = [];
  aim.on = false;
  mediaListeners = [];
  mediaRemoved.mockClear();
  window.localStorage.clear();
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => queue.push(cb));
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation((() => null) as never);
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 900, height: 620, right: 900, bottom: 620, x: 0, y: 0, toJSON: () => ({}) });
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', { configurable: true, get: () => 900 });
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientHeight', { configurable: true, get: () => 620 });
  stubMedia(false);
});

afterEach(() => {
  delete (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).clientWidth;
  delete (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).clientHeight;
  delete (window as unknown as Record<string, unknown>).matchMedia;
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('TownScene input', () => {
  it('UAC 1: a mouse over a building shows its tooltip, and leaving the canvas hides it', () => {
    const { container } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    aim.on = true;
    pointer('pointermove', canvas, 'mouse');
    const tip = screen.getByRole('tooltip');
    expect(tip.textContent).toContain('ZZT Tiling [A/C I]');
    expect(tip.textContent).toContain('2 invoices today');
    pointer('pointerleave', canvas, 'mouse');
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('UAC 1: the mouse over empty ground shows no tooltip', () => {
    const { container } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    pointer('pointermove', container.querySelector('canvas') as HTMLCanvasElement, 'mouse');
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('UAC 4: a tap on a building opens its lightbox straight away, with no tooltip', () => {
    const onSelect = vi.fn();
    const { container } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={onSelect} />);
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    aim.on = true;
    pointer('pointerdown', canvas, 'touch');
    pointer('pointermove', canvas, 'touch'); // a touch never hovers
    expect(screen.queryByRole('tooltip')).toBeNull();
    pointer('pointerup', canvas, 'touch');
    expect(onSelect).toHaveBeenCalledWith({ kind: 'shop', key: 'k1' });
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('UAC 4: a drag turns the town and opens nothing', () => {
    const onSelect = vi.fn();
    const { container } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={onSelect} />);
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    aim.on = true;
    pointer('pointerdown', canvas, 'touch');
    pointer('pointermove', canvas, 'touch', { clientX: 380 });
    pointer('pointerup', canvas, 'touch', { clientX: 380 });
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe('TownScene motion controls', () => {
  it('UAC 12: with motion on, frames keep coming; Pause stops them, and the choice is remembered', () => {
    render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    expect(settle(0, 200)).toBe(200); // the town moves: a frame is always asked for
    expect(queue.length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Pause motion' }));
    settle(20000); // the fly-in, if still running, finishes; then nothing more
    expect(queue).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Play motion' })).toBeTruthy();
    expect(window.localStorage.getItem('town_motion')).toBe('off');
  });

  it('follows a reduced-motion switch while open, and removes its listener on unmount', () => {
    const { unmount } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    expect(mediaListeners.length).toBeGreaterThan(0);
    act(() => mediaListeners.forEach((cb) => cb({ matches: true })));
    settle(0);
    expect(queue).toHaveLength(0); // static now: nothing drives or bobs
    expect(screen.getByRole('button', { name: 'Play motion' })).toBeTruthy();
    unmount();
    expect(mediaRemoved).toHaveBeenCalledWith('change', expect.any(Function));
  });
});

describe('TownScene label pills', () => {
  it('are out of the pointer and tab order while hidden during the fly-in', () => {
    const { container } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    const pills = Array.from(container.querySelectorAll<HTMLButtonElement>('[data-town-label]'));
    expect(pills.length).toBeGreaterThan(0);
    pills.forEach((pill) => {
      expect(pill.dataset.state).toBe('hidden');
      expect(pill.tabIndex).toBe(-1);
      expect(pill.className).toContain('data-[state=hidden]:pointer-events-none');
    });
  });

  it('come back into the tab order once shown', () => {
    stubMedia(true); // no fly-in: shown at once
    const { container } = render(<TownScene snapshot={SNAPSHOT as never} onSelect={() => undefined} />);
    const pills = Array.from(container.querySelectorAll<HTMLButtonElement>('[data-town-label]'));
    pills.forEach((pill) => {
      expect(pill.dataset.state).not.toBe('hidden');
      expect(pill.tabIndex).toBe(pill.dataset.state === 'shown' ? 0 : -1);
    });
  });
});
