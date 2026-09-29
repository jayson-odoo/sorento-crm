/**
 * CostPriceChangeSetDetail header, fix lane round 6 R1 (#1288, PR #1305). The owner, 28 Sep
 * 2026: "why the download file and discard is at the top scattered there, it should be Apply
 * 228 changes as call to action, the download file and discard as dropdown buttons in gear
 * button". Apply N changes is the one primary button top right, running the same action as
 * the footer bar; Download file and Discard live in the gear (DetailActions, D6); Discard
 * keeps its deferred countdown.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { CostPriceChangeSetDetail as CostPriceChangeSetDetailType } from '../../types/costPrice.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/cost-price-uploads/set-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const discardStart = vi.fn();
let discardCountdown: React.ReactNode = null;
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ countdown: discardCountdown, start: discardStart }),
}));

const downloadSource = vi.fn();
vi.mock('../../services/costPriceService', () => ({
  downloadCostPriceSourceFile: (...args: unknown[]) => downloadSource(...args),
}));

vi.mock('./CostPriceHistoryTab', () => ({
  CostPriceHistoryTab: () => <div data-testid="history-stub" />,
}));
vi.mock('./CostPriceLinesTab', () => ({
  CostPriceLinesTab: () => <div data-testid="lines-stub" />,
}));

const applyMutate = vi.fn();
const submitMutate = vi.fn();
let detail: CostPriceChangeSetDetailType;
vi.mock('../../hooks/useCostPriceChangeSets', () => ({
  useCostPriceChangeSet: () => ({ data: detail, isLoading: false }),
  useRefreshCostPricePrices: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useApplyCostPriceChangeSet: () => ({ mutateAsync: applyMutate, isPending: false }),
  useSubmitCostPriceChangeSet: () => ({ mutateAsync: submitMutate, isPending: false }),
  costPriceChangeSetsPagerQuery: {
    listQueryKey: () => ['cost-price-change-sets-pager'],
    fetchPage: async () => ({ ids: ['set-1'], hasNextPage: false }),
  },
}));

import { CostPriceChangeSetDetail } from './CostPriceChangeSetDetail';

function makeDetail(overrides: Partial<CostPriceChangeSetDetailType> = {}): CostPriceChangeSetDetailType {
  return {
    id: 'set-1',
    code: 'CPC-0002',
    status: 'pending_verification',
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
    submitted_by_name: 'Mei Ling',
    submitted_at: '2026-09-27T00:05:00',
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: null,
    applied_at: null,
    verified: null,
    verification_enabled: true,
    counts: {
      changed: 0, unchanged: 0, new_link: 0, unmatched: 0, duplicate_code: 0,
      needs_attention: 0, skipped: 0, accepted: 0, rejected: 0, undecided: 0,
    },
    largest_rise: null,
    actions: {
      can_apply: false, apply_blocked_reason: null, apply_count: 0,
      can_submit: false, can_decide: true, can_return: true, can_discard: false,
      decide_blocked_reason: null,
    },
    ...overrides,
  };
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CostPriceChangeSetDetail changeSetId="set-1" />
    </QueryClientProvider>,
  );
}


function draft(overrides: Partial<CostPriceChangeSetDetailType> = {}) {
  return makeDetail({
    status: 'draft',
    verification_enabled: false,
    actions: {
      can_apply: true, apply_blocked_reason: null, apply_count: 228,
      can_submit: false, can_decide: false, can_return: false, can_discard: true,
      decide_blocked_reason: null,
    },
    ...overrides,
  });
}

describe('R1: Apply N changes is the header call to action, the rest sits in the gear', () => {
  it('renders Apply 228 changes as the primary button and runs apply', () => {
    detail = draft();
    discardCountdown = null;
    renderDetail();
    const apply = screen.getByRole('button', { name: 'Apply 228 changes' });
    fireEvent.click(apply);
    expect(applyMutate).toHaveBeenCalled();
  });

  it('keeps Download file and Discard out of the header until the gear opens', async () => {
    detail = draft();
    discardCountdown = null;
    renderDetail();
    expect(screen.queryByRole('button', { name: 'Download file' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole('button', { name: 'Actions' }), { key: 'Enter' });
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'Download file' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Discard' })).toBeInTheDocument();
  });

  it('Download file in the gear runs the download', async () => {
    detail = draft();
    discardCountdown = null;
    renderDetail();
    fireEvent.keyDown(screen.getByRole('button', { name: 'Actions' }), { key: 'Enter' });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Download file' }));
    expect(downloadSource).toHaveBeenCalledWith('set-1');
  });

  it('Discard in the gear starts the deferred countdown, no dialog', async () => {
    detail = draft();
    discardCountdown = null;
    renderDetail();
    fireEvent.keyDown(screen.getByRole('button', { name: 'Actions' }), { key: 'Enter' });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Discard' }));
    expect(discardStart).toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('while Discard counts down, its countdown stands where Apply stood', () => {
    detail = draft();
    discardCountdown = <button type="button">Cancel discard</button>;
    renderDetail();
    expect(screen.getByRole('button', { name: 'Cancel discard' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Apply 228 changes' })).not.toBeInTheDocument();
    discardCountdown = null;
  });

  it('with verification on, the header call to action is Submit for verification', () => {
    detail = draft({
      verification_enabled: true,
      actions: { ...draft().actions, can_apply: false, can_submit: true },
    });
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: 'Submit for verification' }));
    expect(submitMutate).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /^Apply/ })).not.toBeInTheDocument();
  });

  it('an applied set has no call to action, only the gear with Download file', async () => {
    detail = draft({ status: 'applied', actions: { ...draft().actions, can_apply: false, can_discard: false } });
    renderDetail();
    expect(screen.queryByRole('button', { name: /^Apply/ })).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('button', { name: 'Actions' }), { key: 'Enter' });
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'Download file' })).toBeInTheDocument();
    expect(within(menu).queryByRole('menuitem', { name: 'Discard' })).not.toBeInTheDocument();
  });
});
