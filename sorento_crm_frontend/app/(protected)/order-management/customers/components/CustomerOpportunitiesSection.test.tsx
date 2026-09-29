/**
 * The customer page's Opportunities section (UAC S2-12; plan section 16, J8).
 *
 * "No opportunities yet" with a "Log opportunity" button when there are none, preset to this
 * customer; the section renders in both view and edit (same layout, CLAUDE.md CRUD standard).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const hooks = vi.hoisted(() => ({ useCustomerOpportunities: vi.fn() }));
vi.mock('@/app/(protected)/sales/opportunities/hooks/useSalesOpportunities', () => hooks);

vi.mock('@/app/(protected)/sales/opportunities/components/SalesOpportunityModal', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">opportunity modal</div> : null,
}));

// Phase 3 fix B4: the section is gated on the sales module being enabled and on
// sales.opportunities.view/.add - default every existing test to "on", so only the new
// gating tests below need to override these.
const permissionState = vi.hoisted(() => ({
  granted: new Set(['sales.opportunities.view', 'sales.opportunities.add']),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissionState.granted.has(slug),
}));
const moduleState = vi.hoisted(() => ({
  enabledModuleKeys: new Set(['sales']) as Set<string> | null,
  isLoading: false,
}));
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => moduleState,
}));

import CustomerOpportunitiesSection from './CustomerOpportunitiesSection';

beforeEach(() => {
  hooks.useCustomerOpportunities.mockReset();
  permissionState.granted = new Set(['sales.opportunities.view', 'sales.opportunities.add']);
  moduleState.enabledModuleKeys = new Set(['sales']);
  moduleState.isLoading = false;
});

describe('CustomerOpportunitiesSection', () => {
  it('shows "No opportunities yet" with Log opportunity when there are none', () => {
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(screen.getByText('No opportunities yet')).toBeTruthy();
    // Two now (nit: the empty state carries its own CTA in the body, alongside the
    // CardHeader's) - either opens the same modal.
    fireEvent.click(screen.getAllByRole('button', { name: /log opportunity/i })[0]);
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('lists the customer opportunities when present', () => {
    hooks.useCustomerOpportunities.mockReturnValue({
      data: [
        {
          id: 'opp-1',
          opportunity_no: 'OPP-000001',
          title: 'ZZT Deal',
          stage_label: 'New',
          expected_amount: '1000.00',
          expected_close_date: '2026-11-01',
        },
      ],
      isLoading: false,
      isError: false,
    });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(screen.getByText('ZZT Deal')).toBeTruthy();
    expect(screen.queryByText('No opportunities yet')).toBeNull();
  });

  it('renders the same in view and edit mode', () => {
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { rerender } = render(<CustomerOpportunitiesSection customerId="cust-1" isEditing={false} />);
    expect(screen.getByText('No opportunities yet')).toBeTruthy();
    rerender(<CustomerOpportunitiesSection customerId="cust-1" isEditing={true} />);
    expect(screen.getByText('No opportunities yet')).toBeTruthy();
  });

  it('fix B4: the empty state carries its own Log opportunity CTA in the body', () => {
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    const buttons = screen.getAllByRole('button', { name: /log opportunity/i });
    // One in the CardHeader, one in the empty-state body (nit: an empty state's CTA
    // belongs in the body, not only in a header the reader may not associate with it).
    expect(buttons.length).toBe(2);
  });

  it('fix B4: renders nothing without sales.opportunities.view', () => {
    permissionState.granted = new Set(['sales.opportunities.add']);
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { container } = render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(container.textContent).toBe('');
  });

  it('fix B4: renders nothing when the sales module is off', () => {
    moduleState.enabledModuleKeys = new Set(['order_management']);
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { container } = render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(container.textContent).toBe('');
  });

  it('fix B4: renders while the module list is still loading (fails open)', () => {
    moduleState.enabledModuleKeys = null;
    moduleState.isLoading = true;
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(screen.getByText('Opportunities')).toBeTruthy();
  });

  it('fix B4: hides Log opportunity (both the header and the empty state) without .add', () => {
    permissionState.granted = new Set(['sales.opportunities.view']);
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(screen.queryByRole('button', { name: /log opportunity/i })).toBeNull();
  });

  it('fix2 nit: the query only runs with view permission AND the module on', () => {
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(hooks.useCustomerOpportunities).toHaveBeenLastCalledWith('cust-1');
  });

  it('fix2 nit: the query does not run without sales.opportunities.view', () => {
    permissionState.granted = new Set(['sales.opportunities.add']);
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(hooks.useCustomerOpportunities).toHaveBeenLastCalledWith(null);
  });

  it('fix2 nit: the query does not run when the sales module is off', () => {
    moduleState.enabledModuleKeys = new Set(['order_management']);
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(hooks.useCustomerOpportunities).toHaveBeenLastCalledWith(null);
  });

  it('fix2 should-fix 3: the stage pill colours from stage_key', () => {
    hooks.useCustomerOpportunities.mockReturnValue({
      data: [
        {
          id: 'opp-1',
          opportunity_no: 'OPP-000001',
          title: 'ZZT Deal',
          stage_key: 'lost',
          stage_label: 'Lost',
          expected_amount: '1000.00',
          expected_close_date: '2026-11-01',
        },
      ],
      isLoading: false,
      isError: false,
    });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(screen.getByText('Lost').className).toMatch(/--color-destructive-soft/);
  });
});
