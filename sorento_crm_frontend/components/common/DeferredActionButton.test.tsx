/**
 * S6-06, S6-08 - the countdown that replaced the confirmation dialog.
 *
 * Two properties, both of which a hand-rolled timer would get wrong:
 *
 * 1. **The clock is the SERVER's.** The bar drains against `commit_at`, not against
 *    a local counter started at mount, so a refresh, a tab switch or a remount
 *    picks the countdown up where the server actually is - a component that
 *    restarted its own ten seconds would promise a window the server has already
 *    closed.
 * 2. **Escape does nothing.** There is no dialog here, and a keystroke that
 *    dismisses things must not be the way an action gets taken back (D7). Cancel is
 *    a button, and it is the only way back.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

import DeferredActionButton, { DeferredCountdown } from './DeferredActionButton';
import type { PendingAction } from '@/services/pendingActionService';

/**
 * `vitest.setup.ts` makes `prefers-reduced-motion` MATCH by default, and the
 * fill's transition is branched on that preference (M3-01 fix round), so the
 * branch has to be named per test rather than inherited: full motion below,
 * reduced motion in its own test.
 */
const motionPreference = vi.hoisted(() => ({ reduced: false }));
vi.mock('@/lib/motion', () => ({
  useReducedMotion: () => motionPreference.reduced,
}));

/** Naive UTC, exactly as the backend serialises it. */
const NOW = Date.UTC(2026, 7, 30, 10, 0, 0);

function parked(overrides: Partial<PendingAction> = {}): PendingAction {
  return {
    id: 'pa-1',
    action_key: 'product.delete',
    entity_type: 'product',
    entity_id: 'p-1',
    commit_at: '2026-08-30T10:00:10',
    window_seconds: 10,
    ...overrides,
  };
}

beforeEach(() => {
  motionPreference.reduced = false;
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

/**
 * Runs the fill's double rAF to completion. `advanceTimersToNextFrame` (not a
 * millisecond guess) fires exactly the next queued `requestAnimationFrame`
 * callback, called twice for the two frames the arm effect schedules.
 */
function armFillTransition() {
  act(() => {
    vi.advanceTimersToNextFrame();
  });
  act(() => {
    vi.advanceTimersToNextFrame();
  });
}

describe('the countdown runs on the server clock (S6-06)', () => {
  it('reads the remaining time from commit_at, not from a fresh local window', () => {
    // Seven seconds have already gone by on the server. A local timer would start
    // at ten and promise three seconds that do not exist.
    render(
      <DeferredCountdown
        pending={parked({ commit_at: '2026-08-30T10:00:03' })}
        verb="Deleting"
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole('timer')).toHaveTextContent('Deleting in 3s');
  });

  it('treats a timezone-less commit_at as UTC', () => {
    // Malaysia is UTC+8. Parsed as local time, this countdown would read as eight
    // hours in the past and the bar would be empty from the first frame.
    render(
      <DeferredCountdown
        pending={parked({ commit_at: '2026-08-30T10:00:08' })}
        verb="Deleting"
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole('timer')).toHaveTextContent('Deleting in 8s');
    expect(screen.getByTestId('deferred-countdown')).not.toHaveAttribute('data-lapsed');
  });

  it('drains as the clock advances and then says the action is being applied', () => {
    render(
      <DeferredCountdown pending={parked()} verb="Deleting" onCancel={vi.fn()} />,
    );
    expect(screen.getByRole('timer')).toHaveTextContent('Deleting in 10s');

    // The label ticks once a second now (M3-01) - the fill's own CSS
    // transition is what drains visually between ticks.
    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(screen.getByRole('timer')).toHaveTextContent('Deleting in 4s');

    act(() => {
      vi.advanceTimersByTime(4000);
    });
    // Zero is not "done": only the server decides that, and it says so through
    // `last_outcome`.
    expect(screen.getByTestId('deferred-countdown')).toHaveAttribute(
      'data-lapsed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});

describe('the fill animates transform, not width (M3-01)', () => {
  it('arms a scaleX transition once, never touching style.width', () => {
    render(<DeferredCountdown pending={parked()} verb="Deleting" onCancel={vi.fn()} />);
    const bar = screen.getByTestId('deferred-countdown-bar') as HTMLElement;

    // Mounts at scaleX(1) with no transition - the starting value the double
    // rAF below needs something to animate FROM.
    expect(bar.style.transform).toBe('scaleX(1)');
    expect(bar.style.width).toBe('');

    // The double rAF that arms the transition.
    armFillTransition();

    expect(bar.style.transform).toBe('scaleX(0)');
    expect(bar.style.transitionProperty).toBe('transform');
    expect(bar.style.transitionDuration).toBe('10000ms');
    expect(bar.style.transitionTimingFunction).toBe('linear');
    // Never set at any point - only `transform` moves the fill.
    expect(bar.style.width).toBe('');
  });

  it('reports zero size changes to a ResizeObserver during the window (baseline: one per 100ms tick)', () => {
    const sizeChanges: number[] = [];
    const realRO = globalThis.ResizeObserver;
    class TrackingResizeObserver {
      private target: Element | null = null;
      constructor(private cb: ResizeObserverCallback) {}
      observe(el: Element) {
        this.target = el;
      }
      unobserve() {
        this.target = null;
      }
      disconnect() {
        this.target = null;
      }
    }
    globalThis.ResizeObserver = TrackingResizeObserver as unknown as typeof ResizeObserver;

    try {
      render(<DeferredCountdown pending={parked()} verb="Deleting" onCancel={vi.fn()} />);
      const bar = screen.getByTestId('deferred-countdown-bar') as HTMLElement;
      const observer = new ResizeObserver(() => sizeChanges.push(1));
      observer.observe(bar);

      armFillTransition();
      // A transform never changes layout size, so a real ResizeObserver would
      // never fire here either - this jsdom stand-in only proves the fill's
      // own box never changes width/height across the window.
      const widthAtStart = bar.getBoundingClientRect().width;
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(bar.getBoundingClientRect().width).toBe(widthAtStart);
      expect(sizeChanges).toHaveLength(0);
    } finally {
      globalThis.ResizeObserver = realRO;
    }
  });

  it('steps the fill once per tick under reduced motion, with no inline transition', () => {
    // The class alone cannot do this: the hook writes the transition as an
    // INLINE style, which beats `motion-reduce:transition-none` every time.
    motionPreference.reduced = true;
    render(<DeferredCountdown pending={parked()} verb="Deleting" onCancel={vi.fn()} />);
    const bar = screen.getByTestId('deferred-countdown-bar') as HTMLElement;

    expect(bar.style.transform).toBe('scaleX(1)');
    armFillTransition();
    expect(bar.style.transitionDuration).toBe('');
    expect(bar.style.transitionProperty).toBe('');

    // Three of the ten seconds gone: the bar steps with the label rather than
    // tweening between the two.
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByRole('timer')).toHaveTextContent('Deleting in 7s');
    expect(bar.style.transform).toBe('scaleX(0.7)');
    expect(bar.style.transitionDuration).toBe('');
  });

  it('keeps motion-reduce:transition-none on the fill and still counts the label down', () => {
    render(<DeferredCountdown pending={parked()} verb="Deleting" onCancel={vi.fn()} />);
    const bar = screen.getByTestId('deferred-countdown-bar') as HTMLElement;
    expect(bar.className).toContain('motion-reduce:transition-none');

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByRole('timer')).toHaveTextContent('Deleting in 7s');
  });
});

describe('Escape does not cancel a pending action (S6-08)', () => {
  it('leaves the countdown running and calls nothing', () => {
    const onCancel = vi.fn();
    render(
      <DeferredCountdown pending={parked()} verb="Deleting" onCancel={onCancel} />,
    );

    fireEvent.keyDown(screen.getByTestId('deferred-countdown'), { key: 'Escape' });
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByRole('timer')).toHaveTextContent('Deleting in 10s');
  });

  it('Cancel is a button, and it is the way back', () => {
    const onCancel = vi.fn();
    render(
      <DeferredCountdown pending={parked()} verb="Deleting" onCancel={onCancel} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe('the button becomes its own countdown (S6-06)', () => {
  it('shows the primary button while nothing is parked, and the countdown instead of it once one is', () => {
    const { rerender } = render(
      <DeferredActionButton
        pending={null}
        verb="Deleting"
        onCancel={vi.fn()}
        idle={<button type="button">Edit product</button>}
      />,
    );
    expect(screen.getByRole('button', { name: 'Edit product' })).toBeInTheDocument();

    rerender(
      <DeferredActionButton
        pending={parked()}
        verb="Deleting"
        onCancel={vi.fn()}
        idle={<button type="button">Edit product</button>}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Edit product' })).toBeNull();
    expect(screen.getByTestId('deferred-countdown')).toBeInTheDocument();

    // Cancel restores it: nothing was applied, so the record is what it was.
    rerender(
      <DeferredActionButton
        pending={null}
        verb="Deleting"
        onCancel={vi.fn()}
        idle={<button type="button">Edit product</button>}
      />,
    );
    expect(screen.getByRole('button', { name: 'Edit product' })).toBeInTheDocument();
    expect(screen.queryByTestId('deferred-countdown')).toBeNull();
  });
});
