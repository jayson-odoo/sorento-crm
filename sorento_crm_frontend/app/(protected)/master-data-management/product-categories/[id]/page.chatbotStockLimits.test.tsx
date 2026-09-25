/**
 * Blocking 1 (reviewer pass, PR #1221, 85c2e9e7) named three surfaces to guard: the
 * CategoryForm modal (create + edit), ProductForm, and this page - the category
 * detail's inline edit, which is the actual "view = edit" surface for an EXISTING
 * category (`CategoriesList.tsx` never opens `CategoryForm` in edit mode; the tree
 * row opens this page instead, per the plan's dated note, PLAN line 166).
 *
 * This page's own null/zero mapping (`draft.chatbot_max_qty.trim() ? Number(...) :
 * null`) was already correct before the fix round - unlike the two zod schemas, it
 * never went through `z.coerce.number()` - but the review asked for a vitest per
 * form covering this surface too, so a future edit here cannot regress it silently.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

const CAT_ID = '11111111-1111-1111-1111-111111111111';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => `/master-data-management/product-categories/${CAT_ID}`,
}));

// `Container` reads `useSettings()`, which throws outside a `SettingsProvider`
// (`providers/settings-provider.tsx`) - stub it to a passthrough div, the same
// pattern other detail-page tests use, since settings are not this test's subject.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const updateMutateAsync = vi.fn().mockResolvedValue({});
const useCategoryMock = vi.fn();
vi.mock('../hooks/useProductCategories', () => ({
  useCategoriesTree: () => ({ data: [] }),
  useCategory: (id: string | null) => useCategoryMock(id),
  useUpdateCategory: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
}));

vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({
    pending: null,
    isPending: false,
    isBlocked: false,
    start: vi.fn(),
    cancel: vi.fn(),
    countdown: null,
  }),
}));

const permissionState = { view: true, edit: true };
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => {
    if (slug === 'master_data.chatbot_stock_limits.view') return permissionState.view;
    if (slug === 'master_data.chatbot_stock_limits.edit') return permissionState.edit;
    return false;
  },
}));

import ProductCategoryDetailPage from './page';

const LIVE_CATEGORY = {
  id: CAT_ID,
  category_code: 'CAT1',
  category_name: 'Category 1',
  description: '',
  is_active: true,
  is_searchable: true,
  display_order: 0,
  parent_category_id: null,
  chatbot_max_qty: 40,
  chatbot_eta_offset_days: 6,
};

function makeParams() {
  return Promise.resolve({ id: CAT_ID });
}

// `params` is a Promise `use()` unwraps (React 19); the resolution finishing
// after `render()` returns is an update React needs wrapped in `act()` to
// flush before the test can find anything the resolved page renders.
async function renderPage() {
  await act(async () => {
    render(
      <Suspense fallback={null}>
        <ProductCategoryDetailPage params={makeParams()} />
      </Suspense>,
    );
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  permissionState.view = true;
  permissionState.edit = true;
  useCategoryMock.mockReturnValue({ data: LIVE_CATEGORY, isLoading: false });
});

describe('ProductCategoryDetailPage - chatbot stock-limit inline edit submit (Blocking 1)', () => {
  it('clearing both fields submits null, not 0', async () => {
    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));

    fireEvent.change(screen.getByLabelText('Max quantity (assistant)'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('ETA offset (days)'), { target: { value: '' } });

    fireEvent.click(screen.getByRole('button', { name: /Save category/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const payload = updateMutateAsync.mock.calls[0][0].data;
    expect(payload.chatbot_max_qty).toBeNull();
    expect(payload.chatbot_eta_offset_days).toBeNull();
  });

  it('typing 0 in both fields submits 0, not null', async () => {
    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));

    fireEvent.change(screen.getByLabelText('Max quantity (assistant)'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('ETA offset (days)'), { target: { value: '0' } });

    fireEvent.click(screen.getByRole('button', { name: /Save category/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const payload = updateMutateAsync.mock.calls[0][0].data;
    expect(payload.chatbot_max_qty).toBe(0);
    expect(payload.chatbot_eta_offset_days).toBe(0);
  });

  it('saving with the values untouched submits them unchanged', async () => {
    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/ }));
    fireEvent.click(screen.getByRole('button', { name: /Save category/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const payload = updateMutateAsync.mock.calls[0][0].data;
    expect(payload.chatbot_max_qty).toBe(40);
    expect(payload.chatbot_eta_offset_days).toBe(6);
  });
});
