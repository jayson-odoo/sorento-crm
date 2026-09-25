/**
 * Sheet content's `prefers-reduced-motion` opacity fallback (`slideVariants`
 * in sheet.tsx collapses the slide to `{ opacity }` under reduced motion)
 * races WAAPI's hand-off exactly like every other opacity-animating surface,
 * so `sheet.tsx` wires `onUpdate={prefersReducedMotion ? NOOP_ON_UPDATE :
 * undefined}` on the content - conditional, since the normal-motion slide on
 * `x`/`y` is not in WAAPI's `acceleratedValues` and needs no listener at all
 * (see sheet.animation-boundary.test.tsx for that half).
 *
 * This is a SEPARATE file, not a second `describe` in
 * sheet.animation-boundary.test.tsx, because framer-motion's
 * `useReducedMotion` (node_modules/framer-motion/dist/es/utils/reduced-motion/use-reduced-motion.mjs)
 * reads `window.matchMedia('(prefers-reduced-motion: reduce)')` exactly ONCE
 * per process, lazily, on its first-ever call (`!hasReducedMotionListener.current`
 * gates a MODULE-LEVEL cache in `./state.mjs`) - every later call in the same
 * test file reads the cached value, no matter what `window.matchMedia` is
 * mocked to afterward. A single file can only ever exercise one of
 * normal/reduced motion; putting this in its own file gives it a fresh module
 * graph (and therefore a fresh, uncached first read) so mocking
 * `matchMedia` to reduced-motion BEFORE the first render actually takes.
 *
 * jsdom has no `Element.prototype.animate`, so this guards the fix's wiring,
 * not the WAAPI race itself - see dialog.animation-boundary.test.tsx for the
 * full mechanism writeup.
 */
import React from 'react';
import { describe, it, expect, vi, beforeAll, beforeEach, afterAll } from 'vitest';
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

// Must run before ANY render in this file - useReducedMotion's module-level
// cache locks in whatever matchMedia says on its first call.
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterAll(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: realMatchMedia });
});

beforeEach(() => {
  onUpdateSpy.mockClear();
  MotionGlobalConfig.skipAnimations = false;
});

// `overlay={false}` isolates the content entirely - with no overlay
// `motion.div` mounted, every onUpdate call the shared spy sees can only be
// the content's own.
function renderReducedMotionSheet(open: boolean) {
  return (
    <Sheet open={open}>
      <SheetContent overlay={false}>
        <SheetTitle>T</SheetTitle>
      </SheetContent>
    </Sheet>
  );
}

describe('Sheet content drives onUpdate on its reduced-motion opacity fallback', () => {
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
