/**
 * Dialog no longer blanks for a frame after opening or flashes the scrim for
 * a frame while closing.
 *
 * A real-browser frame trace (agent-browser, recorded against this file's
 * `main` ancestor) showed: right when the enter spring reached its target,
 * BOTH the overlay and the content dropped to `opacity: 0` for exactly one
 * frame before returning to `1`; right when the exit spring finished, BOTH
 * jumped BACK to `opacity: 1` for exactly one frame before AnimatePresence
 * unmounted them. The cause is motion/react handing `opacity`/`transform` off
 * to the browser's native Web Animations API whenever nothing reads the value
 * every frame (motion-dom's `supportsBrowserAnimation`,
 * node_modules/motion-dom/dist/es/animation/waapi/supports/waapi.mjs).
 * WAAPI's own completion handler (NativeAnimation.mjs `onfinish`) writes the
 * settled value through the motion value - which only lands on motion's next
 * scheduled render tick - and THEN cancels the native animation immediately,
 * which strips its effect before that write has reached the inline style.
 * The element is left, for that one frame, on whatever inline opacity motion
 * set before this phase started: `0` (the pre-entrance value) on enter,
 * `1` (the pre-exit, fully-open value) on exit.
 *
 * jsdom has no `Element.prototype.animate`, so motion always takes its JS
 * ticker path there and this race is structurally unreachable - it cannot be
 * asserted by driving a real animation in this suite (see the frame-trace
 * evidence in the PR body instead). What CAN be pinned here is the fix
 * itself: passing `onUpdate` to a motion value disqualifies WAAPI outright
 * (`!onUpdate` in supportsBrowserAnimation), so this asserts the overlay's
 * AND the content's `motion.div` are EACH wired with one, and that motion
 * actually invokes it on each surface while animating - i.e. the disqualifier
 * is live on both, not a prop that silently does nothing on one of them.
 *
 * `onUpdate` is called with the element's `latestValues` (framer-motion's
 * `VisualElement.notifyUpdate`, `this.notify('Update', this.latestValues)`).
 * Under the non-reduced motion this suite forces, the content's variants
 * (`surfaceVariants` in lib/motion.ts) animate `{ opacity, scale }` while the
 * overlay animates `opacity` alone - so a call's argument carries a `scale`
 * key if and only if it came from the content's `motion.div`. That split is
 * how the two assertions below tell the surfaces apart from one shared spy.
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

import { Dialog, DialogContent, DialogTitle } from './dialog';

const realMatchMedia = window.matchMedia;
const skipAnimations = MotionGlobalConfig.skipAnimations;

beforeEach(() => {
  onUpdateSpy.mockClear();
  // Force the real spring path (not the reduced-motion same-frame collapse) -
  // the WAAPI hand-off this test guards against only happens on a real,
  // multi-frame animation.
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

// A call came from the content's `motion.div` iff its `latestValues` carries
// `scale` - only the content's variants animate scale (see file header).
function isContentCall(call: unknown[]): boolean {
  const latest = call[0] as Record<string, unknown> | undefined;
  return latest !== undefined && Object.prototype.hasOwnProperty.call(latest, 'scale');
}

function splitCallsBySurface(calls: unknown[][]) {
  const contentCalls = calls.filter(isContentCall);
  const overlayCalls = calls.filter((call) => !isContentCall(call));
  return { overlayCalls, contentCalls };
}

describe('Dialog defeats WAAPI hand-off on its animated surfaces', () => {
  it('drives onUpdate on both the overlay and the content while entering', async () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>T</DialogTitle>
        </DialogContent>
      </Dialog>,
    );

    await new Promise((resolve) => setTimeout(resolve, 500));

    // Each surface's own `motion.div` ticks onUpdate on every frame of a real
    // spring, so a healthy run calls each one this many times. Asserted per
    // surface (not summed) so deleting `onUpdate` from just one of the two
    // `motion.div`s - which reintroduces that surface's WAAPI flicker - fails
    // this test instead of hiding behind the other surface's calls.
    const { overlayCalls, contentCalls } = splitCallsBySurface(onUpdateSpy.mock.calls);
    expect(overlayCalls.length).toBeGreaterThan(1);
    expect(contentCalls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate on both the overlay and the content while closing', async () => {
    const { rerender } = render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>T</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    onUpdateSpy.mockClear();

    rerender(
      <Dialog open={false}>
        <DialogContent>
          <DialogTitle>T</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    await new Promise((resolve) => setTimeout(resolve, 500));

    const { overlayCalls, contentCalls } = splitCallsBySurface(onUpdateSpy.mock.calls);
    expect(overlayCalls.length).toBeGreaterThan(1);
    expect(contentCalls.length).toBeGreaterThan(1);
  });
});
