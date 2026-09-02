import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { TakeoverCountdown } from './TakeoverCountdown';

/** Two frames, not a millisecond guess - the double rAF arms the fill's transition. */
function armFrames() {
  act(() => {
    vi.advanceTimersToNextFrame();
  });
  act(() => {
    vi.advanceTimersToNextFrame();
  });
}

/** `'scaleX(0.4)'` -> `0.4`. jsdom stores the inline style as a plain string;
 *  there is no CSS engine to interpolate it over time, so a test can only read
 *  the value the component SET, not a value a real browser's compositor would
 *  be mid-tween on - the interpolation itself is a browser/DevTools check. */
function scaleXOf(el: HTMLElement): number {
  const match = /scaleX\(([-\d.]+)\)/.exec(el.style.transform);
  if (!match) throw new Error(`not a scaleX transform: ${el.style.transform}`);
  return Number(match[1]);
}

describe('TakeoverCountdown', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('renders remaining time from commit_at (server time), depleting', () => {
    const commitAt = new Date(Date.now() + 60_000).toISOString();
    render(<TakeoverCountdown commitAt={commitAt} />);
    // ~1:00 remaining at mount
    expect(screen.getByTestId('takeover-remaining').textContent).toMatch(/0?1:0\d/);
    const bar = screen.getByTestId('takeover-bar') as HTMLElement;
    // Starts near full (M3-02): the fill's initial scaleX IS the remaining
    // fraction, painted before any transition runs.
    expect(scaleXOf(bar)).toBeGreaterThan(0.8);

    // Arms the fill's own CSS transition: drains to 0 over the remaining
    // window (a browser interpolates this; jsdom cannot, so the assertion is
    // on the transition's OWN parameters, not a mid-window snapshot).
    armFrames();
    expect(scaleXOf(bar)).toBe(0);
    expect(bar.style.transitionProperty).toBe('transform');
    expect(Number(bar.style.transitionDuration.replace('ms', ''))).toBeGreaterThan(58_000);
    expect(bar.style.transitionTimingFunction).toBe('linear');
  });

  it('treats a timezone-less (naive UTC) commit_at as UTC, not local', () => {
    // Backend sends naive UTC ISO (no Z). Build one 60s in the future in UTC.
    const naive = new Date(Date.now() + 60_000).toISOString().replace('Z', '');
    render(<TakeoverCountdown commitAt={naive} />);
    // Must NOT be instantly "Finalizing…" (the UTC+8 local-parse bug).
    expect(screen.getByTestId('takeover-remaining').textContent).not.toBe('Finalizing…');
    expect(scaleXOf(screen.getByTestId('takeover-bar') as HTMLElement)).toBeGreaterThan(0.5);
  });

  it('uses windowSeconds as a fixed denominator (remount-safe): late mount shows a short bar', () => {
    // Simulate a tab-switch remount: 60s window but only 6s remaining.
    const commitAt = new Date(Date.now() + 6_000).toISOString();
    render(<TakeoverCountdown commitAt={commitAt} windowSeconds={60} />);
    const bar = screen.getByTestId('takeover-bar') as HTMLElement;
    // ~6/60 ≈ 0.1 - NOT full (the bug showed 100%). This is the fill's
    // INITIAL scaleX, set before the arming transition even runs.
    expect(scaleXOf(bar)).toBeCloseTo(0.1, 1);
    expect(screen.getByTestId('takeover-remaining').textContent).toMatch(/0:0[56]/);
  });

  it('shows "Finalizing…" and fires onExpire once at zero', () => {
    const onExpire = vi.fn();
    const commitAt = new Date(Date.now() + 2_000).toISOString();
    render(<TakeoverCountdown commitAt={commitAt} onExpire={onExpire} />);

    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(screen.getByTestId('takeover-remaining').textContent).toBe('Finalizing…');
    expect(onExpire).toHaveBeenCalledTimes(1);
    // Finalizing flatlines the bar full grey rather than the transition's own
    // end value (scaleX(0), empty) - "the window is over" reads as a full
    // bar, not a vanished one.
    expect(scaleXOf(screen.getByTestId('takeover-bar') as HTMLElement)).toBe(1);

    // does not fire again on further ticks
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(onExpire).toHaveBeenCalledTimes(1);
  });

  it('animates transform only, keeps motion-reduce:transition-none (M3-02)', () => {
    const commitAt = new Date(Date.now() + 10_000).toISOString();
    render(<TakeoverCountdown commitAt={commitAt} />);
    const bar = screen.getByTestId('takeover-bar') as HTMLElement;
    expect(bar.className).toContain('motion-reduce:transition-none');
    expect(bar.style.width).toBe('');
  });
});
