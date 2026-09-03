/**
 * SetCompanyDialog - the ONE dialog for `Set company…` (AC-F4, AC-F4b).
 *
 * The dialog never calls the backend itself; `Apply` starts one deferred
 * action per selected file/folder through the shipped grace-window engine
 * (`useDeferredBulkAction`, not mocked here - the pending/commit toast text
 * is the hook's, and a mock would just assert the mock). Only the engine's
 * own transport - `pendingActionService` and `deferredToast` - is mocked, the
 * same seam `hooks/useDeferredBulkAction.test.tsx` uses.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    dismiss: vi.fn(),
  },
}));

const raised: { id?: string; subject: string; verb?: string; onCancel: () => void }[] = [];
const dismissDeferredToast = vi.fn();
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: (input: {
    id?: string;
    subject: string;
    verb?: string;
    onCancel: () => void;
  }) => {
    raised.push(input);
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

vi.mock('@/app/providers/CompanyProvider', () => ({
  useCompany: () => ({
    grants: [
      { id: 'company-s', name: 'Sorento' },
      { id: 'company-m', name: 'Mocha' },
    ],
  }),
}));

import SetCompanyDialog from './SetCompanyDialog';
import { pendingEntityStore } from '@/lib/pending-entity-store';

/** A naive-UTC timestamp `offsetMs` from now, the way the backend writes them. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function renderDialog(props: Partial<React.ComponentProps<typeof SetCompanyDialog>> = {}) {
  const onOpenChange = vi.fn();
  const utils = render(
    <SetCompanyDialog
      open
      onOpenChange={onOpenChange}
      fileIds={['f-1']}
      folderIds={[]}
      {...props}
    />,
    { wrapper },
  );
  return { onOpenChange, ...utils };
}

const trigger = () =>
  document.querySelector('[data-slot="searchable-select-trigger"]') as HTMLElement;

/** Opens the picker and selects the option with this label. */
async function pick(label: string) {
  fireEvent.click(trigger());
  const option = await screen.findByRole('option', { name: label });
  fireEvent.click(option);
  await waitFor(() => expect(document.querySelector('[role="listbox"]')).toBeNull());
}

beforeEach(() => {
  vi.clearAllMocks();
  raised.length = 0;
  pendingEntityStore.reset();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  createPendingAction.mockImplementation(
    async ({
      actionKey,
      entityType,
      entityId,
    }: {
      actionKey: string;
      entityType: string;
      entityId: string;
    }) => ({
      id: `pa-${entityId}`,
      action_key: actionKey,
      entity_type: entityType,
      entity_id: entityId,
      commit_at: serverTime(10_000),
      window_seconds: 10,
    }),
  );
  cancelPendingAction.mockResolvedValue(undefined);
  getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

afterEach(() => {
  queryClient.clear();
});

describe('SetCompanyDialog', () => {
  it('AC-F4: focuses the picker as soon as it opens', async () => {
    renderDialog();
    await waitFor(() => expect(document.activeElement).toBe(trigger()));
  });

  it('AC-F4: the selection count reads in the reader\'s words', () => {
    renderDialog({
      fileIds: Array.from({ length: 12 }, (_, i) => `f-${i}`),
      folderIds: Array.from({ length: 3 }, (_, i) => `d-${i}`),
    });
    expect(screen.getByText('3 folders, 12 files')).toBeInTheDocument();
  });

  it('AC-F4: Enter, with a value chosen, applies the same as clicking Apply', async () => {
    renderDialog({ fileIds: ['f-1'], folderIds: [] });
    await pick('Sorento');
    fireEvent.keyDown(trigger(), { key: 'Enter' });
    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({ payload: { company_id: 'company-s' } }),
    );
  });

  it('AC-F4: Escape closes the dialog without applying', async () => {
    const { onOpenChange } = renderDialog();
    await waitFor(() => expect(document.activeElement).toBe(trigger()));
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
      code: 'Escape',
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(createPendingAction).not.toHaveBeenCalled();
  });

  it('AC-F4: Apply parks attachment.set_company for files and attachment_directory.set_company for folders, {company_id: null} for Shared', async () => {
    const { onOpenChange } = renderDialog({ fileIds: ['f-1', 'f-2'], folderIds: ['d-1'] });
    await pick('Shared');
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(3));
    const calls = createPendingAction.mock.calls.map((c) => c[0]);
    expect(
      calls.filter(
        (c) =>
          c.actionKey === 'attachment.set_company' &&
          c.entityType === 'attachment' &&
          c.payload?.company_id === null,
      ),
    ).toHaveLength(2);
    expect(
      calls.filter(
        (c) =>
          c.actionKey === 'attachment_directory.set_company' &&
          c.entityType === 'attachment_directory' &&
          c.payload?.company_id === null,
      ),
    ).toHaveLength(1);
    // Apply closes the dialog immediately (R22) - the countdown, not a modal, owns the wait.
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('AC-F4: re-picking inside the popover does not apply the OLD value (review defect on PR #442)', async () => {
    // cmdk's own Command.Input also renders role="combobox" (parity with Radix's
    // SelectTrigger), so a guard keyed on role alone matches the search input
    // too: reopening the picker after a first pick, narrowing by typing, and
    // pressing Enter ran handleApply() with the STALE pre-typing value instead
    // of reaching cmdk's own Enter handling.
    renderDialog({ fileIds: ['f-1'], folderIds: [] });
    await pick('Sorento');

    fireEvent.click(trigger());
    const searchInput = await screen.findByPlaceholderText('Search...');
    fireEvent.change(searchInput, { target: { value: 'Mocha' } });
    await screen.findByRole('option', { name: 'Mocha' });

    // Enter inside the open popover reaches cmdk's own handling (it picks the
    // highlighted "Mocha" row and closes) - it must NOT also run our Apply
    // with the value from before the popover reopened.
    fireEvent.keyDown(searchInput, { key: 'Enter' });
    await waitFor(() => expect(document.querySelector('[role="listbox"]')).toBeNull());
    expect(createPendingAction).not.toHaveBeenCalled();

    // Radix returns focus to the (now closed) trigger on close - the same
    // Enter-applies affordance from the first test, now carrying the value
    // just picked by typing.
    await waitFor(() => expect(document.activeElement).toBe(trigger()));
    fireEvent.keyDown(trigger(), { key: 'Enter' });

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({ payload: { company_id: 'company-m' } }),
    );
  });

  it('AC-F4b: the pending toast names the selection and commit reads "Company set: …"', async () => {
    // Parked with the window already behind them, so the store's reconcile
    // asks the server straight away rather than the test waiting out five
    // real seconds.
    createPendingAction.mockImplementation(
      async ({
        actionKey,
        entityType,
        entityId,
      }: {
        actionKey: string;
        entityType: string;
        entityId: string;
      }) => ({
        id: `pa-${entityId}`,
        action_key: actionKey,
        entity_type: entityType,
        entity_id: entityId,
        commit_at: serverTime(-2_000),
        window_seconds: 10,
      }),
    );
    renderDialog({ fileIds: ['f-1'], folderIds: ['d-1'] });
    await pick('Sorento');
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(raised).toHaveLength(1));
    expect(raised[0].verb).toBe('Setting company');
    expect(raised[0].subject).toBe('1 folder, 1 file');

    // The outcome's action_key has to echo back the entity's OWN action key -
    // a mismatch (the store's guard against a stale read) reads as unsettled,
    // not committed - so the file and the folder each get their own.
    getCurrentPendingAction.mockImplementation(async (entityType: string, entityId: string) => ({
      pending: null,
      last_outcome: {
        id: `pa-${entityId}`,
        action_key:
          entityType === 'attachment' ? 'attachment.set_company' : 'attachment_directory.set_company',
        status: 'committed',
        error_text: null,
        ended_at: serverTime(0),
      },
    }));
    await act(async () => {
      pendingEntityStore.reconcileDue();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith('Company set: 1 folder, 1 file'),
    );
  });
});
