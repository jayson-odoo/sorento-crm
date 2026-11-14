/**
 * SPARE-PART-ORDER-REQUEST review round 2 (browser pass 5, step 8), red-first (Phase 2).
 *
 * R11 the spare part record page's Lines grid fits its card at 1280 with no inner sideways
 *     scroll hiding Total. The grid is the standard fixed-layout DataGrid
 *     (OrderInquiryLinesTab `tableLayout: { width: 'fixed' }`), so its width is the sum of its
 *     visible columns' sizes; that sum must fit the card the page gives it at 1280:
 *
 *       1280 viewport - 280 sidebar (css/demos/demo1.css --sidebar-width)
 *            - 48 Container padding (lg:px-6) - 2 card border = 950 px.
 *
 *     Measured today (default visibility, the Lines tab's DEFAULT_HIDDEN_COLUMNS): the sum is
 *     far over that, so Total sits past the card edge. Asserted for the approver's view (the
 *     editable Qty / Unit price inputs) and the read-only view.
 */
import React from 'react';
import { renderHook } from '@testing-library/react';
import { getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return { ...actual, getOrderInquiryPoDetail: vi.fn(), getOrderInquirySpoDetail: vi.fn() };
});
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import { DEFAULT_HIDDEN_COLUMNS } from '../../components/orderInquiryWorklistColumns';

const CARD_WIDTH_AT_1280 = 1280 - 280 - 48 - 2;

function widthOf(options: Record<string, unknown>) {
  const { result } = renderHook(() => {
    const columns = useOrderInquiryHeaderLinesColumns(options as never);
    const table = useReactTable({
      data: [],
      columns,
      getCoreRowModel: getCoreRowModel(),
      initialState: {
        columnVisibility: Object.fromEntries(DEFAULT_HIDDEN_COLUMNS.map((id) => [id, false])),
      },
    });
    return {
      total: table.getTotalSize(),
      sizes: table.getVisibleLeafColumns().map((c) => `${c.id}=${c.getSize()}`),
      ids: table.getVisibleLeafColumns().map((c) => c.id),
    };
  });
  return result.current;
}

describe('R11: the spare part Lines grid fits its card at 1280', () => {
  it.each([
    ['the approver, pending', { inquiryType: 'spare_part_request', headerState: 'pending_approval', canDecide: true, onEditLine: vi.fn() }],
    ['a reader, raised', { inquiryType: 'spare_part_request', headerState: 'raised', canDecide: false }],
  ])('%s: the visible columns sum within the 1280 card width', (_who, options) => {
    const { total, sizes, ids } = widthOf(options);
    expect(ids, 'precondition: Total is one of the columns').toContain('line_total');
    expect(total, `column sizes ${sizes.join(', ')} (sum ${total})`).toBeLessThanOrEqual(CARD_WIDTH_AT_1280);
  });
});

/**
 * R13 (browser pass on 300a42e1): at 1280 the Location header read "Locatio". A header with
 * its sort control needs about 90 px (8 characters at ~8 px, the sort icon, cell padding).
 */
describe('R13: the spare part Location header is not clipped', () => {
  it.each([
    ['the approver, pending', { inquiryType: 'spare_part_request', headerState: 'pending_approval', canDecide: true, onEditLine: vi.fn() }],
    ['a reader, raised', { inquiryType: 'spare_part_request', headerState: 'raised', canDecide: false }],
  ])('%s: Location is at least 90 px wide', (_who, options) => {
    const { sizes } = widthOf(options);
    const location = sizes.find((s) => /^location[^=]*=/.test(s));
    expect(location, `column sizes ${sizes.join(', ')}`).toBeDefined();
    expect(Number(location!.split('=')[1])).toBeGreaterThanOrEqual(90);
  });
});
