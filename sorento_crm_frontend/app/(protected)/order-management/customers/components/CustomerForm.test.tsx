/**
 * CustomerForm - the "Sales agent" field (#1170 slice 1).
 *
 * Two things matter: an already-assigned agent shows up preselected when the record loads
 * (never a blank the person has to re-pick), and clearing it sends an explicit `null` rather
 * than omitting the key - `CustomerUpdate.sales_agent_id` is `exclude_unset`, so an omitted
 * key means "leave it alone" and would silently keep the old agent.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const getCustomer = vi.fn();
const createCustomer = vi.fn();
const updateCustomer = vi.fn();
const getCustomers = vi.fn();
const deleteCustomer = vi.fn();
const getCustomerSalesAgentsSelect = vi.fn();

vi.mock('../services/customerService', () => ({
  getCustomer: (...a: unknown[]) => getCustomer(...a),
  createCustomer: (...a: unknown[]) => createCustomer(...a),
  updateCustomer: (...a: unknown[]) => updateCustomer(...a),
  getCustomers: (...a: unknown[]) => getCustomers(...a),
  deleteCustomer: (...a: unknown[]) => deleteCustomer(...a),
  getCustomerSalesAgentsSelect: (...a: unknown[]) => getCustomerSalesAgentsSelect(...a),
}));

import CustomerForm from './CustomerForm';

const AGENTS = [
  { id: 'agent-1', sales_agent: 'SEAN I', person_label: 'Sean Tan' },
  { id: 'agent-2', sales_agent: 'LCL', person_label: null },
];

const CUSTOMER = {
  id: 'cust-1',
  customer_code: 'C-001',
  customer_name: 'Alpha Trading',
  email: null,
  phone_number: null,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  sales_agent_id: 'agent-1',
  sales_agent_code: 'SEAN I',
  sales_agent_name: 'Sean Tan',
};

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  getCustomerSalesAgentsSelect.mockResolvedValue(AGENTS);
  updateCustomer.mockResolvedValue({ ...CUSTOMER });
  createCustomer.mockResolvedValue({ ...CUSTOMER, id: 'cust-2' });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('CustomerForm - Sales agent', () => {
  it('preselects the customer\'s current agent, code and name, no id shown', async () => {
    getCustomer.mockResolvedValue({ ...CUSTOMER });
    render(<CustomerForm customerId="cust-1" />);

    const combo = await screen.findByRole('combobox', { name: 'Sales Agent' });
    await waitFor(() => expect(combo).toHaveTextContent('SEAN I - Sean Tan'));
    expect(combo).not.toHaveTextContent('agent-1');
  });

  it('sends an explicit null when the agent is cleared', async () => {
    getCustomer.mockResolvedValue({ ...CUSTOMER });
    render(<CustomerForm customerId="cust-1" />);

    const combo = await screen.findByRole('combobox', { name: 'Sales Agent' });
    await waitFor(() => expect(combo).toHaveTextContent('SEAN I - Sean Tan'));

    fireEvent.pointerDown(within(combo).getByRole('button', { name: 'Clear selection' }));
    fireEvent.click(screen.getByRole('button', { name: /update customer/i }));

    await waitFor(() => expect(updateCustomer).toHaveBeenCalled());
    expect(updateCustomer).toHaveBeenCalledWith(
      'cust-1',
      expect.objectContaining({ sales_agent_id: null }),
    );
  });

  it('a new customer with no agent picked submits null, not an unset field', async () => {
    render(<CustomerForm />);

    fireEvent.change(screen.getByPlaceholderText('CUST-001'), { target: { value: 'C-999' } });
    fireEvent.change(screen.getByPlaceholderText('Enter customer name'), {
      target: { value: 'Beta Supplies' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create customer/i }));

    await waitFor(() => expect(createCustomer).toHaveBeenCalled());
    expect(createCustomer).toHaveBeenCalledWith(
      expect.objectContaining({ sales_agent_id: null }),
    );
  });

  it('lists every active agent as code - name, searchable, not capped', async () => {
    getCustomer.mockResolvedValue({ ...CUSTOMER });
    render(<CustomerForm customerId="cust-1" />);

    const combo = await screen.findByRole('combobox', { name: 'Sales Agent' });
    fireEvent.click(combo);

    expect(await screen.findByRole('option', { name: 'SEAN I - Sean Tan' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'LCL' })).toBeInTheDocument();
  });

  it('narrows the list when a search term is typed', async () => {
    getCustomer.mockResolvedValue({ ...CUSTOMER });
    render(<CustomerForm customerId="cust-1" />);

    const combo = await screen.findByRole('combobox', { name: 'Sales Agent' });
    fireEvent.click(combo);
    await screen.findByRole('option', { name: 'LCL' });

    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'LCL' } });

    expect(screen.getByRole('option', { name: 'LCL' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'SEAN I - Sean Tan' })).not.toBeInTheDocument();
  });

  it('shows a customer\'s current agent, once deactivated, as a disabled preselected option - never a blank', async () => {
    // The active-agents select (AGENTS) no longer carries this id - the agent was
    // deactivated after assignment - but the customer record still names it.
    const customerWithRetiredAgent = {
      ...CUSTOMER,
      sales_agent_id: 'agent-retired',
      sales_agent_code: 'RETIRED',
      sales_agent_name: 'Old Agent',
    };
    getCustomer.mockResolvedValue(customerWithRetiredAgent);
    render(<CustomerForm customerId="cust-1" />);

    const combo = await screen.findByRole('combobox', { name: 'Sales Agent' });
    // Not the placeholder ("No sales agent") - the assignment is still visible.
    await waitFor(() => expect(combo).toHaveTextContent(/RETIRED.*Old Agent/));

    fireEvent.click(combo);
    const option = await screen.findByRole('option', { name: /RETIRED.*Old Agent/ });
    expect(option).toHaveAttribute('aria-disabled', 'true');
  });

  it('never labels the current agent inactive while the options query is still loading', async () => {
    // Review round 2, new finding 1: while `agentOptions` is loading (or errors, or 403s -
    // PUT is ungated today), `options` reads as an empty array, same as a genuinely
    // deactivated agent - and used to synthesize a misleading "(inactive)" label on an
    // agent that is perfectly active, just not loaded yet. Never resolves during this test.
    getCustomer.mockResolvedValue({ ...CUSTOMER });
    getCustomerSalesAgentsSelect.mockReturnValue(new Promise(() => {}));
    render(<CustomerForm customerId="cust-1" />);

    const combo = await screen.findByRole('combobox', { name: 'Sales Agent' });
    expect(combo).not.toHaveTextContent('(inactive)');
    expect(combo).not.toHaveTextContent('SEAN I');
  });
});
