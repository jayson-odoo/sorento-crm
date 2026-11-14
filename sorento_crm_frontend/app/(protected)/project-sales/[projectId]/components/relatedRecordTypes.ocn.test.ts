/**
 * OCN-ORDER-CHANGE-NOTICE round 8: the order change notice is a registered Related type. Its row
 * renders in the project's Related grid with the type label and its status in the notice's own
 * words, and a click opens the notice. Same harness as relatedRecordTypes.test.ts; fake values.
 */
import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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

const OCN_ROW = {
  kind: 'order_change_notice',
  id: 'ocn-1',
  number: 'OCN26-0302',
  status: 'processed_by_cs',
  approval_status: 'approved',
  date: '2026-06-10',
  raised_by: 'Rina Raiser',
  subject: 'Delivery pushed to January',
  value: null,
};
const OCN_TYPES = [...TYPES, { kind: 'order_change_notice', label: 'Order change notice' }];

vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useProjectRelatedRecords: () => ({
      data: response([...ROWS, OCN_ROW], OCN_TYPES),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
    useSponsorshipRollup: () => ({ data: undefined, isLoading: false, isError: false }),
  };
});

import { RELATED_RECORD_TYPES } from './relatedRecordTypes';
import { RelatedRecordsPanel } from './RelatedRecordsPanel';

describe('the order change notice on the Related tab', () => {
  it('is registered with its own page', () => {
    expect(RELATED_RECORD_TYPES.order_change_notice.label).toBe('Order change notice');
    expect(RELATED_RECORD_TYPES.order_change_notice.href('x1')).toBe('/procurement-management/order-change-notices/x1');
  });

  it('renders its row with the type, the raiser and its status in words, and opens the notice', () => {
    renderWithClient(React.createElement(RelatedRecordsPanel, { project: project() }));
    const cell = screen.getByText('OCN26-0302');
    const row = cell.closest('tr') as HTMLElement;
    expect(row).toBeTruthy();
    expect(row.textContent).toContain('Order change notice');
    expect(row.textContent).toContain('Rina Raiser');
    expect(row.textContent).toContain('Done');
    expect(row.textContent).not.toMatch(/processed_by_cs|processed by cs/i);
    fireEvent.click(cell);
    expect(push).toHaveBeenCalledWith(
      `/procurement-management/order-change-notices/ocn-1?back=${encodeURIComponent('/project-sales/p1?tab=related')}`,
    );
  });
});
