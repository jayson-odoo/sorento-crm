/**
 * CostPriceLinesTab (#1288, Lane A) - AC-S2-15: with the setting on, the review page is
 * the SAME layout with Submit for verification in place of Apply for the uploader, and
 * for a verifier the Decision column, Accept all, Return to submitter and Apply N
 * changes; a disabled Apply carries `apply_blocked_reason` as its tooltip. With the
 * setting off, none of these render.
 *
 * The component never re-derives the four-eyes rule itself - it renders exactly what
 * `changeSet.actions`/`verification_enabled` says (contract 1.4) - so every case here is
 * a different `changeSet` fixture, not a different mocked permission.
 *
 * Mocked at the hook boundary, same technique as `CostPriceLinesTab.test.tsx` (see that
 * file's header for why: the coder is mid-swap on `costPriceService.ts`).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { CostPriceChangeLine, CostPriceChangeSetDetail } from '../../types/costPrice.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/cost-price-uploads/set-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ placeholder }: { placeholder?: string }) => (
    <div data-testid="searchable-select-stub">{placeholder}</div>
  ),
}));

const mutateAsync = vi.fn().mockResolvedValue(undefined);
const mutation = () => ({ mutateAsync, isPending: false });

let linesData: CostPriceChangeLine[] = [];
vi.mock('../../hooks/useCostPriceChangeSets', () => ({
  useCostPriceChangeLines: () => ({ data: { data: linesData } }),
  usePatchCostPriceChangeLine: () => mutation(),
  useDecideCostPriceLine: () => mutation(),
  useDecideAllCostPriceLines: () => mutation(),
  useSubmitCostPriceChangeSet: () => mutation(),
  useReturnCostPriceChangeSet: () => mutation(),
  useApplyCostPriceChangeSet: () => mutation(),
}));

import { CostPriceLinesTab } from './CostPriceLinesTab';

function line(overrides: Partial<CostPriceChangeLine> = {}): CostPriceChangeLine {
  return {
    id: overrides.id ?? `line-${Math.random()}`,
    sheet: '19 series',
    row_no: 7,
    line_no: '1',
    supplier_code_raw: 'ZZT-001',
    supplier_code: 'ZZT-001',
    code_note: null,
    configuration: 'a configuration',
    flags: [],
    match_outcome: 'exact',
    match_rung: null,
    product: { id: 'p-1', product_code: 'ZZT-001', description: 'A product' },
    current_unit_cost: 100,
    current_currency: 'CNY',
    new_unit_cost: 110,
    change_pct: 10,
    line_state: 'changed',
    skipped: false,
    skip_reason: null,
    new_link_lead_time_days: null,
    decision: null,
    decision_reason: null,
    decided_by_name: null,
    stale: null,
    ...overrides,
  };
}

function changeSet(overrides: Partial<CostPriceChangeSetDetail> = {}): CostPriceChangeSetDetail {
  return {
    id: 'set-1',
    code: 'CPC-0001',
    status: 'draft',
    channel: 'staff_upload',
    supplier: { id: 'sup-1', supplier_code: 'ZZT-S', supplier_name: 'A Supplier' },
    currency: 'CNY',
    start_date: null,
    end_date: null,
    file_name: 'list.xlsx',
    has_source_file: true,
    sheets: [{ name: '19 series', header_row: 6, rows: 1, skipped_reason: null }],
    total_rows: 1,
    uploaded_by_name: 'Mei Ling',
    created_at: '2026-09-27T00:00:00',
    submitted_by_name: null,
    submitted_at: null,
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: null,
    applied_at: null,
    verified: null,
    verification_enabled: false,
    counts: {
      changed: 1, unchanged: 0, new_link: 0, unmatched: 0, duplicate_code: 0,
      needs_attention: 0, skipped: 0, accepted: 0, rejected: 0, undecided: 0,
    },
    largest_rise: null,
    actions: {
      can_apply: true, apply_blocked_reason: null, apply_count: 1,
      can_submit: false, can_decide: false, can_return: false, can_discard: true,
      decide_blocked_reason: null,
    },
    ...overrides,
  };
}

function renderTab(cs: CostPriceChangeSetDetail) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CostPriceLinesTab changeSet={cs} />
    </QueryClientProvider>,
  );
}

describe('AC-S2-15: verification off - none of the verification-only controls render', () => {
  it('the uploader sees only Apply N changes, no Submit, no Decision column, no Accept all/Return', () => {
    linesData = [line()];
    renderTab(
      changeSet({
        verification_enabled: false,
        status: 'draft',
        actions: {
          can_apply: true, apply_blocked_reason: null, apply_count: 1,
          can_submit: false, can_decide: false, can_return: false, can_discard: true,
          decide_blocked_reason: null,
        },
      }),
    );

    expect(screen.getByRole('button', { name: /Apply 1 change\b/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Submit for verification/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Decision' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Accept all/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Return to submitter/i })).not.toBeInTheDocument();
  });
});

describe('AC-S2-15: verification on - the uploader gets Submit in place of Apply', () => {
  it('a Draft staff set shows Submit for verification, not Apply, for the uploader', () => {
    linesData = [line()];
    renderTab(
      changeSet({
        verification_enabled: true,
        status: 'draft',
        channel: 'staff_upload',
        actions: {
          can_apply: false, apply_blocked_reason: 'submit for verification first', apply_count: 1,
          can_submit: true, can_decide: false, can_return: false, can_discard: true,
          decide_blocked_reason: null,
        },
      }),
    );

    expect(screen.getByRole('button', { name: /Submit for verification/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Apply 1 change\b/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Decision' })).not.toBeInTheDocument();
  });
});

describe('AC-S2-15: verification on, Pending - the verifier gets Decision, Accept all, Return and Apply', () => {
  it('renders the Decision column, Accept all, Return to submitter and a disabled Apply with its tooltip reason', () => {
    linesData = [line({ decision: null })];
    renderTab(
      changeSet({
        verification_enabled: true,
        status: 'pending_verification',
        channel: 'staff_upload',
        actions: {
          can_apply: false, apply_blocked_reason: '1 row still needs a decision', apply_count: 1,
          can_submit: false, can_decide: true, can_return: true, can_discard: false,
          decide_blocked_reason: null,
        },
      }),
    );

    expect(screen.getByRole('columnheader', { name: 'Decision' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Accept all/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Return to submitter/i })).toBeInTheDocument();

    const applyButton = screen.getByRole('button', { name: /Apply 1 change\b/i });
    expect(applyButton).toBeDisabled();
    expect(applyButton).toHaveAttribute('title', '1 row still needs a decision');
  });

  it('a resolved Pending set shows an enabled Apply with no tooltip', () => {
    linesData = [line({ decision: 'accepted' })];
    renderTab(
      changeSet({
        verification_enabled: true,
        status: 'pending_verification',
        channel: 'staff_upload',
        actions: {
          can_apply: true, apply_blocked_reason: null, apply_count: 1,
          can_submit: false, can_decide: true, can_return: true, can_discard: false,
          decide_blocked_reason: null,
        },
      }),
    );

    const applyButton = screen.getByRole('button', { name: /Apply 1 change\b/i });
    expect(applyButton).not.toBeDisabled();
    expect(applyButton).not.toHaveAttribute('title');
  });
});
