/**
 * SPARE-PART-OR-B C, red-first (Phase 2). C4.1: Revise opens the SAME edit form as Create, in
 * revision mode (owner standing rule: "Edit opens the same form as Create").
 * Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md.
 *
 * NAMED CONTRACT CHOICES (the UAC leaves them open):
 * 1. Pressing Revise opens the revision (the existing POST) and then navigates to
 *    `${SPARE_PART_REQUESTS_PATH}/{id}/edit`.
 * 2. While a revision is a draft (`revision_state: 'draft'`, `can_edit`), the header offers an
 *    "Edit" link to that same form beside Submit.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/spare-part-requests/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

const apiFetch = vi.fn(
  async () =>
    new Response(JSON.stringify({ id: 'oi-1', revision_state: 'draft' }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...(a as [])) }));

import { SparePartRequestActions } from './SparePartRequestActions';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

const EDIT_PATH = '/procurement-management/spare-part-requests/oi-1/edit';

function header(over: Record<string, unknown>): OrderInquiryHeaderDetail {
  return {
    id: 'oi-1',
    inquiry_no: 'OR-2611-0007',
    oi_no: 'OI-2611-0003',
    inquiry_type: 'spare_part_request',
    state: 'raised',
    revision_state: null,
    currency: 'MYR',
    can_edit: false,
    can_decide: false,
    can_revise: true,
    raise_history: [],
    ...over,
  } as unknown as OrderInquiryHeaderDetail;
}

const ROWS = [
  { id: 'row-1', verb: 'REPLENISH', state: 'raised', item_code: 'SP-SEAL-40', qty: '10' },
] as unknown as OrderInquiryWorklistRow[];

function mount(h: OrderInquiryHeaderDetail) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestActions header={h} rows={ROWS} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('C4.1: Revise opens the edit form', () => {
  it('pressing Revise opens the revision and goes to the edit form', async () => {
    mount(header({}));
    fireEvent.click(screen.getByRole('button', { name: 'Revise' }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    await waitFor(() => expect(push).toHaveBeenCalledWith(EDIT_PATH));
  });

  it('an open revision draft offers Edit, linking to the same form', () => {
    mount(header({ can_revise: false, can_edit: true, revision_state: 'draft' }));
    const edit = screen.getByRole('link', { name: 'Edit' });
    expect(edit.getAttribute('href')).toBe(EDIT_PATH);
    expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument();
  });
});
