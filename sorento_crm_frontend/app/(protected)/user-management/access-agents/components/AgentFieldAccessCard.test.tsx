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

  it('renders every field the agent owns, ticked or not', () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
    expect(screen.getByText('ETA delay')).toBeInTheDocument();
    // The denied one is present-and-unticked, not omitted: a field you cannot see
    // on the screen is a field you cannot grant.
    expect(screen.getByText('Gatepass')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 allowed')).toBeInTheDocument();
  });

  it('tells the admin the agent restricts nothing when it owns no gated fields', () => {
    setup({ agent_code: 'other_agent', fields: [], overrides: [] });
    expect(screen.getByText(/owns no restricted fields/i)).toBeInTheDocument();
  });

  it('only sends the ticks that actually changed', async () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });

    fireEvent.click(screen.getAllByRole('checkbox')[1]); // tick Gatepass
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(mockMutate).toHaveBeenCalledTimes(1));
    expect(mockMutate).toHaveBeenCalledWith({
      agentId: 'agent-1',
      // ETA delay was already allowed and untouched, so it is not resent - two
      // admins editing different rows must not revoke each other.
      fields: [{ resource: 'incoming_stock', field_key: 'gatepass_date', is_allowed: true }],
    });
  });

  it('cannot save with nothing changed', () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  });

  it('surfaces per-contact exceptions, which the ticks alone would not explain', () => {
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

    expect(screen.getByText(/per-contact exceptions/i)).toBeInTheDocument();
    expect(screen.getByText('Ah Seng Hardware')).toBeInTheDocument();
    expect(screen.getByText(/may not see/i)).toBeInTheDocument();
  });

  it('hides the exceptions section when there are none', () => {
    setup({ agent_code: 'incoming_stock_enquiries', fields: FIELDS, overrides: [] });
    expect(screen.queryByText(/per-contact exceptions/i)).not.toBeInTheDocument();
  });
});
