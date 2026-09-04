/**
 * M5-06 - the picking lines table renders on DataGrid instead of a raw
 * `<Table>`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/procurement-management/grn/grn-1',
}));

vi.mock('./GRNNavigation', () => ({
  default: () => <div data-testid="grn-navigation" />,
}));

vi.mock('./grn-delete-dialog', () => ({
  default: () => null,
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const grnMock = vi.fn();
vi.mock('../hooks/useGRN', () => ({
  useGRN: () => grnMock(),
  useUpdateGRN: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  grnPagerQuery: {
    listQueryKey: () => ['grn'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
}));

vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

import GRNDetail from './GRNDetail';

const GRN = {
  id: 'grn-1',
  picking_number: 'GR-001114',
  spo_number: 'PO-000338',
  picking_date: '2026-06-22',
  picking_status: 'approved',
  picking_lines: [
    {
      id: 'line-1',
      picking_header_id: 'grn-1',
      product_id: 'p-1',
      quantity_expected: 10,
      quantity_picked: 10,
      quantity_discrepancy: 0,
      picked_condition: 'good',
      product: { id: 'p-1', product_code: 'SKU-001', product_name: 'Widget A' },
      source_warehouse: { id: 'w-1', warehouse_code: 'WH-KL', warehouse_name: 'KL' },
    },
    {
      id: 'line-2',
      picking_header_id: 'grn-1',
      product_id: 'p-2',
      quantity_expected: 5,
      quantity_picked: 4,
      quantity_discrepancy: 1,
      picked_condition: 'good',
      product: { id: 'p-2', product_code: 'SKU-002', product_name: 'Widget B' },
      destination_warehouse: { id: 'w-2', warehouse_code: 'WH-PG', warehouse_name: 'Penang' },
    },
  ],
};

beforeEach(() => {
  pushMock.mockReset();
  grnMock.mockReturnValue({ data: GRN, isLoading: false });
});

describe('GRNDetail - picking lines DataGrid', () => {
  it('renders the column headers and a real cell value for each picking line', () => {
    render(<GRNDetail grnId="grn-1" />);

    expect(screen.getByText('Product')).toBeInTheDocument();
    expect(screen.getByText('Location')).toBeInTheDocument();
    expect(screen.getByText('Expected')).toBeInTheDocument();
    expect(screen.getByText('Picked')).toBeInTheDocument();

    expect(screen.getByText('SKU-001')).toBeInTheDocument();
    expect(screen.getByText('SKU-002')).toBeInTheDocument();
    expect(screen.getByText('WH-KL')).toBeInTheDocument();
  });
});
