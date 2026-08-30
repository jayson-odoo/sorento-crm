/**
 * S7-03 - the second create-mode dialog reopens clean.
 *
 * Same bug as SLAPolicyTierDialog: the component stays mounted between
 * openings, so create mode has to name its own `values` too, or reopening
 * on "Add" shows the grant that was just edited.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactAgentAccessDialog from './ContactAgentAccessDialog';
import type { ContactAgentAccess } from '../types/accessAgent.types';

const noopMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };

vi.mock('../hooks/useAccessAgents', () => ({
  useCreateContactAgentAccess: () => noopMutation,
  useUpdateContactAgentAccess: () => noopMutation,
}));

function makeContactAccess(overrides: Partial<ContactAgentAccess> = {}): ContactAgentAccess {
  return {
    id: 'ca-1',
    respond_contact_phone: '+60123456789',
    respond_contact_name: 'Alice',
    agent_id: 'a-1',
    is_allowed: false,
    valid_from: new Date('2026-01-01T00:00:00.000Z'),
    valid_to: new Date('2026-02-01T00:00:00.000Z'),
    created_at: new Date(),
    synced_to_excel: false,
    ...overrides,
  };
}

beforeEach(() => {
  noopMutation.mutate.mockClear();
  noopMutation.mutateAsync.mockClear();
});

describe('ContactAgentAccessDialog reopens clean in create mode (S7-03)', () => {
  it('does not carry the edited grant\'s Allowed/date fields into a fresh Add', async () => {
    const onOpenChange = vi.fn();
    const contactAccess = makeContactAccess();
    const queryClient = new QueryClient();

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ContactAgentAccessDialog
          open
          onOpenChange={onOpenChange}
          contactAccess={contactAccess}
          accessAgentId="a-1"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
      expect(screen.getByDisplayValue('2026-01-01')).toBeInTheDocument();
      expect(screen.getByDisplayValue('2026-02-01')).toBeInTheDocument();
    });

    // Close (component instance stays mounted).
    rerender(
      <QueryClientProvider client={queryClient}>
        <ContactAgentAccessDialog
          open={false}
          onOpenChange={onOpenChange}
          contactAccess={contactAccess}
          accessAgentId="a-1"
        />
      </QueryClientProvider>,
    );

    // Reopen in create mode ("Add").
    rerender(
      <QueryClientProvider client={queryClient}>
        <ContactAgentAccessDialog
          open
          onOpenChange={onOpenChange}
          contactAccess={null}
          accessAgentId="a-2"
          defaultContactPhone="+60199999999"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
    });
    expect(screen.queryByDisplayValue('2026-01-01')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('2026-02-01')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Add Contact Access Agent' })).toBeInTheDocument();
  });
});
