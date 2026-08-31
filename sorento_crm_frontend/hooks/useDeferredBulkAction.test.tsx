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

/**
 * A selection can mix two entity kinds behind ONE countdown - `Set company`
 * running `attachment.set_company` on the files it touches and
 * `attachment_directory.set_company` on the folders, both parked by the same
 * `run()` call (PLAN-shared-brand-attachments R22). Each target can override
 * the hook's own `actionKey`/`entityType`; a target with neither uses the
 * hook's default.
 */
describe('bulk action with a per-target actionKey/entityType override', () => {
  function renderMixedBulk() {
    return renderHook(
      () =>
        useDeferredBulkAction({
          actionKey: 'attachment.set_company',
          entityType: 'attachment',
          verb: 'Setting company',
          pastVerb: 'updated',
          describe: (count) => `${count} item${count === 1 ? '' : 's'}`,
          invalidateKeys: [['drive-contents']],
        }),
      { wrapper },
    );
  }

  beforeEach(() => {
    createPendingAction.mockImplementation(
      async ({
        entityId,
        actionKey,
        entityType,
      }: {
        entityId: string;
        actionKey: string;
        entityType: string;
      }) => ({
        id: `pa-${entityId}`,
        action_key: actionKey,
        entity_type: entityType,
        entity_id: entityId,
        commit_at: serverTime(10_000),
        window_seconds: 10,
      }),
    );
  });

  it('a target with an override parks under ITS OWN actionKey/entityType, not the hook default', async () => {
    const { result } = renderMixedBulk();

    await act(async () => {
      result.current.run([
        { id: 'file-1' },
        {
          id: 'folder-1',
          actionKey: 'attachment_directory.set_company',
          entityType: 'attachment_directory',
        },
      ]);
    });

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(2));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: 'file-1',
        actionKey: 'attachment.set_company',
        entityType: 'attachment',
      }),
    );
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({
        entityId: 'folder-1',
        actionKey: 'attachment_directory.set_company',
        entityType: 'attachment_directory',
      }),
    );
    // The store dims each row under ITS OWN kind, so a folder row and a file
    // row with the same id would not collide.
    const keys = pendingEntityStore.getKeys();
    expect(keys.has(pendingEntityKey('attachment', 'file-1'))).toBe(true);
    expect(keys.has(pendingEntityKey('attachment_directory', 'folder-1'))).toBe(true);
  });

  it('the payload travels with the target, override or not', async () => {
    const { result } = renderMixedBulk();

    await act(async () => {
      result.current.run([
        { id: 'file-1', payload: { company_id: null } },
        {
          id: 'folder-1',
          payload: { company_id: null },
          actionKey: 'attachment_directory.set_company',
          entityType: 'attachment_directory',
        },
      ]);
    });

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(2));
    for (const call of createPendingAction.mock.calls) {
      expect(call[0].payload).toEqual({ company_id: null });
    }
  });
});

/**
 * `finishText` swaps the default noun-first template ("12 products deleted.")
 * for verb-first copy ("Company set: 3 folders, 12 files") - used wherever the
 * reader is better told what happened than what was acted upon.
 */
describe('bulk action with a finishText override', () => {
  function renderWithFinishText() {
    return renderHook(
      () =>
        useDeferredBulkAction({
          actionKey: 'attachment.set_company',
          entityType: 'attachment',
          verb: 'Setting company',
          pastVerb: 'updated',
          describe: (count) => `${count} file${count === 1 ? '' : 's'}`,
          finishText: {
            allCommitted: (count) => `Company set: ${count} files`,
            allFailed: (count) => `Could not set company for ${count} files.`,
            partial: (committed, failed) =>
              `Company set for ${committed} files; ${failed} could not be.`,
          },
        }),
      { wrapper },
    );
  }

  it('all committed reads the override, never the default noun-first template', async () => {
    createPendingAction.mockImplementation(async ({ entityId }: { entityId: string }) => ({
      id: `pa-${entityId}`,
      action_key: 'attachment.set_company',
      entity_type: 'attachment',
      entity_id: entityId,
      commit_at: serverTime(-2_000),
      window_seconds: 10,
    }));
    getCurrentPendingAction.mockResolvedValue({
      pending: null,
      last_outcome: {
        id: 'pa-f-1',
        action_key: 'attachment.set_company',
        status: 'committed',
        error_text: null,
        ended_at: serverTime(0),
      },
    });

    const { result } = renderWithFinishText();
    await act(async () => {
      result.current.run([{ id: 'f-1' }]);
    });
    await waitFor(() => expect(raised).toHaveLength(1));

    await act(async () => {
      pendingEntityStore.reconcileDue();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Company set: 1 files'));
  });

  it('a partial result reads the override, both numbers included', async () => {
    createPendingAction.mockImplementation(async ({ entityId }: { entityId: string }) => ({
      id: `pa-${entityId}`,
      action_key: 'attachment.set_company',
      entity_type: 'attachment',
      entity_id: entityId,
      commit_at: serverTime(-2_000),
      window_seconds: 10,
    }));
    getCurrentPendingAction.mockImplementation(async (_entityType: string, entityId: string) => ({
      pending: null,
      last_outcome: {
        id: `pa-${entityId}`,
        action_key: 'attachment.set_company',
        status: entityId === 'f-2' ? 'failed' : 'committed',
        error_text: entityId === 'f-2' ? 'Refused: the folder no longer exists.' : null,
        ended_at: serverTime(0),
      },
    }));

    const { result } = renderWithFinishText();
    await act(async () => {
      result.current.run([{ id: 'f-1' }, { id: 'f-2' }]);
    });
    await waitFor(() => expect(raised).toHaveLength(1));

    await act(async () => {
      pendingEntityStore.reconcileDue();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('Company set for 1 files; 1 could not be.'),
    );
  });
});
