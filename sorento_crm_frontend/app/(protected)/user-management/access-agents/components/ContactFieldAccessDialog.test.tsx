import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ContactFieldAccessDialog from './ContactFieldAccessDialog';

const getAgentFieldAccess = vi.fn();
const setAgentFieldAccess = vi.fn();

vi.mock('../services/accessAgentService', () => ({
  getAgentFieldAccess: (...a: unknown[]) => getAgentFieldAccess(...a),
  setAgentFieldAccess: (...a: unknown[]) => setAgentFieldAccess(...a),
}));

const FIELDS = [
  // Agent allows it; this contact has no exception.
  { resource: 'incoming_stock', field_key: 'eta_date', label: 'ETA', is_allowed: true, override: null, effective: true },
  // Agent denies it; this contact is explicitly allowed.
  { resource: 'incoming_stock', field_key: 'gatepass_date', label: 'Gatepass', is_allowed: false, override: true, effective: true },
];

function setup() {
  getAgentFieldAccess.mockResolvedValue({
    agent_code: 'incoming_stock_enquiries',
    fields: FIELDS,
    overrides: [],
  });
  setAgentFieldAccess.mockResolvedValue({ agent_code: 'x', fields: FIELDS, overrides: [] });

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactFieldAccessDialog
        open
        onOpenChange={() => {}}
        agentId="agent-1"
        agentName="Incoming Stock Enquiries"
        contactId="contact-1"
        contactName="Ah Seng Hardware"
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getAgentFieldAccess.mockReset();
  setAgentFieldAccess.mockReset();
});

describe('ContactFieldAccessDialog', () => {
  it('asks the backend for this contact, not the agent-wide view', async () => {
    setup();
    await waitFor(() => expect(getAgentFieldAccess).toHaveBeenCalledWith('agent-1', 'contact-1'));
  });

  it('shows what the contact inherits, not just what is overridden', async () => {
    setup();
    // An inherited value must say so, or an admin cannot tell an explicit deny
    // from an untouched default - and those behave differently later.
    expect(await screen.findByRole('button', { name: 'ETA: Follows agent (allowed)' })).toBeInTheDocument();
    // The dialog's draft mirrors the server state through a `useEffect`, one
    // render tick after the fetch resolves. `findByRole` above only proves
    // the fetch settled, not that the effect has run, so assert with a
    // retrying query rather than a one-shot `getByRole`.
    expect(await screen.findByRole('button', { name: 'Gatepass: Allowed for this contact' })).toBeInTheDocument();
  });

  it('cycles a field through follow, allow and deny', async () => {
    setup();
    fireEvent.click(await screen.findByRole('button', { name: 'ETA: Follows agent (allowed)' }));
    expect(await screen.findByRole('button', { name: 'ETA: Allowed for this contact' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'ETA: Allowed for this contact' }));
    expect(await screen.findByRole('button', { name: 'ETA: Denied for this contact' })).toBeInTheDocument();
  });

  it('sends null to clear an override rather than guessing a boolean', async () => {
    setup();
    // Gatepass starts as an explicit allow; cycling it twice lands on "follows".
    fireEvent.click(await screen.findByRole('button', { name: 'Gatepass: Allowed for this contact' }));
    fireEvent.click(screen.getByRole('button', { name: 'Gatepass: Denied for this contact' }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(setAgentFieldAccess).toHaveBeenCalledTimes(1));
    expect(setAgentFieldAccess).toHaveBeenCalledWith(
      'agent-1',
      [
        {
          resource: 'incoming_stock',
          field_key: 'gatepass_date',
          is_allowed: null,
          contact_id: 'contact-1',
        },
      ],
      'contact-1',
    );
  });

  it('sends only the fields that changed', async () => {
    setup();
    fireEvent.click(await screen.findByRole('button', { name: 'ETA: Follows agent (allowed)' }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(setAgentFieldAccess).toHaveBeenCalled());
    const sent = setAgentFieldAccess.mock.calls[0][1] as { field_key: string }[];
    expect(sent).toHaveLength(1);
    expect(sent[0].field_key).toBe('eta_date');
  });

  it('cannot save with nothing changed', async () => {
    setup();
    await screen.findByRole('button', { name: 'ETA: Follows agent (allowed)' });
    // Save's disabled state comes from `dirty`, which compares against a
    // draft the dialog copies from the fetched data via a `useEffect` - one
    // render tick after the fetch resolves. Asserting immediately after the
    // findByRole above can catch that tick between fetch and effect, where
    // the draft is still empty and "dirty" reads non-empty. Wait for it to
    // settle instead of asserting once.
    await waitFor(() => expect(screen.getByRole('button', { name: /save/i })).toBeDisabled());
  });

  it('counts the exceptions so an admin sees this contact is not standard', async () => {
    setup();
    expect(await screen.findByText('1 exception(s)')).toBeInTheDocument();
  });
});
