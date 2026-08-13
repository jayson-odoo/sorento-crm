import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AgentFieldAccessCard from './AgentFieldAccessCard';

const mockUseFieldAccess = vi.fn();
const mockMutate = vi.fn();

vi.mock('../hooks/useAccessAgents', () => ({
  useAgentFieldAccess: (...args: unknown[]) => mockUseFieldAccess(...args),
  useSetAgentFieldAccess: () => ({ mutate: mockMutate, isPending: false }),
}));

const FIELDS = [
  { resource: 'incoming_stock', field_key: 'eta_delay_date', label: 'ETA delay', is_allowed: true },
  { resource: 'incoming_stock', field_key: 'gatepass_date', label: 'Gatepass', is_allowed: false },
];

function setup(data: unknown, state: Partial<{ isLoading: boolean; isError: boolean }> = {}) {
  mockUseFieldAccess.mockReturnValue({
    data,
    isLoading: state.isLoading ?? false,
    isError: state.isError ?? false,
  });
  return render(<AgentFieldAccessCard agentId="agent-1" />);
}

// The trigger renders chips once fields are allowed, so it has no stable accessible name.
const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);

beforeEach(() => {
  mockUseFieldAccess.mockReset();
  mockMutate.mockReset();
});

describe('AgentFieldAccessCard', () => {
  it('shows a loading skeleton rather than an empty list', () => {
    const { container } = setup(undefined, { isLoading: true });
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it('says so when the list cannot be loaded', () => {
    setup(undefined, { isError: true });
    expect(screen.getByText(/could not load the field list/i)).toBeInTheDocument();
  });

  it('shows the allowed fields on the trigger without opening anything', () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });

    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]')!;
    expect(trigger.textContent).toContain('ETA delay');
    expect(screen.getByText('1 of 2 allowed')).toBeInTheDocument();
  });

  it('offers every field the agent owns, allowed or not', async () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });
    openMenu();

    // The denied one is offered-and-unselected, not omitted: a field you cannot see
    // on the screen is a field you cannot grant.
    await waitFor(() => expect(screen.getByRole('option', { name: /Gatepass/ })).toBeInTheDocument());
    expect(screen.getByRole('option', { name: /ETA delay/ })).toBeInTheDocument();
  });

  it('shows the field key beside the label, because that is what the answer side speaks', async () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });
    openMenu();

    // `gatepass_date` is the token the MCP envelope keys on and the one
    // `field_access.denied[].field` reports; the admin-facing label is not.
    await waitFor(() => expect(screen.getByText('gatepass_date')).toBeInTheDocument());
  });

  it('tells the admin the agent restricts nothing when it owns no gated fields', () => {
    setup({ agent_code: 'other_agent', fields: [], overrides: [] });
    expect(screen.getByText(/owns no restricted fields/i)).toBeInTheDocument();
  });

  it('only sends the fields that actually changed', async () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });
    openMenu();

    await waitFor(() => expect(screen.getByRole('option', { name: /Gatepass/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('option', { name: /Gatepass/ }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(mockMutate).toHaveBeenCalledTimes(1));
    expect(mockMutate).toHaveBeenCalledWith({
      agentId: 'agent-1',
      // ETA delay was already allowed and untouched, so it is not resent - two
      // admins editing different rows must not revoke each other.
      fields: [{ resource: 'incoming_stock', field_key: 'gatepass_date', is_allowed: true }],
    });
  });

  it('sends a revoke when an allowed field is deselected', async () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });
    openMenu();

    await waitFor(() => expect(screen.getByRole('option', { name: /ETA delay/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('option', { name: /ETA delay/ }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(mockMutate).toHaveBeenCalledTimes(1));
    expect(mockMutate).toHaveBeenCalledWith({
      agentId: 'agent-1',
      fields: [{ resource: 'incoming_stock', field_key: 'eta_delay_date', is_allowed: false }],
    });
  });

  it('cannot save with nothing changed', () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  });

  it('does not render per-contact exceptions, which live on the contact page', () => {
    // Display only. The overrides are still returned by the API and still written
    // from the contact's own page - they are what makes `field_access.denied`
    // able to say "you may not see this" instead of "that has not happened yet".
    setup({
      agent_code: 'incoming_stock_enquiries',
      fields: FIELDS,
      overrides: [
        {
          resource: 'incoming_stock',
          field_key: 'eta_delay_date',
          label: 'ETA delay',
          contact_id: 'c-1',
          contact_name: 'Ah Seng Hardware',
          is_allowed: false,
        },
      ],
    });

    expect(screen.queryByText(/per-contact exceptions/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Ah Seng Hardware')).not.toBeInTheDocument();
  });
});
