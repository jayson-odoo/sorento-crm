/**
 * MessageSnippetsList - loading / empty / error / data + the CRUD affordances
 * (UAC AC-L4, slice S4.4). Product standard: DataGrid + search + Add, modal
 * create/edit, hard delete behind a confirmation.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// jsdom polyfills for ScrollArea / DataGrid.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/sla-management/message-snippets',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// DataGrid persists column prefs through this hook (it fires network) - stub it,
// or no rows render in jsdom.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

/* The grace window is the server's; what this file proves is that the row parks one. */
const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'message_snippet.delete',
  entity_type: 'message_snippet',
  entity_id: 's1',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const hooks = vi.hoisted(() => ({
  useMessageSnippets: vi.fn(),
  useCreateMessageSnippet: vi.fn(),
  useUpdateMessageSnippet: vi.fn(),
  useDeleteMessageSnippet: vi.fn(),
}));
vi.mock('../hooks/useMessageSnippets', () => hooks);

import MessageSnippetsList from './MessageSnippetsList';
import type { MessageSnippet } from '../types/messageSnippet.types';

function snippet(over: Partial<MessageSnippet> = {}): MessageSnippet {
  return {
    id: 's1',
    name: 'Stock check',
    shortcut: 'stock',
    body: 'Hi $contact_name, we are checking stock.',
    is_active: true,
    created_at: '2026-08-15T02:00:00',
    updated_at: null,
    ...over,
  };
}

function mockList(
  rows: MessageSnippet[],
  over: Partial<{ isLoading: boolean; isError: boolean; error: Error }> = {},
) {
  hooks.useMessageSnippets.mockReturnValue({
    data: over.isLoading || over.isError
      ? undefined
      : { data: rows, pagination: { total: rows.length, page: 1, limit: 10 }, empty: !rows.length },
    isLoading: !!over.isLoading,
    isError: !!over.isError,
    error: over.error ?? null,
  });
}

let createAsync: ReturnType<typeof vi.fn>;
let updateAsync: ReturnType<typeof vi.fn>;
let deleteAsync: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  createAsync = vi.fn().mockResolvedValue(snippet());
  updateAsync = vi.fn().mockResolvedValue(snippet());
  deleteAsync = vi.fn().mockResolvedValue(undefined);
  hooks.useCreateMessageSnippet.mockReturnValue({ mutateAsync: createAsync, isPending: false });
  hooks.useUpdateMessageSnippet.mockReturnValue({ mutateAsync: updateAsync, isPending: false });
  hooks.useDeleteMessageSnippet.mockReturnValue({ mutateAsync: deleteAsync, isPending: false });
  mockList([snippet()]);
});

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MessageSnippetsList />
    </QueryClientProvider>,
  );
}

describe('MessageSnippetsList', () => {
  it('renders the snippets with their shortcut and status', async () => {
    renderList();

    expect(await screen.findByText('Stock check')).toBeInTheDocument();
    expect(screen.getByText('/stock')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('shows the stored wording, tokens and all - this page is where they are edited', async () => {
    renderList();

    expect(
      await screen.findByText('Hi $contact_name, we are checking stock.'),
    ).toBeInTheDocument();
  });

  it('renders a loading state', () => {
    mockList([], { isLoading: true });
    renderList();

    expect(screen.queryByText('Stock check')).not.toBeInTheDocument();
  });

  it('renders an empty state that says what to do next', async () => {
    mockList([]);
    renderList();

    expect(
      await screen.findByText(/No snippets yet\. Add one and it appears in the ticket composer\./),
    ).toBeInTheDocument();
  });

  it('renders the error instead of an empty grid', async () => {
    mockList([], { isError: true, error: new Error('Failed to load message snippets') });
    renderList();

    expect(await screen.findByTestId('snippets-error')).toHaveTextContent(
      'Failed to load message snippets',
    );
  });

  it('opens the create modal from the toolbar', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: /add snippet/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Add snippet')).toBeInTheDocument();
  });

  it('creates a snippet from the modal', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: /add snippet/i }));
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Greeting' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Hi there' } });
    fireEvent.click(screen.getByRole('button', { name: /create snippet/i }));

    await waitFor(() =>
      expect(createAsync).toHaveBeenCalledWith({
        name: 'Greeting',
        shortcut: null,
        body: 'Hi there',
        is_active: true,
      }),
    );
  });

  it('refuses to save a snippet with no name or no message', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: /add snippet/i }));
    fireEvent.click(await screen.findByRole('button', { name: /create snippet/i }));

    expect(await screen.findByText('Give the snippet a name.')).toBeInTheDocument();
    expect(screen.getByText('A snippet needs some text.')).toBeInTheDocument();
    expect(createAsync).not.toHaveBeenCalled();
  });

  it('drops a variable into the message from the token buttons', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: /add snippet/i }));
    fireEvent.click(await screen.findByRole('button', { name: '$contact_name' }));

    expect(screen.getByLabelText('Message')).toHaveValue('$contact_name');
  });

  it('opens the edit modal pre-filled from the row', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit Stock check' }));

    expect(await screen.findByText('Edit snippet')).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toHaveValue('Stock check');
    expect(screen.getByLabelText('Shortcut')).toHaveValue('stock');
  });

  it('saves an edit against the row it was opened from', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit Stock check' }));
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Stock status' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() =>
      expect(updateAsync).toHaveBeenCalledWith({
        id: 's1',
        body: expect.objectContaining({ name: 'Stock status', shortcut: 'stock' }),
      }),
    );
  });

  it('parks the delete on the row that was pressed, with no dialog in the way (S6-10)', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'Delete Stock check' }));

    // D7: the press IS the action, and Cancel in the countdown is the way back.
    // The browser never calls the DELETE - the server does, when the window lapses.
    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'message_snippet.delete',
          entityType: 'message_snippet',
          entityId: 's1',
        }),
      ),
    );
    expect(deleteAsync).not.toHaveBeenCalled();
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();
  });
});

