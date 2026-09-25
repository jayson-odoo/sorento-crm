/**
 * Sheet's overlay animates opacity exactly like Dialog's/AlertDialog's, so it
 * carries the same WAAPI hand-off race (#1250, follow-up to #1246's
 * dialog.animation-boundary.test.tsx). The content itself slides on `x`/`y`
 * under normal motion - not accelerated by WAAPI here (only `opacity` is, see
 * lib/motion.ts NOOP_ON_UPDATE) - but its `prefers-reduced-motion` fallback
 * (`slideVariants` in sheet.tsx) drops the slide for a same-frame opacity
 * change, which races exactly like every other surface's fade.
 *
 * jsdom has no `Element.prototype.animate`, so this guards the fix's wiring,
 * not the WAAPI race itself - see dialog.animation-boundary.test.tsx for the
 * full mechanism writeup.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import { MotionGlobalConfig } from 'motion/react';

const { onUpdateSpy } = vi.hoisted(() => ({ onUpdateSpy: vi.fn() }));

vi.mock('@/lib/motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/motion')>();
  return { ...actual, NOOP_ON_UPDATE: onUpdateSpy };
});

import { Sheet, SheetContent, SheetTitle } from './sheet';

const realMatchMedia = window.matchMedia;
const skipAnimations = MotionGlobalConfig.skipAnimations;

function mockMatchMedia(reducedMotion: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: reducedMotion,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

beforeEach(() => {
  onUpdateSpy.mockClear();
  MotionGlobalConfig.skipAnimations = false;
  mockMatchMedia(false);
});

afterEach(() => {
  MotionGlobalConfig.skipAnimations = skipAnimations;
  Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: realMatchMedia });
});

// Under normal (non-reduced) motion, the content slides on `x`/`y` while the
// overlay animates `opacity` alone - so a call's argument carries an `x` or
// `y` key if and only if it came from the content's `motion.div`.
function isContentCall(call: unknown[]): boolean {
  const latest = call[0] as Record<string, unknown> | undefined;
  if (latest === undefined) return false;
  return Object.prototype.hasOwnProperty.call(latest, 'x') || Object.prototype.hasOwnProperty.call(latest, 'y');
}

function splitCallsBySurface(calls: unknown[][]) {
  const contentCalls = calls.filter(isContentCall);
  const overlayCalls = calls.filter((call) => !isContentCall(call));
  return { overlayCalls, contentCalls };
}

function renderSheet(open: boolean) {
  return (
    <Sheet open={open}>
      <SheetContent>
        <SheetTitle>T</SheetTitle>
      </SheetContent>
    </Sheet>
  );
}

describe('Sheet overlay and content (slide) defeat WAAPI hand-off', () => {
  it('drives onUpdate on both the overlay and the sliding content while entering', async () => {
    render(renderSheet(true));
    await new Promise((resolve) => setTimeout(resolve, 500));

    const { overlayCalls, contentCalls } = splitCallsBySurface(onUpdateSpy.mock.calls);
    expect(overlayCalls.length).toBeGreaterThan(1);
    expect(contentCalls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate on both the overlay and the sliding content while closing', async () => {
    const { rerender } = render(renderSheet(true));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(renderSheet(false));
    await new Promise((resolve) => setTimeout(resolve, 500));

    const { overlayCalls, contentCalls } = splitCallsBySurface(onUpdateSpy.mock.calls);
    expect(overlayCalls.length).toBeGreaterThan(1);
    expect(contentCalls.length).toBeGreaterThan(1);
  });
});

// Isolated from the overlay entirely (`overlay={false}`), under forced
// `prefers-reduced-motion: reduce`, so every onUpdate call in this describe
// block can only have come from the content's own motion.div running its
// opacity fallback (slideVariants collapses to `{ opacity }` under reduced
// motion) - the surface the issue calls out by name.
describe("Sheet content drives onUpdate on its reduced-motion opacity fallback", () => {
  beforeEach(() => {
    mockMatchMedia(true);
  });

  function renderReducedMotionSheet(open: boolean) {
    return (
      <Sheet open={open}>
        <SheetContent overlay={false}>
          <SheetTitle>T</SheetTitle>
        </SheetContent>
      </Sheet>
    );
  }

  it('drives onUpdate while entering under reduced motion', async () => {
    render(renderReducedMotionSheet(true));
    await new Promise((resolve) => setTimeout(resolve, 200));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(0);
  });

  it('keeps driving onUpdate while closing under reduced motion', async () => {
    const { rerender } = render(renderReducedMotionSheet(true));
    await new Promise((resolve) => setTimeout(resolve, 200));
    onUpdateSpy.mockClear();

    rerender(renderReducedMotionSheet(false));
    await new Promise((resolve) => setTimeout(resolve, 200));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(0);
  });
});
