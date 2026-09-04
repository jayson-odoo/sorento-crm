/**
 * M5-06 - the tickets list renders on DataGrid instead of a raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
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

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TicketsList />
    </QueryClientProvider>,
  );
}

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
