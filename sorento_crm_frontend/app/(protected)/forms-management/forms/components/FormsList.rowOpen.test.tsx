/**
 * S3-01, D3 - a form row opens the form.
 *
 * The tester's Run 2A found no navigation on a Forms row click, with the row menu
 * holding Delete alone: on that screen a record could not be opened at all. This
 * pins the row as the way in - the whole row, by mouse and by keyboard - and the
 * href it carries.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/forms-management/forms',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const FORM = {
  id: 'form-1',
  code: 'FRM-001',
  name: 'Warranty claim',
  form_type: 'marketing',
  purpose: 'claim',
  language: 'en',
  version: 1,
  is_active: true,
  updated_at: '2026-02-01T00:00:00',
};

vi.mock('../hooks/useForms', () => ({
  useForms: () => ({
    data: { data: [FORM], pagination: { total: 1, page: 1 } },
    isLoading: false,
    refetch: vi.fn(),
    isFetching: false,
  }),
  useDeleteForm: () => ({ mutate: vi.fn(), isPending: false }),
  useBulkDeleteForms: () => ({ mutateAsync: vi.fn(), isPending: false }),
  formsListQueryKey: () => ['forms'],
  formsPagerQuery: {
    listQueryKey: () => ['forms'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
}));

import FormsList from './FormsList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FormsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  push.mockReset();
});

describe('FormsList - the row opens the form', () => {
  it('B3: the whole row is a link to the form, carrying the list query', () => {
    renderList();

    const row = screen.getAllByRole('link').find((el) => el.tagName === 'TR') as HTMLElement;
    expect(row).toBeTruthy();

    fireEvent.click(row);

    expect(push).toHaveBeenCalledWith(expect.stringContaining('/forms-management/forms/form-1'));
    expect(push.mock.calls[0][0]).toContain('page=1');
  });

  it('B3: the form code is a real anchor to the same place', () => {
    renderList();

    const anchor = screen
      .getAllByRole('link', { name: 'FRM-001' })
      .find((el) => el.tagName === 'A') as HTMLAnchorElement;
    expect(anchor.getAttribute('href')).toContain('/forms-management/forms/form-1');
  });

  it('B3: Enter on the focused row opens it too', () => {
    renderList();

    const row = screen.getAllByRole('link').find((el) => el.tagName === 'TR') as HTMLElement;
    fireEvent.keyDown(row, { key: 'Enter', code: 'Enter' });

    expect(push).toHaveBeenCalledWith(expect.stringContaining('/forms-management/forms/form-1'));
  });
});
