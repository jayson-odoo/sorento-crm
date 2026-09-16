/**
 * PLAN-portal-forms-market-segment AC-M1/AC-M2: the "Additional portal
 * forms" column and field on the Market Segments admin.
 *
 * The group source for a portal form grant moved here from Contact Access
 * Types (D1) - this file replaces the retired
 * `ContactAccessTypesAdmin.portalForms.test.tsx`, re-pointed at the new
 * owner and re-scoped to the r2 ruling (D3/D4): every contact already gets
 * the four legacy kinds by default, so a segment only offers kinds BEYOND
 * that base (today: Price Tag Request alone), labelled "Additional portal
 * forms" rather than "Portal forms".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/market-segments',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

// DataGrid persists column prefs via this hook (fires network) - stub it, or the
// grid renders skeletons forever and no row can be asserted.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// D7: delete is a server-deferred pending action, not a confirm dialog - the
// component calls this unconditionally, so it needs a mock even though this
// file never exercises delete.
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn().mockResolvedValue({
    id: 'pa-1',
    action_key: 'market_segment.delete',
    entity_type: 'market_segment',
    entity_id: 'retail',
    commit_at: '2026-08-30T10:00:10',
    window_seconds: 10,
  }),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

const useMarketSegments = vi.fn();
const create = { mutate: vi.fn(), isPending: false };
const update = { mutate: vi.fn(), isPending: false };
const remove = { mutate: vi.fn(), isPending: false };
vi.mock('../hooks/useMarketSegments', () => ({
  useMarketSegments: (...a: unknown[]) => useMarketSegments(...a),
  useMarketSegmentMutations: () => ({ create, update, remove }),
}));

import MarketSegmentsAdmin from './MarketSegmentsAdmin';

const ROWS = [
  {
    code: 'retail',
    name: 'Retail',
    description: 'Walk-in buyers',
    is_active: true,
    sort_order: 1,
    is_requestor_selectable: false,
    portal_form_types: ['price_tag_request'],
  },
  {
    code: 'project',
    name: 'Project',
    description: null,
    is_active: true,
    sort_order: 2,
    is_requestor_selectable: false,
    portal_form_types: [],
  },
];

function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <MarketSegmentsAdmin />
    </QueryClientProvider>,
  );
}

function mockState(data: unknown[]) {
  useMarketSegments.mockReturnValue({ data, isLoading: false, isError: false });
}

const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);

async function openRetailDialog() {
  render();
  await screen.findByText('Retail');
  const editButtons = screen.getAllByLabelText('Edit');
  fireEvent.click(editButtons[0]);
  await screen.findByText('Edit market segment');
}

beforeEach(() => {
  vi.clearAllMocks();
  mockState(ROWS);
  create.mutate.mockReset();
  update.mutate.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('MarketSegmentsAdmin - the Additional portal forms column', () => {
  it('draws one chip per granted kind, labelled as the portal labels it', async () => {
    render();
    await screen.findByText('Retail');

    expect(screen.getByText('Price Tag Request')).toBeInTheDocument();
  });

  it('reads as a dash for a segment granted nothing extra', async () => {
    render();
    await screen.findByText('Project');

    // Two rows exist; the dash belongs to Project's own cell, not Retail's.
    const dashes = screen.getAllByText('-');
    expect(dashes.length).toBeGreaterThan(0);
  });
});

describe('MarketSegmentsAdmin - the Additional portal forms field', () => {
  it('offers only the kinds beyond the base four (today: Price Tag Request)', async () => {
    await openRetailDialog();
    openMenu();

    await waitFor(() =>
      expect(screen.getAllByText('Price Tag Request').length).toBeGreaterThan(0),
    );
    for (const label of ['Complaint', 'Stock Inquiry', 'Purchase Request', 'Sponsorship Form']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it('opens with the row current kinds already selected', async () => {
    await openRetailDialog();

    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]')!;
    expect(trigger.textContent).toContain('Price Tag Request');
  });

  it('opens empty for a segment granted nothing extra', async () => {
    render();
    await screen.findByText('Project');
    const editButtons = screen.getAllByLabelText('Edit');
    fireEvent.click(editButtons[1]);
    await screen.findByText('Edit market segment');

    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]')!;
    expect(trigger.textContent).not.toContain('Price Tag Request');
  });

  it('submits the chosen codes when the grant is added', async () => {
    render();
    await screen.findByText('Project');
    const editButtons = screen.getAllByLabelText('Edit');
    fireEvent.click(editButtons[1]);
    await screen.findByText('Edit market segment');
    openMenu();

    await waitFor(() =>
      expect(screen.getAllByText('Price Tag Request').length).toBeGreaterThan(0),
    );
    // Retail's own row badge (background, behind the dialog) also reads
    // "Price Tag Request" - the LAST match is always the popover's own
    // option, list badge or not.
    const options = screen.getAllByText('Price Tag Request');
    fireEvent.click(options[options.length - 1]);
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(update.mutate).toHaveBeenCalled());
    const [{ code, body }] = update.mutate.mock.calls[0];
    expect(code).toBe('project');
    expect(body.portal_form_types).toEqual(['price_tag_request']);
  });

  it('submits the empty list when the grant is taken back', async () => {
    await openRetailDialog();
    openMenu();

    await waitFor(() =>
      expect(screen.getAllByText('Price Tag Request').length).toBeGreaterThan(0),
    );
    // The last match is the option row; the first is the trigger chip.
    const options = screen.getAllByText('Price Tag Request');
    fireEvent.click(options[options.length - 1]);
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(update.mutate).toHaveBeenCalled());
    expect(update.mutate.mock.calls[0][0].body.portal_form_types).toEqual([]);
  });

  it('a new segment is created with no additional portal forms unless one is picked', async () => {
    render();
    await screen.findByText('Retail');
    fireEvent.click(screen.getByRole('button', { name: /add segment/i }));
    await screen.findByText('Add market segment');

    fireEvent.change(screen.getByLabelText('Code'), { target: { value: 'zzt_new' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'ZZT New' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(create.mutate).toHaveBeenCalled());
    expect(create.mutate.mock.calls[0][0].portal_form_types).toEqual([]);
  });
});
