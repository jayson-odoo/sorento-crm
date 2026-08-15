/**
 * `WarrantyPolicyDetailPage` header actions - Phase 3 review, AC-P26 finding 2
 * (detail page half).
 *
 * Mirrors `PoliciesTab.supersedeHiddenWhenClosed.test.tsx` for the OTHER place
 * the Supersede action is rendered (AC-P21). Both surfaces must agree: a
 * closed policy (`effective_to` set) cannot be superseded by any date, so the
 * header action is hidden there too, not merely in the grid row.
 */
import { Suspense } from 'react';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/app/providers/CompanyProvider', () => ({
  useCompany: () => ({ activeCompany: { id: 'company-1', name: 'Sorento' } }),
}));

// The Terms section pulls in its own set of hooks unrelated to this gate;
// stubbed so this file only exercises the header actions.
vi.mock('../../components/TermsByKindSection', () => ({
  TermsByKindSection: () => <div data-testid="terms-section-stub" />,
}));

const hooks = vi.hoisted(() => ({
  usePolicy: vi.fn(),
  useUpdatePolicy: vi.fn(),
  useSupersedePolicy: vi.fn(),
  useDeletePolicy: vi.fn(),
}));
vi.mock('../../hooks/useWarrantyConfig', () => hooks);

import WarrantyPolicyDetailPage from './page';
import type { WarrantyPolicyRow } from '../../types/warranty-config.types';

function policy(over: Partial<WarrantyPolicyRow>): WarrantyPolicyRow {
  return {
    id: 'pol-1',
    version: 'v15',
    effective_from: '2000-01-01',
    effective_to: null,
    policy_text: null,
    source_attachment_name: null,
    term_count: 0,
    created_at: '2000-01-01T00:00:00',
    updated_at: null,
    ...over,
  };
}

beforeEach(() => {
  Object.values(hooks).forEach((f) => f.mockReset());
  hooks.useUpdatePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useSupersedePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeletePolicy.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

async function renderDetail(data: WarrantyPolicyRow) {
  hooks.usePolicy.mockReturnValue({ data, isLoading: false, isError: false, error: null });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // `use(params)` suspends until the promise settles; the test supplies its
  // own Suspense boundary and flushes it inside `act`, same as
  // `consumer360.test.tsx`.
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Suspense fallback={<div>loading</div>}>
          <WarrantyPolicyDetailPage params={Promise.resolve({ id: 'pol-1' })} />
        </Suspense>
      </QueryClientProvider>,
    );
  });
}

describe('WarrantyPolicyDetailPage - AC-P21/AC-P26 finding 2: Supersede is not offered on an already-closed policy', () => {
  it('a CLOSED policy (effective_to set) does not render a Supersede header action', async () => {
    await renderDetail(policy({ version: 'v14', effective_to: '2025-12-31' }));

    expect(screen.queryByRole('button', { name: /^Supersede$/i })).not.toBeInTheDocument();
    // The lifecycle facts are still stated in place of the removed action, so
    // this is not a silent gap.
    expect(screen.getByText('v14')).toBeInTheDocument();
  });

  it('an OPEN ENDED policy (positive control) still renders a Supersede header action', async () => {
    await renderDetail(policy({ version: 'v15', effective_to: null }));

    expect(screen.getByRole('button', { name: /^Supersede$/i })).toBeInTheDocument();
  });
});
