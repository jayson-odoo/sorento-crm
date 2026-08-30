/**
 * S6 feedback A + B - the follow-through, with nothing mounted.
 *
 * The bug this file exists for: a delete started from a list row, and the user
 * scrolls away, opens another module, comes back after the window. The hook that
 * started the action unmounted with it, so nobody ever asked the server what
 * happened, nobody invalidated the list, and the grid kept serving the deleted
 * row out of the React Query cache. Clicking it landed on a "not found" page.
 *
 * So the store carries the action instead of the component: one timer at the
 * server's `commit_at`, the same reconciliation on focus for a tab that was
 * asleep while the timer drifted, and an outcome that is only said out loud while
 * it still answers a click.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastDismiss = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    // The store takes a countdown toast down when its own action settles, whichever
    // record the surface that raised it has moved on to.
    dismiss: (...args: unknown[]) => toastDismiss(...args),
  },
}));

const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
}));

import {
  isOutcomeWorthSaying,
  pendingEntityKey,
  pendingEntityStore,
} from './pending-entity-store';

/** A naive-UTC timestamp `offsetMs` from now, the way the backend writes them. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

const invalidateQueries = vi.fn();
const fakeClient = { invalidateQueries } as unknown as Parameters<
  typeof pendingEntityStore.registerQueryClient
>[0];

function trackDelete(commitInMs = 5_000) {
  pendingEntityStore.track({
    id: 'pa-1',
    entityType: 'product',
    entityId: 'p-1',
    actionKey: 'product.delete',
    commitAt: serverTime(commitInMs),
    successMessage: 'Product deleted',
    invalidateKeys: [['products']],
  });
}

function committed(endedMsAgo = 0) {
  return {
    pending: null,
    last_outcome: {
      id: 'pa-1',
      action_key: 'product.delete',
      status: 'committed',
      error_text: null,
      ended_at: serverTime(-endedMsAgo),
    },
  };
}

/** Let the store's awaited read settle before asserting on what it did. */
async function flush() {
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(0);
}

beforeEach(() => {
  vi.clearAllMocks();
  pendingEntityStore.reset();
  pendingEntityStore.registerQueryClient(fakeClient);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  pendingEntityStore.reset();
});

describe('the follow-through with nothing mounted (S6 feedback A)', () => {
  it('marks the row, then asks the server once the window has lapsed', async () => {
    trackDelete(5_000);
    expect(pendingEntityStore.getKeys().has(pendingEntityKey('product', 'p-1'))).toBe(
      true,
    );
    getCurrentPendingAction.mockResolvedValue(committed());

    // Nothing is rendered: no hook, no poll, no list on screen.
    expect(getCurrentPendingAction).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(7_000);
    await flush();

    expect(getCurrentPendingAction).toHaveBeenCalledWith('product', 'p-1');
    // The list the action named is refetched, so the deleted row leaves the grid
    // without the user touching anything.
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['products'] });
    // And the row stops saying it is on its way out.
    expect(pendingEntityStore.getKeys().has(pendingEntityKey('product', 'p-1'))).toBe(
      false,
    );
    expect(toastSuccess).toHaveBeenCalledWith('Product deleted', expect.anything());
  });

  it('remembers the delete, so a link to the record can be quiet about it', async () => {
    trackDelete(1_000);
    getCurrentPendingAction.mockResolvedValue(committed());

    await vi.advanceTimersByTimeAsync(3_000);
    await flush();

    expect(pendingEntityStore.wasDeletedId('p-1')).toBe(true);
    expect(pendingEntityStore.wasDeletedId('p-2')).toBe(false);
  });

  it('a tab that was asleep reconciles on focus instead', async () => {
    trackDelete(1_000);
    getCurrentPendingAction.mockResolvedValue(committed());

    // The clock moves but the timer does not: that is a suspended tab, and it is
    // why the timer alone is not enough.
    vi.setSystemTime(new Date(Date.now() + 60_000));
    expect(getCurrentPendingAction).not.toHaveBeenCalled();

    pendingEntityStore.reconcileDue();
    await flush();

    expect(getCurrentPendingAction).toHaveBeenCalledTimes(1);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['products'] });
  });

  it('nothing is due before the window lapses', async () => {
    trackDelete(30_000);
    getCurrentPendingAction.mockResolvedValue(committed());

    pendingEntityStore.reconcileDue();
    await flush();

    // The action is still the user's to cancel; asking early would answer
    // "still pending" and cost a request per focus.
    expect(getCurrentPendingAction).not.toHaveBeenCalled();
  });

  it('an action still parked follows the server clock rather than giving up', async () => {
    trackDelete(1_000);
    getCurrentPendingAction.mockResolvedValueOnce({
      pending: {
        id: 'pa-1',
        action_key: 'product.delete',
        entity_type: 'product',
        entity_id: 'p-1',
        commit_at: serverTime(4_000),
        window_seconds: 10,
      },
      last_outcome: null,
    });
    getCurrentPendingAction.mockResolvedValue(committed());

    await vi.advanceTimersByTimeAsync(3_000);
    await flush();
    expect(invalidateQueries).not.toHaveBeenCalled();
    // The row stays dimmed while the action is still the server's.
    expect(pendingEntityStore.getKeys().has(pendingEntityKey('product', 'p-1'))).toBe(
      true,
    );

    await vi.advanceTimersByTimeAsync(6_000);
    await flush();
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['products'] });
  });

  it('a cancel puts the timer down with the dimming', async () => {
    trackDelete(1_000);
    getCurrentPendingAction.mockResolvedValue(committed());

    pendingEntityStore.clear('product', 'p-1');
    await vi.advanceTimersByTimeAsync(10_000);
    await flush();

    expect(getCurrentPendingAction).not.toHaveBeenCalled();
    expect(pendingEntityStore.getKeys().size).toBe(0);
  });

  it('a read that failed leaves the row alone and waits for the next wake', async () => {
    trackDelete(1_000);
    getCurrentPendingAction.mockRejectedValueOnce(new Error('offline'));

    await vi.advanceTimersByTimeAsync(3_000);
    await flush();

    expect(invalidateQueries).not.toHaveBeenCalled();
    expect(pendingEntityStore.getKeys().has(pendingEntityKey('product', 'p-1'))).toBe(
      true,
    );

    getCurrentPendingAction.mockResolvedValue(committed());
    pendingEntityStore.reconcileDue();
    await flush();
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['products'] });
  });
});

describe('what is worth saying (S6 feedback B)', () => {
  it('a fresh outcome is said and a forgotten one is not', () => {
    expect(
      isOutcomeWorthSaying({ status: 'committed', ended_at: serverTime(-2_000) }),
    ).toBe(true);
    expect(
      isOutcomeWorthSaying({ status: 'committed', ended_at: serverTime(-60_000) }),
    ).toBe(false);
  });

  it('a failure has a longer horizon, because nobody else will say it', () => {
    expect(
      isOutcomeWorthSaying({ status: 'failed', ended_at: serverTime(-30_000) }),
    ).toBe(true);
    expect(
      isOutcomeWorthSaying({ status: 'failed', ended_at: serverTime(-5 * 60_000) }),
    ).toBe(false);
  });

  it('one outcome is said once', () => {
    const outcome = {
      id: 'pa-7',
      action_key: 'product.delete',
      status: 'committed' as const,
      error_text: null,
      ended_at: serverTime(0),
    };

    pendingEntityStore.announceOutcome(outcome, 'Product deleted');
    pendingEntityStore.announceOutcome(outcome, 'Product deleted');

    expect(toastSuccess).toHaveBeenCalledTimes(1);
  });

  it('a commit the user has forgotten is not announced by the timer either', async () => {
    trackDelete(1_000);
    getCurrentPendingAction.mockResolvedValue(committed(5 * 60_000));

    await vi.advanceTimersByTimeAsync(3_000);
    await flush();

    // The list still refetches - the row has to go - but nothing is said.
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['products'] });
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
