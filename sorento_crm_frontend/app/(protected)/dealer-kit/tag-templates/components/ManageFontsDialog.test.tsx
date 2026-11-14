/**
 * SPEC-SHEET-PARITY-B2 v3 fix round, review S2: ONE Manage fonts dialog (the designer's
 * FontUploadDialog on the kit library) used by the template designer and the spec sheet, with the
 * rename step: a renamed family is handed back (old, new) so the open document(s) follow it.
 * Written test-FIRST.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));
const renameAsset = vi.fn();
vi.mock('../../services/assetService', () => ({
  renameAsset: (...args: unknown[]) => renameAsset(...args),
  uploadAsset: vi.fn(),
}));
const library = vi.hoisted(() => ({
  remember: vi.fn(),
  reload: vi.fn(async () => undefined),
  rename: vi.fn(),
  forget: vi.fn(),
}));
vi.mock('./useTagBindings', () => ({
  useKitLibrary: () => ({
    fonts: [{ id: 'f-1', name: 'Sorento Display', kind: 'font', tags: [], url: null, mime_type: null }],
    ...library,
  }),
}));

import { ManageFontsDialog } from './ManageFontsDialog';

describe('ManageFontsDialog (review S2)', () => {
  it('renaming a font updates the library and hands back old and new family names', async () => {
    const onFamilyRenamed = vi.fn();
    renameAsset.mockResolvedValue({ id: 'f-1', name: 'Sorento Display Pro', kind: 'font', tags: [], url: null, mime_type: null });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ManageFontsDialog open onClose={vi.fn()} onFamilyRenamed={onFamilyRenamed} />
      </QueryClientProvider>,
    );
    expect(screen.getByRole('dialog', { name: 'Brand fonts' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Rename Sorento Display' }));
    const input = screen.getByDisplayValue('Sorento Display');
    fireEvent.change(input, { target: { value: 'Sorento Display Pro' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(onFamilyRenamed).toHaveBeenCalledWith('Sorento Display', 'Sorento Display Pro'));
    expect(library.rename).toHaveBeenCalledWith('f-1', 'Sorento Display Pro');
  });
});
