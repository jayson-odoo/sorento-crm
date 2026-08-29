/**
 * S3-02, and the tester's run 3B finding: Next on an EDIT screen must land on the
 * next record's EDIT screen.
 *
 * The five forms that carry a pager step between edit screens, not from an edit
 * screen back into a read-only one - somebody working down a list of records is
 * mid-task, and being dropped into the view of the next one means opening Edit
 * again for every single record. `hrefFor` is what keeps them there, and it is a
 * prop each form has to remember to pass, so each form is pinned here.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { useListPager, type ListPagerPage } from '@/hooks/useListPager';

const push = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(search),
}));

const PAGE: ListPagerPage = {
  data: [{ id: 'r1' }, { id: 'r2' }],
  pagination: { total: 2 },
};

const listQueryKey = () => ['edit-form-list'];
const fetchPage = vi.fn(async () => PAGE);

let client: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

/**
 * Exactly what each form passes: the entity's detail path plus the `hrefFor` the
 * form declares. Kept as data so a form that drops the prop fails here.
 */
const EDIT_FORMS: Array<{
  form: string;
  detailPath: string;
  hrefFor: (id: string, search: string) => string;
  expected: string;
}> = [
  {
    form: 'CustomerForm',
    detailPath: '/order-management/customers',
    hrefFor: (id, s) => `/order-management/customers/${id}/edit${s ? `?${s}` : ''}`,
    expected: '/order-management/customers/r2/edit?page=1&limit=25',
  },
  {
    form: 'ProductForm',
    detailPath: '/master-data-management/products',
    hrefFor: (id, s) => `/master-data-management/products/${id}/edit${s ? `?${s}` : ''}`,
    expected: '/master-data-management/products/r2/edit?page=1&limit=25',
  },
  {
    form: 'SupplierForm',
    detailPath: '/procurement-management/suppliers',
    hrefFor: (id, s) => `/procurement-management/suppliers/${id}/edit${s ? `?${s}` : ''}`,
    expected: '/procurement-management/suppliers/r2/edit?page=1&limit=25',
  },
  {
    form: 'PromotionForm',
    detailPath: '/marketing-management/promotions',
    hrefFor: (id, s) => `/marketing-management/promotions/${id}/edit${s ? `?${s}` : ''}`,
    expected: '/marketing-management/promotions/r2/edit?page=1&limit=25',
  },
  {
    form: 'ComplaintForm',
    detailPath: '/complaint-management/complaints',
    hrefFor: (id, s) => `/complaint-management/complaints/${id}/edit${s ? `?${s}` : ''}`,
    expected: '/complaint-management/complaints/r2/edit?page=1&limit=25',
  },
];

beforeEach(() => {
  push.mockReset();
  fetchPage.mockClear();
  search = 'page=1&limit=25';
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(listQueryKey(), PAGE);
});

describe('the edit forms keep the edit route when the pager steps', () => {
  it.each(EDIT_FORMS)('$form', ({ detailPath, hrefFor, expected }) => {
    const { result } = renderHook(
      () => useListPager({ listQueryKey, fetchPage, detailPath, currentId: 'r1', hrefFor }),
      { wrapper },
    );

    act(() => result.current.goNext());

    expect(push).toHaveBeenCalledWith(expected);
  });

  /**
   * The table above proves the hook honours `hrefFor`. This proves the five forms
   * still pass one, which is the half that actually regressed: a form that drops
   * the prop compiles, renders, and silently sends an editing user to a read-only
   * page.
   */
  it.each([
    'app/(protected)/order-management/customers/components/CustomerForm.tsx',
    'app/(protected)/master-data-management/products/components/ProductForm.tsx',
    'app/(protected)/procurement-management/suppliers/components/SupplierForm.tsx',
    'app/(protected)/marketing-management/promotions/components/PromotionForm.tsx',
    'app/(protected)/complaint-management/complaints/components/ComplaintForm.tsx',
  ])('%s passes an hrefFor that keeps /edit', (file) => {
    const source = readFileSync(resolve(process.cwd(), file), 'utf8');
    const pager = source.slice(source.indexOf('<ListPager'));
    const props = pager.slice(0, pager.indexOf('/>'));

    expect(props).toContain('hrefFor');
    expect(props).toContain('/edit');
  });

  it('without hrefFor the same step lands on the read-only record', () => {
    const { result } = renderHook(
      () =>
        useListPager({
          listQueryKey,
          fetchPage,
          detailPath: '/order-management/customers',
          currentId: 'r1',
        }),
      { wrapper },
    );

    act(() => result.current.goNext());

    expect(push).toHaveBeenCalledWith('/order-management/customers/r2?page=1&limit=25');
  });
});
