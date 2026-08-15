/**
 * `TermsByKindSection` — S7b Phase 2c gate.
 *
 * Group 1 item 4 (AC-P4): every Term under a Kind is listed together with a
 * divider between kind groups; an empty group list renders the empty state,
 * not a bare heading.
 *
 * Group 1 item 3, term half (AC-P8a): deleting a Term whose assessments
 * already exist warns that those assessments SURVIVE the delete (historical
 * record, not a cascade victim) — both branches of the copy are asserted.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const hooks = vi.hoisted(() => ({
  useTermsGroupedByKind: vi.fn(),
  useKindOptions: vi.fn(),
  useCreateTerm: vi.fn(),
  useUpdateTerm: vi.fn(),
  useDeleteTerm: vi.fn(),
  useDefectTypes: vi.fn(),
}));
vi.mock('../hooks/useWarrantyConfig', () => hooks);

import { TermsByKindSection } from './TermsByKindSection';
import type { WarrantyTermRow, WarrantyTermsGrouped } from '../types/warranty-config.types';

function term(over: Partial<WarrantyTermRow>): WarrantyTermRow {
  return {
    id: 'term-1',
    policy_id: 'pol-1',
    kind_id: 'kind-1',
    kind_code: 'water_closet',
    kind_name: 'Water Closet',
    part_name: 'Ceramic body',
    duration_months: null,
    is_lifetime: true,
    covered_defect_type_ids: null,
    covered_defect_type_labels: null,
    installation_included: true,
    registration_bonus_months: null,
    qualifications: null,
    exclusions: null,
    assessment_count: 0,
    ...over,
  };
}

const CERAMIC = term({ id: 'term-ceramic', kind_id: 'kind-wc', kind_name: 'Water Closet', part_name: 'Ceramic body' });
const FLUSH = term({ id: 'term-flush', kind_id: 'kind-wc', kind_name: 'Water Closet', part_name: 'Flushing fittings', is_lifetime: false, duration_months: 24 });
const MIRROR = term({ id: 'term-mirror', kind_id: 'kind-mc', kind_name: 'Mirror Cabinet', part_name: 'Hinge', is_lifetime: false, duration_months: 12 });

const deleteMutate = vi.fn().mockResolvedValue(undefined);

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TermsByKindSection policyId="pol-1" />
    </QueryClientProvider>,
  );
}

function grouped(groups: WarrantyTermsGrouped['groups']): WarrantyTermsGrouped {
  return { groups, total: groups.reduce((n, g) => n + g.terms.length, 0) };
}

beforeEach(() => {
  Object.values(hooks).forEach((f) => f.mockReset());
  deleteMutate.mockClear();
  hooks.useKindOptions.mockReturnValue({ data: [] });
  hooks.useDefectTypes.mockReturnValue({ data: [] });
  hooks.useCreateTerm.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useUpdateTerm.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeleteTerm.mockReturnValue({ mutateAsync: deleteMutate, isPending: false });
});

describe('TermsByKindSection — AC-P4: terms grouped under their kind, with a divider between groups', () => {
  it('renders one group-header divider per kind, labelled with the kind name, in the order the API sent them', () => {
    hooks.useTermsGroupedByKind.mockReturnValue({
      data: grouped([
        { kind: { id: 'kind-wc', code: 'water_closet', name: 'Water Closet' }, terms: [CERAMIC, FLUSH] },
        { kind: { id: 'kind-mc', code: 'mirror_cabinet', name: 'Mirror Cabinet' }, terms: [MIRROR] },
      ]),
      isLoading: false,
      isError: false,
      error: null,
    });
    renderSection();

    // `data-group-label` is only set by the non-draggable DataGridTable variant;
    // `columnsDraggable` defaults to true, so the DnD variant (which does not
    // set that attribute) is what actually renders here — assert on the
    // divider's own text instead, which is correct for either variant.
    const dividers = screen.getAllByTestId('data-grid-group-header');
    expect(dividers).toHaveLength(2);
    expect(dividers[0]).toHaveTextContent('Water Closet');
    expect(dividers[1]).toHaveTextContent('Mirror Cabinet');

    // Both terms under Water Closet render as rows, under ONE divider.
    expect(screen.getByText('Ceramic body')).toBeInTheDocument();
    expect(screen.getByText('Flushing fittings')).toBeInTheDocument();
    expect(screen.getByText('Hinge')).toBeInTheDocument();
  });

  it('an empty group list renders the empty state, not a bare heading', () => {
    hooks.useTermsGroupedByKind.mockReturnValue({
      data: grouped([]),
      isLoading: false,
      isError: false,
      error: null,
    });
    renderSection();

    expect(screen.getByText(/No terms under this policy yet/i)).toBeInTheDocument();
    expect(screen.queryAllByTestId('data-grid-group-header')).toHaveLength(0);
  });
});

describe('TermsByKindSection — AC-P8a: deleting a Term names whether assessments survive it', () => {
  it('a Term with assessments warns that they will be KEPT (not lost)', async () => {
    const withAssessments = term({
      id: 'term-quoted',
      kind_name: 'Mirror Cabinet',
      part_name: 'Ceramic body',
      assessment_count: 5,
    });
    hooks.useTermsGroupedByKind.mockReturnValue({
      data: grouped([{ kind: { id: 'kind-mc', code: 'mirror_cabinet', name: 'Mirror Cabinet' }, terms: [withAssessments] }]),
      isLoading: false,
      isError: false,
      error: null,
    });
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: /Delete term/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('5')).toBeInTheDocument();
    expect(within(dialog).getByText(/will be kept/i)).toBeInTheDocument();
  });

  it('a Term with no assessments states plainly that none quote it', async () => {
    const clean = term({ id: 'term-clean', kind_name: 'Mirror Cabinet', part_name: 'Hinge', assessment_count: 0 });
    hooks.useTermsGroupedByKind.mockReturnValue({
      data: grouped([{ kind: { id: 'kind-mc', code: 'mirror_cabinet', name: 'Mirror Cabinet' }, terms: [clean] }]),
      isLoading: false,
      isError: false,
      error: null,
    });
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: /Delete term/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/No assessment quotes it/i)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: /^Delete$/i }));
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('term-clean'));
  });
});
