/**
 * M3-01/M3-02 (`ui-motion-round2`) - the shared draining scaleX fill.
 */
import React, { type CSSProperties } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, renderHook } from '@testing-library/react';
import { useDrainingScaleXFill } from './useDrainingScaleXFill';

/**
 * `vitest.setup.ts` makes `prefers-reduced-motion` MATCH by default (so the
 * suite does not pay a spring's settle time on every dialog), which would put
 * every test in this file on the reduced branch by accident. The branch under
 * test is named here instead: full motion above, reduced motion in its own
 * block at the bottom.
 */
const motionPreference = vi.hoisted(() => ({ reduced: false }));
vi.mock('@/lib/motion', () => ({
  useReducedMotion: () => motionPreference.reduced,
}));

beforeEach(() => {
  motionPreference.reduced = false;
  vi.useFakeTimers();
  vi.setSystemTime(Date.UTC(2026, 7, 30, 10, 0, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

/**
 * Mounts the hook inside a REAL `<React.StrictMode>` element.
 *
 * `next.config.mjs` sets `reactStrictMode: true`, so every effect in dev is
 * mounted, cleaned up and mounted AGAIN before the browser paints. The arm has
 * to survive that replay: the first pass's frames are cancelled by the
 * synthetic cleanup, so whatever the SECOND pass sees must still arm the
 * transition. A ref the first pass set and the cleanup did not reset is exactly
 * what stopped it - the fill sat frozen at `scaleX(1)` for the whole window on
 * both surfaces (`evidence/M3/README.md`, M3-01 FAIL).
 *
 * `renderHook`'s `wrapper` option does NOT reproduce the double-invoke
 * (measured on this repo: wrapper -> one `mount`; an inline `<StrictMode>`
 * element -> `mount`, `cleanup`, `mount`), so this renders the element itself
 * rather than passing a wrapper.
 */
function renderStrict(targetMs: number, startFraction: number) {
  const seen: { current: CSSProperties } = { current: {} };
  function Probe() {
    seen.current = useDrainingScaleXFill(targetMs, startFraction);
    return null;
  }
  render(React.createElement(React.StrictMode, null, React.createElement(Probe)));
  return seen;
}

/** Two frames, not a millisecond guess - see DeferredActionButton.test.tsx. */
function armFrames() {
  act(() => {
    vi.advanceTimersToNextFrame();
  });
  act(() => {
    vi.advanceTimersToNextFrame();
  });
}

describe('useDrainingScaleXFill', () => {
  it('starts at the given fraction with no transition, then drains to scaleX(0) over the remaining time', () => {
    const target = Date.now() + 10_000;
    const { result } = renderHook(() => useDrainingScaleXFill(target, 1));

    expect(result.current.transform).toBe('scaleX(1)');
    expect(result.current.transitionDuration).toBeUndefined();

    armFrames();

    expect(result.current.transform).toBe('scaleX(0)');
    expect(result.current.transitionProperty).toBe('transform');
    expect(result.current.transitionDuration).toBe('10000ms');
    expect(result.current.transitionTimingFunction).toBe('linear');
  });

  it('arms inside <React.StrictMode>, whose double-invoked effect replays the mount', () => {
    const target = Date.now() + 10_000;
    const seen = renderStrict(target, 1);

    // First frame: the value the transition below has to travel FROM.
    expect(seen.current.transform).toBe('scaleX(1)');
    expect(seen.current.transitionDuration).toBeUndefined();

    armFrames();

    expect(seen.current.transform).toBe('scaleX(0)');
    expect(seen.current.transitionProperty).toBe('transform');
    expect(seen.current.transitionDuration).toBe('10000ms');
    expect(seen.current.transitionTimingFunction).toBe('linear');
  });

  it('arms identically without StrictMode (the production build)', () => {
    const target = Date.now() + 10_000;
    const { result } = renderHook(() => useDrainingScaleXFill(target, 1));
    armFrames();
    expect(result.current.transform).toBe('scaleX(0)');
    expect(result.current.transitionDuration).toBe('10000ms');
  });

  it('starts short on a late mount, not full (remount-safe)', () => {
    // Only 10% of the window is left.
    const target = Date.now() + 6_000;
    const { result } = renderHook(() => useDrainingScaleXFill(target, 0.1));
    expect(result.current.transform).toBe('scaleX(0.1)');
  });

  it('never sets width', () => {
    const target = Date.now() + 5_000;
    const { result } = renderHook(() => useDrainingScaleXFill(target, 1));
    armFrames();
    expect(result.current).not.toHaveProperty('width');
  });

  it('re-arms once when the target changes', () => {
    const first = Date.now() + 5_000;
    const { result, rerender } = renderHook(({ target }) => useDrainingScaleXFill(target, 1), {
      initialProps: { target: first },
    });
    armFrames();
    expect(result.current.transform).toBe('scaleX(0)');

    const second = Date.now() + 8_000;
    rerender({ target: second });
    // Resets to full with no transition before the next arm.
    expect(result.current.transform).toBe('scaleX(1)');
    expect(result.current.transitionDuration).toBeUndefined();

    armFrames();
    expect(result.current.transform).toBe('scaleX(0)');
    expect(result.current.transitionDuration).toBe('8000ms');
  });

  it('parks at the start fraction with no transition when targetMs is 0', () => {
    const { result } = renderHook(() => useDrainingScaleXFill(0, 1));
    armFrames();
    expect(result.current.transform).toBe('scaleX(1)');
    expect(result.current.transitionDuration).toBeUndefined();
  });
});

/**
 * M3-01 fix round: the hook writes its transition as an INLINE style, and an
 * inline `transition-duration` beats the `motion-reduce:transition-none` class
 * the two callers carry - so the class alone left a full-speed tween running
 * for someone who asked for none. The preference is branched on here instead,
 * at the one place that writes the style.
 *
 * Reduced motion has no transition to arm, so the fill can only move when the
 * caller re-renders it: both callers already tick once a second (or faster) to
 * redraw their label, and they pass the live fraction with it.
 */
describe('useDrainingScaleXFill under prefers-reduced-motion', () => {
  beforeEach(() => {
    motionPreference.reduced = true;
  });

  it('renders the caller fraction with no transition, and never arms one', () => {
    const target = Date.now() + 10_000;
    const { result } = renderHook(() => useDrainingScaleXFill(target, 1));

    expect(result.current.transform).toBe('scaleX(1)');
    expect(result.current.transitionDuration).toBeUndefined();

    // The frames that would arm the transition under full motion.
    armFrames();

    expect(result.current.transform).toBe('scaleX(1)');
    expect(result.current.transitionProperty).toBeUndefined();
    expect(result.current.transitionDuration).toBeUndefined();
    expect(result.current.transitionTimingFunction).toBeUndefined();
  });

  it('steps to whatever fraction the caller passes on its next tick', () => {
    const target = Date.now() + 10_000;
    const { result, rerender } = renderHook(
      ({ fraction }) => useDrainingScaleXFill(target, fraction),
      { initialProps: { fraction: 1 } },
    );
    armFrames();

    rerender({ fraction: 0.7 });
    expect(result.current.transform).toBe('scaleX(0.7)');
    expect(result.current.transitionDuration).toBeUndefined();

    rerender({ fraction: 0.3 });
    expect(result.current.transform).toBe('scaleX(0.3)');
  });

  it('still arms the transition for someone who did NOT ask for less motion', () => {
    motionPreference.reduced = false;
    const target = Date.now() + 4_000;
    const { result } = renderHook(() => useDrainingScaleXFill(target, 1));
    armFrames();
    expect(result.current.transform).toBe('scaleX(0)');
    expect(result.current.transitionDuration).toBe('4000ms');
  });
});
