/**
 * CONTACT-DELETE-FK: bulk delete deletes what it can and reports the rest per contact.
 * A contact with linked history comes back in `blocked` ({id, name, reason}); the dialog
 * names each one in an error toast instead of a success toast.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', () => api);
const toastMock = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/toast', () => toastMock);

import ContactBulkDeleteDialog from './ContactBulkDeleteDialog';

const ok = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ContactBulkDeleteDialog open onOpenChange={vi.fn()} contactIds={['c1', 'c2']} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Delete 2 contacts' }));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ContactBulkDeleteDialog blocked contacts', () => {
  it('names each contact that was not deleted and why', async () => {
    api.apiFetch.mockResolvedValue(
      ok({
        deleted_count: 1,
        blocked: [
          { id: 'c2', name: 'Bob', reason: 'This contact has 2 price tag requests; it cannot be deleted.' },
        ],
        message: 'Deleted 1 contact. 1 contact was not deleted because it has linked records.',
      }),
    );
    renderDialog();

    await waitFor(() => expect(toastMock.toast.error).toHaveBeenCalled());
    expect(toastMock.toast.error).toHaveBeenCalledWith(
      'Deleted 1 contact. 1 contact was not deleted because it has linked records.',
      expect.objectContaining({
        description: 'Bob: This contact has 2 price tag requests; it cannot be deleted.',
      }),
    );
    expect(toastMock.toast.success).not.toHaveBeenCalled();
  });

  it('keeps the success toast when nothing was blocked', async () => {
    api.apiFetch.mockResolvedValue(ok({ deleted_count: 2, blocked: [], message: 'Deleted 2 contacts.' }));
    renderDialog();

    await waitFor(() => expect(toastMock.toast.success).toHaveBeenCalledWith('Deleted 2 contacts.'));
    expect(toastMock.toast.error).not.toHaveBeenCalled();
  });
});
