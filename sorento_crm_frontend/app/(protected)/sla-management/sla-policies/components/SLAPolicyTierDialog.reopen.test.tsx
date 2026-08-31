/**
 * S7-03 - a create-mode dialog reopens clean.
 *
 * SLAPolicyTierDialog stays mounted between openings (only Radix's
 * DialogContent unmounts); before this slice, editing a tier then reopening
 * on "Add tier" showed the last tier's numbers, because both the local
 * number-input strings and react-hook-form's own state survived the close.
 * `openValues` now names create-mode's values explicitly, and the
 * open/close effect re-seeds the local strings every time the dialog opens.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import SLAPolicyTierDialog from './SLAPolicyTierDialog';
import type { SLAPolicyTier } from '../types/slaPolicy.types';

const noopMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };

vi.mock('../hooks/useSLAPolicies', () => ({
  useCreateSLAPolicyTier: () => noopMutation,
  useUpdateSLAPolicyTier: () => noopMutation,
}));

function makeTier(overrides: Partial<SLAPolicyTier> = {}): SLAPolicyTier {
  return {
    id: 't-5',
    policy_id: 'p-1',
    tier_level: 5,
    tier_name: 'Tier Five',
    response_hours: 48,
    resolution_hours: 72,
    created_at: new Date(),
    updated_at: new Date(),
    ...overrides,
  };
}

beforeEach(() => {
  noopMutation.mutate.mockClear();
  noopMutation.mutateAsync.mockClear();
});

describe('SLAPolicyTierDialog reopens clean in create mode (S7-03)', () => {
  it('does not show the previously-edited tier after closing and reopening to add a new one', async () => {
    const onOpenChange = vi.fn();
    const tier = makeTier();

    const { rerender } = render(
      <SLAPolicyTierDialog open policyId="p-1" tier={tier} onOpenChange={onOpenChange} />,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('5')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Tier Five')).toBeInTheDocument();
      expect(screen.getByDisplayValue('48')).toBeInTheDocument();
      expect(screen.getByDisplayValue('72')).toBeInTheDocument();
    });

    // Close the dialog (component instance stays mounted).
    rerender(
      <SLAPolicyTierDialog open={false} policyId="p-1" tier={tier} onOpenChange={onOpenChange} />,
    );

    // Reopen in create mode ("Add tier").
    rerender(
      <SLAPolicyTierDialog open policyId="p-1" tier={null} onOpenChange={onOpenChange} />,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('1')).toBeInTheDocument();
      // response_hours AND resolution_hours both default to 24.
      expect(screen.getAllByDisplayValue('24')).toHaveLength(2);
    });
    expect(screen.queryByDisplayValue('Tier Five')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('5')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('48')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('72')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Add SLA Policy Tier' })).toBeInTheDocument();
  });
});
