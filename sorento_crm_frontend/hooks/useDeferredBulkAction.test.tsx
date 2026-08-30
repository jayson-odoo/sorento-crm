/**
 * S6-07, bulk - a selection deleted behind ONE countdown.
 *
 * The server holds one pending action per record, so a selection of twelve is twelve
 * parked actions. What the reader must not get is twelve countdowns: the batch is one
 * gesture and it is owed one countdown, one Cancel that withdraws all of them, and one
 * closing sentence. Every selected row still dims on its own, because the dimming comes
 * from the store and the store knows each record separately.
 *
 * The other half is the accounting: a record already counting down its own action is
 * refused (409), and a refusal that is silently swallowed leaves a row sitting on the
 * list looking untouched.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastDismiss = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    dismiss: (...args: unknown[]) => toastDismiss(...args),
  },
}));

const raised: { id?: string; subject: string; onCancel: () => void }[] = [];
const dismissDeferredToast = vi.fn();
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: (input: { id?: string; subject: string; onCancel: () => void }) => {
    raised.push({ id: input.id, subject: input.subject, onCancel: input.onCancel });
    return input.id ?? 'toast';
  },
  dismissDeferredToast: (...args: unknown[]) => dismissDeferredToast(...args),
}));

const createPendingAction = vi.fn();
const cancelPendingAction = vi.fn();
const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: (...args: unknown[]) => cancelPendingAction(...args),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
}));

import { useDeferredBulkAction } from './useDeferredBulkAction';
import { pendingEntityKey, pendingEntityStore } from '@/lib/pending-entity-store';

/** A naive-UTC timestamp `offsetMs` from now, the way the backend writes them. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const onStarted = vi.fn();

function renderBulkDeletion() {
  return renderHook(
    () =>
      useDeferredBulkAction({
        actionKey: 'product.delete',
        entityType: 'product',
        describe: (count) => `${count} product${count === 1 ? '' : 's'}`,
        invalidateKeys: [['products']],
        onStarted,
      }),
    { wrapper },
  );
}

const THREE = [{ id: 'p-1' }, { id: 'p-2' }, { id: 'p-3' }];

beforeEach(() => {
  vi.clearAllMocks();
  raised.length = 0;
  pendingEntityStore.reset();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  createPendingAction.mockImplementation(async ({ entityId }: { entityId: string }) => ({
    id: `pa-${entityId}`,
    action_key: 'product.delete',
    entity_type: 'product',
    entity_id: entityId,
    commit_at: serverTime(10_000),
    window_seconds: 10,
  }));
  cancelPendingAction.mockResolvedValue(undefined);
  getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

afterEach(() => {
  queryClient.clear();
});

describe('bulk delete', () => {
  it('parks one action per row and shows ONE countdown naming the selection', async () => {
    const { result } = renderBulkDeletion();

    await act(async () => {
      result.current.run(THREE);
    });

    await waitFor(() => expect(raised).toHaveLength(1));
    expect(createPendingAction).toHaveBeenCalledTimes(3);
    expect(raised[0].subject).toBe('3 products');
    // Every selected row dims, from the same store a single delete marks.
    const keys = pendingEntityStore.getKeys();
    for (const target of THREE) {
      expect(keys.has(pendingEntityKey('product', target.id))).toBe(true);
    }
    // The selection is dropped once the batch is parked, not before.
    expect(onStarted).toHaveBeenCalledTimes(1);
  });

  it('one Cancel withdraws every parked action and un-dims every row', async () => {
    const { result } = renderBulkDeletion();
    await act(async () => {
      result.current.run(THREE);
    });
    await waitFor(() => expect(raised).toHaveLength(1));

    await act(async () => {
      raised[0].onCancel();
    });

    await waitFor(() => expect(cancelPendingAction).toHaveBeenCalledTimes(3));
    expect(cancelPendingAction.mock.calls.map((c) => c[0]).sort()).toEqual([
      'pa-p-1',
      'pa-p-2',
      'pa-p-3',
    ]);
    await waitFor(() => expect(pendingEntityStore.getKeys().size).toBe(0));
    expect(toastSuccess).toHaveBeenCalledWith('Cancelled. Nothing was applied.');
  });

  it('a row that is already counting down is skipped, counted and named', async () => {
    createPendingAction.mockImplementation(async ({ entityId }: { entityId: string }) => {
      if (entityId === 'p-2') {
        throw new Error('Another action on this record is still counting down.');
      }
      return {
        id: `pa-${entityId}`,
        action_key: 'product.delete',
        entity_type: 'product',
        entity_id: entityId,
        commit_at: serverTime(10_000),
        window_seconds: 10,
      };
    });
    const { result } = renderBulkDeletion();

    await act(async () => {
      result.current.run(THREE);
    });

    await waitFor(() => expect(raised).toHaveLength(1));
    // The countdown covers what was actually parked, never the click's optimism.
    expect(raised[0].subject).toBe('2 products');
    expect(pendingEntityStore.getKeys().has(pendingEntityKey('product', 'p-2'))).toBe(
      false,
    );
  });

  it('says one closing sentence once every window has lapsed, failures included', async () => {
    // Parked with the window already behind them, so the store's reconcile asks the
    // server straight away rather than the test waiting out ten real seconds.
    createPendingAction.mockImplementation(async ({ entityId }: { entityId: string }) => ({
      id: `pa-${entityId}`,
      action_key: 'product.delete',
      entity_type: 'product',
      entity_id: entityId,
      commit_at: serverTime(-2_000),
      window_seconds: 10,
    }));
    const { result } = renderBulkDeletion();
    await act(async () => {
      result.current.run(THREE);
    });
    await waitFor(() => expect(raised).toHaveLength(1));

    // The store asks the server how each one ended; two applied, one was refused by a
    // foreign key. The reader is owed ONE sentence, and it has to carry both numbers.
    getCurrentPendingAction.mockImplementation(
      async (_entityType: string, entityId: string) => ({
        pending: null,
        last_outcome: {
          id: `pa-${entityId}`,
          action_key: 'product.delete',
          status: entityId === 'p-3' ? 'failed' : 'committed',
          error_text:
            entityId === 'p-3'
              ? 'Cannot delete this product: other records still reference it.'
              : null,
          ended_at: serverTime(0),
        },
      }),
    );

    await act(async () => {
      pendingEntityStore.reconcileDue();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('2 products deleted; 1 could not be.'),
    );
    // ONE sentence: no per-row success toast rides along with it.
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
