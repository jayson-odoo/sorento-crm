import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { TakeoverCountdown } from './TakeoverCountdown';

describe('TakeoverCountdown', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('renders remaining time from commit_at (server time), depleting', () => {
    const commitAt = new Date(Date.now() + 60_000).toISOString();
    render(<TakeoverCountdown commitAt={commitAt} />);
    // ~1:00 remaining at mount
    expect(screen.getByTestId('takeover-remaining').textContent).toMatch(/0?1:0\d/);
    const bar = screen.getByTestId('takeover-bar') as HTMLElement;
    expect(parseFloat(bar.style.width)).toBeGreaterThan(80);

    // advance 30s → bar depletes toward half
    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    expect(parseFloat(bar.style.width)).toBeLessThan(60);
  });

  it('treats a timezone-less (naive UTC) commit_at as UTC, not local', () => {
    // Backend sends naive UTC ISO (no Z). Build one 60s in the future in UTC.
    const naive = new Date(Date.now() + 60_000).toISOString().replace('Z', '');
    render(<TakeoverCountdown commitAt={naive} />);
    // Must NOT be instantly "Finalizing…" (the UTC+8 local-parse bug).
    expect(screen.getByTestId('takeover-remaining').textContent).not.toBe('Finalizing…');
    expect(parseFloat((screen.getByTestId('takeover-bar') as HTMLElement).style.width)).toBeGreaterThan(50);
  });

  it('uses windowSeconds as a fixed denominator (remount-safe): late mount shows a short bar', () => {
    // Simulate a tab-switch remount: 60s window but only 6s remaining.
    const commitAt = new Date(Date.now() + 6_000).toISOString();
    render(<TakeoverCountdown commitAt={commitAt} windowSeconds={60} />);
    const bar = screen.getByTestId('takeover-bar') as HTMLElement;
    // ~6/60 ≈ 10% - NOT full (the bug showed 100%).
    expect(parseFloat(bar.style.width)).toBeLessThan(20);
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

    // does not fire again on further ticks
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(onExpire).toHaveBeenCalledTimes(1);
  });
});
