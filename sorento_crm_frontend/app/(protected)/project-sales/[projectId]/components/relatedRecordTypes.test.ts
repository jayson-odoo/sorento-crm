/**
 * PROJECT-RELATED-RECORDS AC-D1: adding a record type is one frontend registry entry. A sixth,
 * fake kind registered with `registerRelatedRecordType` renders in the panel (Type label, Type
 * filter option, row click) without editing RelatedRecordsPanel. Fake values only.
 */
import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { project, renderWithClient, response, ROWS, TYPES } from './relatedRecordsTestKit';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ options }: { options: { value: string; label: string }[] }) =>
    React.createElement(
      'div',
      { 'data-testid': 'multi-select' },
      options.map((o) =>
        React.createElement('button', { key: o.value, 'data-value': o.value, type: 'button' }, o.label),
      ),
    ),
}));

const FAKE_ROW = {
  kind: 'zzt_fake_kind',
  id: 'fake-1',
  number: 'ZZT-FAKE-0001',
  status: 'submitted',
  approval_status: null,
  date: '2026-07-01',
  raised_by: 'Eve Fake',
  subject: 'Fake subject',
  value: null,
};
const FAKE_TYPES = [...TYPES, { kind: 'zzt_fake_kind', label: 'ZZT fake kind' }];

vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useProjectRelatedRecords: () => ({
      data: response([...ROWS, FAKE_ROW], FAKE_TYPES),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
    useSponsorshipRollup: () => ({ data: undefined, isLoading: false, isError: false }),
  };
});

import { RELATED_RECORD_TYPES, registerRelatedRecordType } from './relatedRecordTypes';
import { RelatedRecordsPanel } from './RelatedRecordsPanel';

afterEach(() => {
  delete (RELATED_RECORD_TYPES as Record<string, unknown>)['zzt_fake_kind'];
  push.mockReset();
});

describe('relatedRecordTypes registry', () => {
  it('holds the five kinds with their own pages', () => {
    const href = (kind: string) =>
      (RELATED_RECORD_TYPES as Record<string, { href: (id: string) => string }>)[kind].href('x1');
    expect(href('stock_inquiry')).toBe('/procurement-management/stock-inquiries/x1');
    expect(href('complaint')).toBe('/complaint-management/complaints/x1');
    expect(href('purchase_request')).toBe('/procurement-management/purchase-requests/x1');
    expect(href('sponsorship_form')).toBe('/procurement-management/sponsorship-forms/x1');
    expect(href('new_product_application')).toBe(
      '/procurement-management/new-product-applications/x1',
    );
  });

  it('AC-D1 a sixth kind registered once renders in the grid, the filter and the row click', async () => {
    registerRelatedRecordType('zzt_fake_kind', {
      label: 'ZZT fake kind',
      href: (id: string) => `/zzt-fake/${id}`,
    });
    renderWithClient(React.createElement(RelatedRecordsPanel, { project: project() }));

    const cell = screen.getByText('ZZT-FAKE-0001');
    const row = cell.closest('tr') as HTMLElement;
    expect(row).toBeTruthy();
    expect(row.textContent).toContain('ZZT fake kind');
    expect(row.textContent).toContain('Eve Fake');

    // The Type filter sits in the toolbar's Filters popover (fix round 2, review S1).
    await userEvent.setup().click(screen.getByRole('button', { name: /^filters/i }));
    const offered = screen
      .getAllByTestId('multi-select')
      .flatMap((el) => Array.from(el.querySelectorAll('button')))
      .map((b) => b.getAttribute('data-value'));
    expect(offered).toContain('zzt_fake_kind');

    fireEvent.click(cell);
    expect(push).toHaveBeenCalledWith('/zzt-fake/fake-1');
  });
});
