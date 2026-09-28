/**
 * Chatbot stock ask v2 S5 - the customer's Asks tab (AC-SA509, AC-SA510).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const canEdit = vi.hoisted(() => ({ value: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => slug === 'order_management.customers.edit' && canEdit.value,
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    clearable?: boolean;
  }) => (
    <select
      id={props.id}
      data-clearable={props.clearable ? 'true' : 'false'}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const listCustomerAsks = vi.fn();
const updateCustomerAsk = vi.fn();
vi.mock('@/services/stockAskService', async () => {
  const actual = await vi.importActual<typeof import('@/services/stockAskService')>(
    '@/services/stockAskService',
  );
  return {
    ...actual,
    listCustomerAsks: (...a: unknown[]) => listCustomerAsks(...a),
    updateCustomerAsk: (...a: unknown[]) => updateCustomerAsk(...a),
  };
});

import { CustomerAsksTab } from './CustomerAsksTab';

const ROW = {
  id: 'ask-1',
  customer_name: 'Hock Lee Trading',
  contact_name: 'Ah Seng',
  product_code: 'SRT5674',
  product_name: 'Wiper Blade 24in',
  quantity: 50,
  branch: 'in_stock',
  answer_summary: 'SRT5674 x 50: yes, we have stock, please refer to your salesman to proceed.',
  notified_agent: false,
  notify_skip_reason: 'toggle_off',
  state: 'open',
  note: null,
  created_at: '2026-09-24T06:32:00',
  updated_at: '2026-09-24T06:32:00',
};

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  canEdit.value = true;
  listCustomerAsks.mockResolvedValue({ data: [ROW], pagination: { total: 1, page: 1, limit: 20 } });
  updateCustomerAsk.mockResolvedValue({ ...ROW, state: 'done' });
});

describe('CustomerAsksTab', () => {
  it('renders the grid with every column and the ask', async () => {
    render(<CustomerAsksTab customerId="cust-1" />);
    await waitFor(() => expect(screen.getByText('SRT5674')).toBeInTheDocument());
    for (const header of ['Asked at', 'Contact', 'Product', 'Qty', 'Branch', 'Answer', 'Notified', 'State', 'Note']) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
    expect(screen.getByText('Ah Seng')).toBeInTheDocument();
    expect(screen.getByText('In stock')).toBeInTheDocument();
    expect(screen.getByText(ROW.answer_summary)).toHaveAttribute('title', ROW.answer_summary);
    // Notified: the badge, with the reason on its title.
    expect(screen.getByText('Not sent')).toHaveAttribute('title', 'Notify salesman is off for this contact');
    expect(listCustomerAsks).toHaveBeenCalledWith('cust-1', expect.objectContaining({ pageIndex: 0 }));
    expect(screen.queryByText('ask-1')).not.toBeInTheDocument();
  });

  it('shows an explicit empty state', async () => {
    listCustomerAsks.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 20 } });
    render(<CustomerAsksTab customerId="cust-1" />);
    await waitFor(() => expect(screen.getByText('No stock asks yet')).toBeInTheDocument());
  });

  it('is read-only without order_management.customers.edit', async () => {
    canEdit.value = false;
    render(<CustomerAsksTab customerId="cust-1" />);
    await waitFor(() => expect(screen.getByText('SRT5674')).toBeInTheDocument());
    expect(screen.queryByLabelText('State for SRT5674')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Note for SRT5674')).not.toBeInTheDocument();
    expect(screen.getByText('Open')).toBeInTheDocument();
  });

  it('saves a state change through the mutation', async () => {
    render(<CustomerAsksTab customerId="cust-1" />);
    const select = await screen.findByLabelText('State for SRT5674');
    expect(select).toHaveAttribute('data-clearable', 'false');
    fireEvent.change(select, { target: { value: 'done' } });
    await waitFor(() => expect(updateCustomerAsk).toHaveBeenCalledWith('cust-1', 'ask-1', { state: 'done' }));
  });

  it('saves a note on blur, and only when it changed', async () => {
    render(<CustomerAsksTab customerId="cust-1" />);
    const note = await screen.findByLabelText('Note for SRT5674');
    fireEvent.blur(note);
    expect(updateCustomerAsk).not.toHaveBeenCalled();
    fireEvent.change(note, { target: { value: 'Called, quoted 50' } });
    fireEvent.blur(note);
    await waitFor(() =>
      expect(updateCustomerAsk).toHaveBeenCalledWith('cust-1', 'ask-1', { note: 'Called, quoted 50' }),
    );
  });
});
