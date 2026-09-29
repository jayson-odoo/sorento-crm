/**
 * Contact Details -> Customers card (UAC AC-1, AC-2, AC-3, AC-12). The service modules are mocked, never fetch; the real query hooks run.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const services = vi.hoisted(() => ({
  getContactCustomers: vi.fn(),
  linkContactCustomer: vi.fn(),
}));
vi.mock('../services/contactCustomersService', () => services);

vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => ({
  searchCustomersSelect: vi.fn(async () => []),
  CUSTOMER_SELECT_PAGE_SIZE: 50,
}));

const permissionState = vi.hoisted(() => ({
  granted: new Set<string>(['user_management.contacts.edit']),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissionState.granted.has(slug),
}));

vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({
    run: vi.fn(),
    targetId: null,
    countdown: null,
    isPending: false,
  }),
  useRowPending: () => () => false,
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// The real select is a Radix popover; this stand-in exposes one pick that reports a customer id.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: { onChange: (v: string) => void; 'aria-label'?: string }) => (
    <button type="button" onClick={() => props.onChange('11111111-2222-4333-8444-555555555555')}>
      pick:{props['aria-label']}
    </button>
  ),
}));

import ContactCustomersSection from './ContactCustomersSection';

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const LINKS = [
  {
    id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    customer_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    customer_code: 'C-100',
    customer_name: 'Hanlim Alpha',
    is_active: true,
    source: 'manual',
    sales_agent_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    sales_agent_code: 'AG-1',
    sales_agent_name: 'Alice',
    created_at: '2026-01-01T00:00:00',
  },
  {
    id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    customer_id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
    customer_name: 'Hanlim Beta',
    customer_code: 'C-200',
    is_active: true,
    source: 'manual',
    sales_agent_id: null,
    sales_agent_code: null,
    sales_agent_name: null,
    created_at: '2026-01-02T00:00:00',
  },
];

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactCustomersSection contactId="contact-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(services).forEach((fn) => fn.mockReset());
  permissionState.granted = new Set(['user_management.contacts.edit']);
  services.linkContactCustomer.mockResolvedValue(LINKS[0]);
});

afterEach(() => cleanup());

describe('ContactCustomersSection', () => {
  it('AC-1: one row per link with code - name and the agent, no UUID, no Primary text', async () => {
    services.getContactCustomers.mockResolvedValue({ data: LINKS });
    renderSection();

    expect(await screen.findByText('C-100 - Hanlim Alpha')).toBeInTheDocument();
    expect(screen.getByText('C-200 - Hanlim Beta')).toBeInTheDocument();
    expect(screen.getByText('AG-1 - Alice')).toBeInTheDocument();
    expect(screen.getByText('No sales agent')).toBeInTheDocument();
    expect(screen.queryByText(/primary/i)).not.toBeInTheDocument();
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });

  it('AC-2: no links shows the empty state and keeps the Add customer select', async () => {
    services.getContactCustomers.mockResolvedValue({ data: [] });
    renderSection();

    expect(await screen.findByText('No customers linked')).toBeInTheDocument();
    expect(
      screen.getByText('Link the customer accounts this contact belongs to'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /pick:Add customer/ })).toBeInTheDocument();
  });

  it('AC-3: picking a customer calls the link service with that customer id', async () => {
    services.getContactCustomers.mockResolvedValue({ data: [] });
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: /pick:Add customer/ }));

    await waitFor(() => expect(services.linkContactCustomer).toHaveBeenCalledTimes(1));
    expect(services.linkContactCustomer.mock.calls[0][0]).toBe('contact-1');
    expect(services.linkContactCustomer.mock.calls[0][1]).toBe(
      '11111111-2222-4333-8444-555555555555',
    );
  });

  it('AC-12: without contacts.edit the card is read-only (no select, no Unlink)', async () => {
    permissionState.granted = new Set();
    services.getContactCustomers.mockResolvedValue({ data: LINKS });
    renderSection();

    expect(await screen.findByText('C-100 - Hanlim Alpha')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pick:Add customer/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /unlink/i })).toBeNull();
  });

  it('AC-12: with contacts.edit each row carries an Unlink control', async () => {
    services.getContactCustomers.mockResolvedValue({ data: LINKS });
    renderSection();

    expect(await screen.findByText('C-100 - Hanlim Alpha')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /unlink/i })).toHaveLength(2);
  });
});
