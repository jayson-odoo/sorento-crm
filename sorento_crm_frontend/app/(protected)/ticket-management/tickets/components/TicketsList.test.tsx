/**
 * M5-06 - the tickets list renders on DataGrid instead of a raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// A SHARED `push`, not a fresh `vi.fn()` per `useRouter()` call - SF-4 asserts
// against it across the whole render, so it has to be the same reference the
// component actually calls.
const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/ticket-management/tickets',
  useSearchParams: () => new URLSearchParams(''),
}));

const TICKETS = [
  {
    id: 't-1',
    ticket_number: 'TKT-0001',
    title: 'Cannot log in',
    status: 'open',
    priority: 'high',
    category: 'technical',
    due_date: null,
    raised_by_kind: 'user',
    source_channel: 'manual',
    assigned_to_user: { id: 'u-1', display_name: 'Jane Doe' },
    watchers: [],
    respond_contacts: [],
    attachments: [],
    is_overdue_response: false,
    is_overdue_resolution: false,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-02T00:00:00',
  },
  {
    id: 't-2',
    ticket_number: 'TKT-0002',
    title: 'Invoice mismatch',
    status: 'resolved',
    priority: 'low',
    category: 'billing',
    due_date: null,
    raised_by_kind: 'user',
    source_channel: 'whatsapp_respond',
    assigned_to_user: null,
    watchers: [],
    respond_contacts: [],
    attachments: [],
    is_overdue_response: false,
    is_overdue_resolution: false,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-03T00:00:00',
  },
];

vi.mock('../services/ticketService', () => ({
  getTickets: vi.fn(async () => ({
    data: TICKETS,
    pagination: { total: 2, page: 1, limit: 50 },
  })),
  bulkDeleteTickets: vi.fn(async () => {}),
}));

import TicketsList from './TicketsList';
import { bulkDeleteTickets } from '../services/ticketService';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TicketsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  push.mockClear();
  vi.mocked(bulkDeleteTickets).mockClear();
});

describe('TicketsList - DataGrid', () => {
  it('renders the column headers and a real cell value for each ticket', async () => {
    renderList();

    await waitFor(() => {
      expect(screen.getByText('Cannot log in')).toBeInTheDocument();
    });

    expect(screen.getByText('Ticket #')).toBeInTheDocument();
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Assignee')).toBeInTheDocument();

    expect(screen.getByText('TKT-0001')).toBeInTheDocument();
    expect(screen.getByText('Invoice mismatch')).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
  });
});

describe('TicketsList - bulk delete (SF-4)', () => {
  it('ticking two row checkboxes does not open either record, and Delete selected -> confirm sends exactly those two ids', async () => {
    renderList();

    await waitFor(() => {
      expect(screen.getByText('Cannot log in')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select ticket TKT-0001' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select ticket TKT-0002' }));

    // Ticking the row's own checkbox must not also open the record - the box
    // stops the click from reaching the row (`data-grid-select-column.tsx`'s
    // `stopPropagation`).
    expect(push).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Delete 2 selected' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(bulkDeleteTickets).toHaveBeenCalledTimes(1);
    });
    const ids = vi.mocked(bulkDeleteTickets).mock.calls[0][0] as string[];
    expect([...ids].sort()).toEqual(['t-1', 't-2']);

    // Confirming the delete did not open a record either.
    expect(push).not.toHaveBeenCalled();
  });
});
