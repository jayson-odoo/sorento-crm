/**
 * M3-01/M3-02 (`ui-motion-round2`) - the shared draining scaleX fill.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useDrainingScaleXFill } from './useDrainingScaleXFill';

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(Date.UTC(2026, 7, 30, 10, 0, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

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
