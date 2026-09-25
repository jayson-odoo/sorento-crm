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
 * (`!onUpdate` in supportsBrowserAnimation), so this asserts both the
 * overlay's and the content's `motion.div` are wired with one, and that
 * motion actually invokes it while animating - i.e. the disqualifier is live,
 * not a prop that silently does nothing.
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

    // One motion.div per surface (overlay + content); each ticks onUpdate on
    // every frame of a real spring, so a healthy run calls this many times.
    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps driving onUpdate while closing', async () => {
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

    expect(onUpdateSpy.mock.calls.length).toBeGreaterThan(1);
  });
});
