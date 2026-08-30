/**
 * S6-01, S6-02, S6-03, S6-05 - the grace window from the caller's side.
 *
 * The hook has four transitions and each one is something the reader sees: the
 * click parks the action and the countdown appears; Cancel withdraws it and says
 * nothing was applied; the window closes and the record is gone; the window
 * closes and the handler FAILED, which must read as a failure rather than as a
 * success, because a countdown that simply disappears looks exactly like one.
 *
 * The fourth is the one worth the file: a failure toasts the reason and does NOT
 * navigate. A record page that returned to the list on a failed delete would
 * leave the reader believing a record was removed that is still there.
 *
 * `current` answers per RECORD, so the two keys a delivery order carries (delete
 * and set_status) are told apart here as well - each surface shows only its own.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const showToast = vi.fn((..._args: unknown[]) => 'toast-1');
const dismissToast = vi.fn();
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: (...args: unknown[]) => showToast(...args),
  dismissDeferredToast: (...args: unknown[]) => dismissToast(...args),
}));

const createPendingAction = vi.fn();
const cancelPendingAction = vi.fn();
const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: (...args: unknown[]) => cancelPendingAction(...args),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
}));

import { useDeferredAction } from './useDeferredAction';
import { pendingEntityKey, pendingEntityStore } from '@/lib/pending-entity-store';

const PARKED = {
  id: 'pa-1',
  action_key: 'product.delete',
  entity_type: 'product',
  entity_id: 'p-1',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
};

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function renderDeletion(overrides: Record<string, unknown> = {}) {
  return renderHook(
    () =>
      useDeferredAction({
        actionKey: 'product.delete',
        entityType: 'product',
        entityId: 'p-1',
        verb: 'Deleting',
        subject: 'Ergonomic Chair',
        surface: 'inline',
        watchFromMount: true,
        successMessage: 'Product deleted',
        invalidateKeys: [['products']],
        ...overrides,
      }),
    { wrapper },
  );
}

/** What the next read of `current` will answer. */
function serverSays(pending: unknown, lastOutcome: unknown = null) {
  getCurrentPendingAction.mockResolvedValue({
    pending,
    last_outcome: lastOutcome,
  });
}

async function refetchCurrent() {
  await act(async () => {
    await queryClient.refetchQueries({ queryKey: ['pending-action-current'] });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  pendingEntityStore.clear('product', 'p-1');
  pendingEntityStore.clear('order', 'o-1');
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  createPendingAction.mockResolvedValue(PARKED);
  cancelPendingAction.mockResolvedValue(undefined);
  serverSays(null);
});

afterEach(() => {
  queryClient.clear();
});

describe('start (S6-01)', () => {
  it('parks the action on the server and shows the countdown before the next read', async () => {
    const { result } = renderDeletion();

    await act(async () => {
      result.current.start();
    });

    expect(createPendingAction).toHaveBeenCalledWith({
      actionKey: 'product.delete',
      entityType: 'product',
      entityId: 'p-1',
      payload: undefined,
    });
    await waitFor(() => expect(result.current.pending?.id).toBe('pa-1'));
    expect(result.current.isPending).toBe(true);
    // The row dims from the same click, so the reader can see WHICH record.
    expect(pendingEntityStore.getKeys().has(pendingEntityKey('product', 'p-1'))).toBe(
      true,
    );
  });

  it('a per-click payload overrides the standing one', async () => {
    const { result } = renderDeletion({
      actionKey: 'order.set_status',
      entityType: 'order',
      entityId: 'o-1',
      payload: { order_status_id: 'old' },
    });

    await act(async () => {
      result.current.start({ order_status_id: 'delivered' });
    });

    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({ payload: { order_status_id: 'delivered' } }),
    );
  });

  it('hands the countdown to a toast when the action came from a list row', async () => {
    const { result } = renderDeletion({ surface: 'toast', watchFromMount: false });

    await act(async () => {
      result.current.start();
    });

    await waitFor(() => expect(showToast).toHaveBeenCalledTimes(1));
    // Inline is the record page's answer; a row has nowhere to put one.
    expect(result.current.countdown).toBeNull();
  });
});

describe('cancel (S6-02)', () => {
  it('withdraws the parked action and says nothing was applied', async () => {
    const { result } = renderDeletion();
    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(result.current.pending?.id).toBe('pa-1'));

    await act(async () => {
      result.current.cancel();
    });

    await waitFor(() => expect(cancelPendingAction).toHaveBeenCalledWith('pa-1'));
    expect(toastSuccess).toHaveBeenCalledWith('Cancelled. Nothing was applied.');
    expect(toastError).not.toHaveBeenCalled();
  });
});

describe('commit and failure (S6-03)', () => {
  it('a committed action says so, refreshes the list and leaves the page', async () => {
    const onCommitted = vi.fn();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderDeletion({ onCommitted });
    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(result.current.pending?.id).toBe('pa-1'));

    serverSays(null, {
      id: 'pa-1',
      action_key: 'product.delete',
      status: 'committed',
      error_text: null,
      ended_at: '2026-08-30T10:00:10',
    });
    await refetchCurrent();

    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith('Product deleted', expect.anything()),
    );
    expect(onCommitted).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['products'] });
    expect(pendingEntityStore.getKeys().has(pendingEntityKey('product', 'p-1'))).toBe(
      false,
    );
  });

  it('a FAILED action toasts the reason and does not navigate', async () => {
    const onCommitted = vi.fn();
    const { result } = renderDeletion({ onCommitted });
    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(result.current.pending?.id).toBe('pa-1'));

    serverSays(null, {
      id: 'pa-1',
      action_key: 'product.delete',
      status: 'failed',
      error_text: 'The warehouse still holds stock for it',
      ended_at: '2026-08-30T10:00:10',
    });
    await refetchCurrent();

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'The warehouse still holds stock for it',
        expect.anything(),
      ),
    );
    // The record is still there, so the page it is on must stay open.
    expect(onCommitted).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a cancelled action toasts neither outcome a second time', async () => {
    const onCommitted = vi.fn();
    const { result } = renderDeletion({ onCommitted });
    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(result.current.pending?.id).toBe('pa-1'));

    serverSays(null, {
      id: 'pa-1',
      action_key: 'product.delete',
      status: 'cancelled',
      error_text: null,
      ended_at: '2026-08-30T10:00:03',
    });
    await refetchCurrent();

    await waitFor(() => expect(result.current.pending).toBeNull());
    // Cancel already said its piece where the click was.
    expect(toastSuccess).not.toHaveBeenCalledWith('Product deleted', expect.anything());
    expect(toastError).not.toHaveBeenCalled();
    expect(onCommitted).not.toHaveBeenCalled();
  });
});

describe('two actions on one record (S6-05)', () => {
  const otherKeyParked = {
    id: 'pa-9',
    action_key: 'order.delete',
    entity_type: 'order',
    entity_id: 'o-1',
    commit_at: '2026-08-30T10:00:10',
    window_seconds: 10,
  };

  function renderStatusChange() {
    return renderHook(
      () =>
        useDeferredAction({
          actionKey: 'order.set_status',
          entityType: 'order',
          entityId: 'o-1',
          verb: 'Updating',
          subject: 'DO-1',
          surface: 'inline',
          watchFromMount: true,
          successMessage: 'Delivery order updated',
        }),
      { wrapper },
    );
  }

  it('a countdown started by the OTHER key is not shown under this verb', async () => {
    serverSays(otherKeyParked);
    const { result } = renderStatusChange();

    await waitFor(() => expect(result.current.isBlocked).toBe(true));
    // The record holds one action; this surface is not the one running it.
    expect(result.current.pending).toBeNull();
    expect(result.current.countdown).toBeNull();
  });

  it('the outcome of the OTHER key does not toast here', async () => {
    serverSays(otherKeyParked);
    const { result } = renderStatusChange();
    await waitFor(() => expect(result.current.isBlocked).toBe(true));

    serverSays(null, {
      id: 'pa-9',
      action_key: 'order.delete',
      status: 'committed',
      error_text: null,
      ended_at: '2026-08-30T10:00:10',
    });
    await refetchCurrent();

    await waitFor(() => expect(result.current.isBlocked).toBe(false));
    expect(toastSuccess).not.toHaveBeenCalledWith(
      'Delivery order updated',
      expect.anything(),
    );
  });
});
