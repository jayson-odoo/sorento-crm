/**
 * Sheet's overlay animates opacity exactly like Dialog's/AlertDialog's, so it
 * carries the same WAAPI hand-off race (#1250, follow-up to #1246's
 * dialog.animation-boundary.test.tsx). The content itself slides on `x`/`y`
 * under normal motion - not in WAAPI's `acceleratedValues` (opacity, clipPath,
 * filter, transform; see lib/motion.ts NOOP_ON_UPDATE) - so it carries no
 * `onUpdate` here at all; it only gets one conditionally, under reduced
 * motion, where `slideVariants` collapses to an opacity-only fallback that
 * races the same way (see sheet.reduced-motion.animation-boundary.test.tsx).
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

beforeEach(() => {
  onUpdateSpy.mockClear();
  MotionGlobalConfig.skipAnimations = false;
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
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

afterEach(() => {
  MotionGlobalConfig.skipAnimations = skipAnimations;
  Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: realMatchMedia });
});

function renderSheet(open: boolean) {
  return (
    <Sheet open={open}>
      <SheetContent>
        <SheetTitle>T</SheetTitle>
      </SheetContent>
    </Sheet>
  );
}

// Under normal (non-reduced) motion the content slides on `x`/`y` alone and
// carries no `onUpdate` at all (see sheet.tsx - it is conditional on reduced
// motion), so every call the shared spy sees here is the overlay's.
describe('Sheet overlay defeats WAAPI hand-off (normal motion)', () => {
  it('drives onUpdate on the overlay while entering', async () => {
    render(renderSheet(true));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate on the overlay while closing', async () => {
    const { rerender } = render(renderSheet(true));
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(renderSheet(false));
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});
