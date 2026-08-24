/**
 * PromotionsList - expiry-batch deep link behaviour.
 *
 * Verifies the `?expiry_notify_batch_id=` deep link filters the list query,
 * renders the dismissable banner, and that Clear strips the param
 * (router.replace to the bare pathname).
 *
 * The data hooks / services and next/navigation are mocked. NOTE: the shared
 * DataGrid never settles past its skeleton rows under jsdom (it depends on
 * layout measurement absent there), so row selection + the Compile-PDF bulk
 * action can't be exercised at component level - that path is covered by
 * `useCompilePromotionsPdf.test.tsx` (mutation → ordered ids, toast, invalidate)
 * and by the Playwright spec `e2e/promo-expiry-compile.spec.ts`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ---- next/navigation ----
const push = vi.fn();
const replace = vi.fn();
let searchParamValue: string | null = null;
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => '/marketing-management/promotions',
  useSearchParams: () => ({ get: (k: string) => (k === 'expiry_notify_batch_id' ? searchParamValue : null) }),
}));

// ---- data hooks / services ----
const getPromotions = vi.fn();
vi.mock('../services/promotionService', () => ({
  getPromotions: (...a: unknown[]) => getPromotions(...a),
}));
const compileMutate = vi.fn();
vi.mock('../hooks/usePromotions', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useCompilePromotionsPdf: () => ({ mutate: compileMutate, isPending: false }),
  };
});
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: new Set(['marketing']), isLoading: false }),
}));
vi.mock(
  '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes',
  () => ({ useContactAccessTypes: () => ({ data: [] }) }),
);
// The Resubmit bulk action is permission-gated; the real hook needs a NextAuth
// SessionProvider that these tests deliberately don't mount. The slug is captured
// rather than ignored - a mock that blindly returns true hides a misspelt slug,
// which silently removes the action for everyone.
const hasPermission = vi.fn(() => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
}));

import PromotionsList from './PromotionsList';

const ROWS = [
  {
    id: 'promo-1',
    description: 'Sorento Sale',
    access_levels: ['sorento_dealer'],
    is_active: true,
    products_count: 2,
    attachments: [],
    created_at: '2026-06-01T00:00:00Z',
    start_date: '2026-06-01',
    end_date: '2026-07-01',
  },
  {
    id: 'promo-2',
    description: 'Cabana Clearance',
    access_levels: ['cabana_office'],
    is_active: true,
    products_count: 0,
    attachments: [],
    created_at: '2026-06-02T00:00:00Z',
    start_date: '2026-06-02',
    end_date: '2026-07-02',
  },
];

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PromotionsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamValue = null;
  getPromotions.mockResolvedValue({ data: ROWS, pagination: { total: ROWS.length } });
  // jsdom gaps used by Radix / DataGrid.
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('PromotionsList - expiry batch deep link', () => {
  it('renders the banner and passes the batch id into the query when deep-linked', async () => {
    searchParamValue = 'batch-123';
    renderList();

    expect(
      await screen.findByText(/Showing promotions from a recent expiry-reminder batch/i),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(getPromotions).toHaveBeenCalledWith(
        expect.objectContaining({ expiry_notify_batch_id: 'batch-123' }),
      ),
    );
  });

  it('Clear strips the batch param (router.replace to the bare pathname)', async () => {
    searchParamValue = 'batch-123';
    renderList();
    const clearBtn = await screen.findByRole('button', { name: /^clear$/i });
    fireEvent.click(clearBtn);
    expect(replace).toHaveBeenCalledWith('/marketing-management/promotions');
  });

  it('no banner and no batch id when the deep link param is absent', async () => {
    searchParamValue = null;
    renderList();
    await waitFor(() => expect(getPromotions).toHaveBeenCalled());
    expect(
      screen.queryByText(/Showing promotions from a recent expiry-reminder batch/i),
    ).not.toBeInTheDocument();
    expect(getPromotions).toHaveBeenCalledWith(
      expect.objectContaining({ expiry_notify_batch_id: undefined }),
    );
  });
});

describe('PromotionsList - Resubmit gate', () => {
  it('gates on a slug the backend registry actually issues', async () => {
    // `marketing.promotions.update` does not exist - `_crud` emits view/add/edit/
    // delete. Asking for a slug nobody holds silently drops the action from the
    // toolbar, which looks like the feature was never built.
    renderList();
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
    expect(hasPermission).toHaveBeenCalledWith('marketing.promotions.edit');
  });
});
