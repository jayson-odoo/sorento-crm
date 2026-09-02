/**
 * M3-01/M3-02 (`ui-motion-round2`) - the shared draining scaleX fill.
 */
import React, { type CSSProperties } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, renderHook } from '@testing-library/react';
import { useDrainingScaleXFill } from './useDrainingScaleXFill';

beforeEach(() => {
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
