/**
 * FontUploadDialog - the "Brand fonts" list (rename, delete) plus the upload
 * form (PLAN-brand-font-manage.md).
 *
 * Delete asks nothing (D7, S6): the trash parks a deferred action and becomes
 * a countdown with Cancel, never a confirmation dialog. What this file pins
 * at the DOM level is that the click parks the RIGHT key/entity with no
 * dialog in the way, that Cancel withdraws it, and that the row is removed
 * only once the server reports the delete committed - a failed commit (a
 * font still in use) is `useDeferredAction`'s own concern and is covered
 * there; this file only has to prove the row survives it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() },
}));

const createPendingAction = vi.fn();
const cancelPendingAction = vi.fn();
const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: (...args: unknown[]) => cancelPendingAction(...args),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
}));

const renameAsset = vi.fn();
const uploadAsset = vi.fn();
vi.mock('../../services/assetService', () => ({
  renameAsset: (...args: unknown[]) => renameAsset(...args),
  uploadAsset: (...args: unknown[]) => uploadAsset(...args),
}));

import { toast } from '@/lib/toast';
import { pendingEntityStore } from '@/lib/pending-entity-store';
import { FontUploadDialog } from './FontUploadDialog';
import type { KitAsset } from '../../services/assetService';

const mockToastError = vi.mocked(toast.error);

function font(overrides: Partial<KitAsset> & { id: string; name: string }): KitAsset {
  return {
    kind: 'font',
    tags: [],
    url: null,
    mime_type: null,
    ...overrides,
  };
}

/** A naive-UTC timestamp, the way the backend writes `commit_at`. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

function renderDialog(props: Partial<React.ComponentProps<typeof FontUploadDialog>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const defaults: React.ComponentProps<typeof FontUploadDialog> = {
    open: true,
    fonts: [],
    onCancel: vi.fn(),
    onUploaded: vi.fn(),
    onRenamed: vi.fn(),
    onDeleted: vi.fn(),
  };
  const merged = { ...defaults, ...props };
  const view = render(
    <QueryClientProvider client={client}>
      <FontUploadDialog {...merged} />
    </QueryClientProvider>,
  );
  return { ...view, client, props: merged };
}

beforeEach(() => {
  vi.clearAllMocks();
  pendingEntityStore.reset();
  getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});

describe('the list', () => {
  it('shows the empty state with no brand fonts', () => {
    renderDialog({ fonts: [] });
    expect(screen.getByText('No brand fonts yet')).toBeInTheDocument();
  });

  it('lists every font by name', () => {
    renderDialog({
      fonts: [
        font({ id: 'f-1', name: 'Sorento Display' }),
        font({ id: 'f-2', name: 'Sorento Body' }),
      ],
    });
    expect(screen.getByText('Sorento Display')).toBeInTheDocument();
    expect(screen.getByText('Sorento Body')).toBeInTheDocument();
  });
});

describe('rename', () => {
  it('saves on Enter and calls onRenamed with the old name', async () => {
    const onRenamed = vi.fn();
    renameAsset.mockResolvedValue(font({ id: 'f-1', name: 'Sorento Display Pro' }));
    renderDialog({
      fonts: [font({ id: 'f-1', name: 'Sorento Display' })],
      onRenamed,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Rename Sorento Display' }));
    const input = screen.getByDisplayValue('Sorento Display');
    fireEvent.change(input, { target: { value: 'Sorento Display Pro' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(renameAsset).toHaveBeenCalledWith('f-1', 'Sorento Display Pro'));
    await waitFor(() =>
      expect(onRenamed).toHaveBeenCalledWith(
        font({ id: 'f-1', name: 'Sorento Display Pro' }),
        'Sorento Display',
      ),
    );
  });

  it('Escape restores the old name without saving', () => {
    renderDialog({ fonts: [font({ id: 'f-1', name: 'Sorento Display' })] });

    fireEvent.click(screen.getByRole('button', { name: 'Rename Sorento Display' }));
    const input = screen.getByDisplayValue('Sorento Display');
    fireEvent.change(input, { target: { value: 'Something else' } });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(renameAsset).not.toHaveBeenCalled();
    expect(screen.getByText('Sorento Display')).toBeInTheDocument();
  });

  it('an empty name cannot be saved', () => {
    renderDialog({ fonts: [font({ id: 'f-1', name: 'Sorento Display' })] });

    fireEvent.click(screen.getByRole('button', { name: 'Rename Sorento Display' }));
    const input = screen.getByDisplayValue('Sorento Display');
    fireEvent.change(input, { target: { value: '   ' } });

    expect(screen.getByRole('button', { name: 'Save Sorento Display' })).toBeDisabled();
  });
});

describe('delete (D7 - deferred, no confirm dialog)', () => {
  it('parks the delete with no dialog in the way', async () => {
    createPendingAction.mockResolvedValue({
      id: 'pa-1',
      action_key: 'dealer_kit_asset.delete',
      entity_type: 'dealer_kit_asset',
      entity_id: 'f-1',
      commit_at: serverTime(10_000),
      window_seconds: 10,
    });
    renderDialog({ fonts: [font({ id: 'f-1', name: 'Sorento Display' })] });

    fireEvent.click(screen.getByRole('button', { name: 'Delete Sorento Display' }));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'dealer_kit_asset.delete',
          entityType: 'dealer_kit_asset',
          entityId: 'f-1',
        }),
      ),
    );
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });

  it('Cancel during the countdown keeps the row and calls nothing further', async () => {
    createPendingAction.mockResolvedValue({
      id: 'pa-1',
      action_key: 'dealer_kit_asset.delete',
      entity_type: 'dealer_kit_asset',
      entity_id: 'f-1',
      commit_at: serverTime(10_000),
      window_seconds: 10,
    });
    cancelPendingAction.mockResolvedValue(undefined);
    const onDeleted = vi.fn();
    renderDialog({ fonts: [font({ id: 'f-1', name: 'Sorento Display' })], onDeleted });

    fireEvent.click(screen.getByRole('button', { name: 'Delete Sorento Display' }));
    await waitFor(() => expect(createPendingAction).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(cancelPendingAction).toHaveBeenCalledWith('pa-1'));
    expect(onDeleted).not.toHaveBeenCalled();
    expect(screen.getByText('Sorento Display')).toBeInTheDocument();
  });

  it('the row is removed once the server commits the delete', async () => {
    createPendingAction.mockResolvedValue({
      id: 'pa-1',
      action_key: 'dealer_kit_asset.delete',
      entity_type: 'dealer_kit_asset',
      entity_id: 'f-1',
      commit_at: serverTime(10_000),
      window_seconds: 10,
    });
    const onDeleted = vi.fn();
    const { client } = renderDialog({
      fonts: [font({ id: 'f-1', name: 'Sorento Display' })],
      onDeleted,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Delete Sorento Display' }));
    await waitFor(() => expect(createPendingAction).toHaveBeenCalled());

    getCurrentPendingAction.mockResolvedValue({
      pending: null,
      last_outcome: {
        id: 'pa-1',
        action_key: 'dealer_kit_asset.delete',
        status: 'committed',
        error_text: null,
        ended_at: serverTime(0),
      },
    });
    await act(async () => {
      await client.refetchQueries({ queryKey: ['pending-action-current'] });
    });

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith('f-1'));
  });

  it('a font still in use fails at commit: the toast names it and the row stays', async () => {
    createPendingAction.mockResolvedValue({
      id: 'pa-1',
      action_key: 'dealer_kit_asset.delete',
      entity_type: 'dealer_kit_asset',
      entity_id: 'f-1',
      commit_at: serverTime(10_000),
      window_seconds: 10,
    });
    const onDeleted = vi.fn();
    const { client } = renderDialog({
      fonts: [font({ id: 'f-1', name: 'Sorento Display' })],
      onDeleted,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Delete Sorento Display' }));
    await waitFor(() => expect(createPendingAction).toHaveBeenCalled());

    getCurrentPendingAction.mockResolvedValue({
      pending: null,
      last_outcome: {
        id: 'pa-1',
        action_key: 'dealer_kit_asset.delete',
        status: 'failed',
        error_text: 'Still used by: Standard 70x38',
        ended_at: serverTime(0),
      },
    });
    await act(async () => {
      await client.refetchQueries({ queryKey: ['pending-action-current'] });
    });

    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith(
        'Still used by: Standard 70x38',
        expect.anything(),
      ),
    );
    expect(onDeleted).not.toHaveBeenCalled();
    expect(screen.getByText('Sorento Display')).toBeInTheDocument();
  });
});
