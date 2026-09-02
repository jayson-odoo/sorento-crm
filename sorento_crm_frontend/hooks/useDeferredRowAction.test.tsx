/**
 * S6-07 - the grace window started from a LIST ROW, twice in a row.
 *
 * One hook serves every row of a list: the record is whichever row was just pressed,
 * so a second delete re-points the same hook at another record. Nothing about the FIRST
 * action ended when that happened, and this file is what says so - because the shape
 * that reads as "ended" from inside the hook (`pending` going null) is exactly the shape
 * a re-point produces, and the first version of it dismissed row A's countdown, and its
 * Cancel with it, the moment row B was pressed. The window was still open; the reader
 * simply had no way back into it.
 *
 * So: two rows deleted in quick succession keep two live countdowns, each cancelling its
 * own action, and each row stays dimmed until its own window lapses.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastDismiss = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    dismiss: (...args: unknown[]) => toastDismiss(...args),
  },
}));

/** Every countdown toast raised, in order, with the Cancel it was given. */
const raised: { id: string; subject: string; onCancel: () => void }[] = [];
const dismissDeferredToast = vi.fn();
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: (input: { pending: { id: string }; subject: string; onCancel: () => void }) => {
    raised.push({
      id: input.pending.id,
      subject: input.subject,
      onCancel: input.onCancel,
    });
    return `pending-action-${input.pending.id}`;
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

import { useDeferredRowAction } from './useDeferredRowAction';
import { pendingEntityKey, pendingEntityStore } from '@/lib/pending-entity-store';

/** A naive-UTC timestamp `offsetMs` from now, the way the backend writes them. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

function parked(actionId: string, entityId: string) {
  return {
    id: actionId,
    action_key: 'brand.delete',
    entity_type: 'brand',
    entity_id: entityId,
    commit_at: serverTime(10_000),
    window_seconds: 10,
  };
}

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function renderRowDeletion() {
  return renderHook(
    () =>
      useDeferredRowAction({
        actionKey: 'brand.delete',
        entityType: 'brand',
        successMessage: 'Brand deleted',
        invalidateKeys: [['brands']],
      }),
    { wrapper },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  raised.length = 0;
  // Module-level state is per TAB, and each test is a fresh tab.
  pendingEntityStore.reset();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  // The server holds one parked action per RECORD, and answers `current` per record.
  // Standing in for it rather than answering "nothing is parked" to everything, because
  // the poll's answer is what tells the hook an action ENDED - and a mock that always
  // says nothing is parked ends every action a millisecond after it starts.
  const server = new Map<string, ReturnType<typeof parked>>();
  createPendingAction.mockImplementation(async ({ entityId }: { entityId: string }) => {
    const action = parked(`pa-${entityId}`, entityId);
    server.set(entityId, action);
    return action;
  });
  cancelPendingAction.mockImplementation(async (id: string) => {
    for (const [entityId, action] of server) {
      if (action.id === id) server.delete(entityId);
    }
  });
  getCurrentPendingAction.mockImplementation(
    async (_entityType: string, entityId: string) => ({
      pending: server.get(entityId) ?? null,
      last_outcome: null,
    }),
  );
});

afterEach(() => {
  queryClient.clear();
});

describe('two rows deleted in quick succession', () => {
  it('keeps both countdowns alive, and dims both rows', async () => {
    const { result } = renderRowDeletion();

    await act(async () => {
      result.current.run({ id: 'brand-a', subject: 'Acme' });
    });
    await waitFor(() => expect(raised).toHaveLength(1));

    await act(async () => {
      result.current.run({ id: 'brand-b', subject: 'Beta' });
    });
    await waitFor(() => expect(raised).toHaveLength(2));

    expect(raised.map((t) => t.subject)).toEqual(['Acme', 'Beta']);
    // The first countdown is still on screen: its window is open and its Cancel is the
    // only way back into it.
    expect(dismissDeferredToast).not.toHaveBeenCalledWith('pending-action-pa-brand-a');
    expect(toastDismiss).not.toHaveBeenCalledWith('pending-action-pa-brand-a');

    const keys = pendingEntityStore.getKeys();
    expect(keys.has(pendingEntityKey('brand', 'brand-a'))).toBe(true);
    expect(keys.has(pendingEntityKey('brand', 'brand-b'))).toBe(true);
  });

  it("the first toast's Cancel withdraws the FIRST action, not the one on screen", async () => {
    const { result } = renderRowDeletion();

    await act(async () => {
      result.current.run({ id: 'brand-a', subject: 'Acme' });
    });
    await waitFor(() => expect(raised).toHaveLength(1));
    await act(async () => {
      result.current.run({ id: 'brand-b', subject: 'Beta' });
    });
    await waitFor(() => expect(raised).toHaveLength(2));

    await act(async () => {
      raised[0].onCancel();
    });

    await waitFor(() => expect(cancelPendingAction).toHaveBeenCalledWith('pa-brand-a'));
    // Only that row is released: the second is still counting down.
    await waitFor(() =>
      expect(pendingEntityStore.getKeys().has(pendingEntityKey('brand', 'brand-a'))).toBe(
        false,
      ),
    );
    expect(
      pendingEntityStore.getKeys().has(pendingEntityKey('brand', 'brand-b')),
    ).toBe(true);
    expect(toastDismiss).toHaveBeenCalledWith('pending-action-pa-brand-a');
  });
});
