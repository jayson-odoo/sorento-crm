/**
 * Contact Details -> Customers card (UAC AC-1, AC-2, AC-3, AC-12). The service modules are mocked, never fetch; the real query hooks run.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const services = vi.hoisted(() => ({
  getContactCustomers: vi.fn(),
  linkContactCustomers: vi.fn(),
}));
vi.mock('../services/contactCustomersService', () => services);

const customerSvc = vi.hoisted(() => ({
  searchCustomersSelect: vi.fn(),
  CUSTOMER_SELECT_PAGE_SIZE: 50,
}));
vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => customerSvc);

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

// The real multi-select is a Radix popover; this stand-in lists the fetched options as checkboxes.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    onChange: (v: string[]) => void;
    fetchOptions?: (q: string) => Promise<
      { value: string; label: string; description?: string; disabled?: boolean }[]
    >;
  }) => {
    const [opts, setOpts] = React.useState<
      { value: string; label: string; description?: string; disabled?: boolean }[]
    >([]);
    // The real control fetches when it opens, not on mount, so options reflect the rows
    // loaded by then (which is what disables "already linked").
    return (
      <div>
        <button type="button" onClick={() => void props.fetchOptions?.('').then(setOpts)}>
          open picker
        </button>
        {opts.map((o) => (
          <label key={o.value}>
            <input
              type="checkbox"
              aria-label={o.label}
              checked={props.value.includes(o.value)}
              disabled={o.disabled}
              onChange={(e) =>
                props.onChange(
                  e.target.checked
                    ? [...props.value, o.value]
                    : props.value.filter((v) => v !== o.value),
                )
              }
            />
          </label>
        ))}
      </div>
    );
  },
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

// Option labels differ from the row text on purpose, so a row and its option never collide.
const OPTIONS = [
  { value: LINKS[0].customer_id, label: 'Option C-100', description: 'AG-1 - Alice' },
  { value: 'opt-2', label: 'Option C-300', description: 'No sales agent' },
  { value: 'opt-3', label: 'Option C-400', description: 'No sales agent' },
  { value: 'opt-4', label: 'Option C-500', description: 'No sales agent' },
].map((o) => ({ ...o, disabled: false }));

async function openPicker() {
  fireEvent.click(await screen.findByRole('button', { name: 'open picker' }));
}

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
  services.linkContactCustomers.mockResolvedValue(LINKS);
  customerSvc.searchCustomersSelect.mockReset();
  customerSvc.searchCustomersSelect.mockResolvedValue(OPTIONS);
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
    expect(screen.getByRole('button', { name: 'Link customers' })).toBeInTheDocument();
  });

  it('AC-3 / AC-14: ticking three customers reads "Link 3 customers" and one click sends all three ids once', async () => {
    services.getContactCustomers.mockResolvedValue({ data: [] });
    renderSection();
    await screen.findByText('No customers linked');
    await openPicker();
    fireEvent.click(await screen.findByLabelText('Option C-300'));
    fireEvent.click(screen.getByLabelText('Option C-400'));
    fireEvent.click(screen.getByLabelText('Option C-500'));

    const button = screen.getByRole('button', { name: 'Link customers' });
    expect(button).toHaveTextContent('Link 3 customers');
    expect(button).toBeEnabled();
    fireEvent.click(button);

    await waitFor(() => expect(services.linkContactCustomers).toHaveBeenCalledTimes(1));
    expect(services.linkContactCustomers).toHaveBeenCalledWith('contact-1', [
      'opt-2',
      'opt-3',
      'opt-4',
    ]);
  });

  it('AC-14: with nothing ticked the Link button is disabled', async () => {
    services.getContactCustomers.mockResolvedValue({ data: [] });
    renderSection();

    await openPicker();
    await screen.findByLabelText('Option C-300');
    expect(screen.getByRole('button', { name: 'Link customers' })).toBeDisabled();
    expect(services.linkContactCustomers).not.toHaveBeenCalled();
  });

  it('AC-3: an already-linked customer is a disabled option', async () => {
    services.getContactCustomers.mockResolvedValue({ data: LINKS });
    renderSection();

    await screen.findByText('C-100 - Hanlim Alpha');
    await openPicker();
    expect(await screen.findByLabelText('Option C-100')).toBeDisabled();
    expect(screen.getByLabelText('Option C-300')).toBeEnabled();
  });

  it('AC-12: without contacts.edit the card is read-only (no select, no Unlink)', async () => {
    permissionState.granted = new Set();
    services.getContactCustomers.mockResolvedValue({ data: LINKS });
    renderSection();

    expect(await screen.findByText('C-100 - Hanlim Alpha')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Link customers' })).toBeNull();
    expect(screen.queryByLabelText('Option C-300')).toBeNull();
    expect(screen.queryByRole('button', { name: /unlink/i })).toBeNull();
  });

  it('AC-12: with contacts.edit each row carries an Unlink control', async () => {
    services.getContactCustomers.mockResolvedValue({ data: LINKS });
    renderSection();

    expect(await screen.findByText('C-100 - Hanlim Alpha')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /unlink/i })).toHaveLength(2);
  });
});
