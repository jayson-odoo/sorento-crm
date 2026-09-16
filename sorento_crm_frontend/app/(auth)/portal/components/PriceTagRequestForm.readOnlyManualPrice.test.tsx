/**
 * Read-only submitted view shows the line's SAVED price basis (F2, AC-S1-10).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-line-promo-combo-subject-acceptance-criteria.md`
 * AC-S1-10: "Given the read-only view of a submitted request, Then each line
 * shows List price, and in Selling mode its Promotion and Selling price."
 *
 * The read-only Selling price cell is fed by `readLinePricing` - a SECOND,
 * client-side `lookupLinePricing` recompute keyed on `line.promotion_id`
 * only (`PriceTagRequestForm.tsx` ~line 844-854). It never sends the line's
 * `manual_sell_price`, so a line saved with a manual price and no promotion
 * recomputes through the promotion/list path instead and renders the list
 * total, not the manual figure the salesperson actually typed and the
 * server actually stored (`line.sell_price` on the response, S7 D2/D3).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

vi.mock('../lib/price-tag-request-service', () => ({
  lookupDebtors: vi.fn(async () => []),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(async () => []),
  lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
  // The read-only view's OWN recompute - never told about `manual_sell_price`.
  // It answers as the real backend would for an uncovered line with no
  // promotion: sell_price = the list total, basis 'list'.
  lookupLinePricing: vi.fn(async (_mode: string, lines: { key: string }[]) =>
    lines.map((line) => ({
      key: line.key,
      list_price: 150,
      promotion_options: [],
      auto_promotion_id: null,
      sell_price: 150,
      sell_price_basis: 'list' as const,
      parts_at_list: [],
      candidates: [],
    })),
  ),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  deleteRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
}));

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

import { getRequest } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const baseRequest = {
  id: 'req-1',
  doc_number: 'PT-202609-0001',
  debtor_code: 'ZZTD01',
  debtor_name: 'ZZT Dealer',
  promotion_id: null,
  promotion_name: null,
  price_mode: 'selling' as const,
  needed_by_date: '2026-09-10',
  notes: null,
  status: 'ready',
  line_count: 1,
  created_at: '2026-09-01T00:00:00Z',
  portal_draft_at: null,
  contact_id: 'contact-1',
  has_completed_export: false,
  attachments: [],
  lines: [
    {
      id: 'line-1',
      line_type: 'product' as const,
      product_id: 'prod-manual',
      product_set_id: null,
      name: 'ZZT Manual-priced product',
      code: 'SRTMAN01',
      show_promo_price: true,
      quantity: 5,
      included_accessories: null,
      remarks: null,
      sort_order: 0,
      // The line's OWN saved price basis: an agreed manual price, no
      // promotion. Server-computed `list_price`/`sell_price` on the
      // response reflect this (S7 API contract).
      promotion_id: null,
      promotion_name: null,
      manual_sell_price: 175,
      list_price: 150,
      sell_price: 175,
      sell_price_basis: 'manual' as const,
      parts: [],
      tags: [],
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  asMock(getRequest).mockResolvedValue(baseRequest);
});

describe('PriceTagRequestForm - read-only view renders the saved manual price (F2, AC-S1-10)', () => {
  it("shows the line's manual_sell_price (175) as Selling price, not the recomputed list price (150)", async () => {
    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');

    await waitFor(() => {
      expect(screen.getByText('RM 175')).toBeInTheDocument();
    });

    // Owner ruling after #948: the read-only submitted view gets the SAME
    // column shape as the edit table - List price / Promotion / Selling
    // price are `<th>`/`<td>` columns, not a sub-row under the item. Assert
    // the header carries the columns, and the line's own row (found by the
    // product name, a fixed per-line anchor) carries the values in cells of
    // THAT row - the bug this file guards against (F2: the read-only view's
    // own `lookupLinePricing` recompute never sees `manual_sell_price`, so it
    // would print the recomputed list total here instead of the saved 175).
    const linesTable = screen.getByRole('table');
    const headers = within(linesTable)
      .getAllByRole('columnheader')
      .map((h) => h.textContent?.trim());
    expect(headers).toContain('List price');
    expect(headers).toContain('Promotion');
    expect(headers).toContain('Selling price');

    const rows = within(linesTable).getAllByRole('row');
    const lineRow = rows.find((row) =>
      within(row).queryByText('ZZT Manual-priced product'),
    );
    expect(lineRow).toBeTruthy();
    expect(within(lineRow!).getByText('RM 150')).toBeInTheDocument();
    // No promotion saved on this line, and its basis is 'manual' - the
    // Promotion cell reads "Manual price", not a covering promotion's name.
    expect(within(lineRow!).getByText('Manual price')).toBeInTheDocument();
    expect(within(lineRow!).getByText('RM 175')).toBeInTheDocument();
  });
});

// ----------------------------------------------------------- kill: viewSpan

// Owner ruling after #948: List price / Promotion / Selling price are real
// table columns on the desktop table (992px and up, `useIsMobile`'s
// `MOBILE_BREAKPOINT`). A line's part row still spans the WHOLE row width
// via `viewSpan` (`PriceTagRequestForm.tsx`), a hard-coded
// `isMobile ? 4 : viewSelling ? 7 : 5` arithmetic that a header column
// change can silently drift from with every other test in this suite green.
describe('PriceTagRequestForm - read-only view: a part row spans the current header width, not a stale count', () => {
  it("a Selling-mode line with a part: the part row's colspan equals the header column count", async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      lines: [
        {
          ...baseRequest.lines[0],
          parts: [
            {
              id: 'part-1',
              product_id: 'prod-part',
              code: 'ZZT-PART-1',
              name: 'ZZT Part',
              role: null,
              candidates: [],
              sort_order: 0,
            },
          ],
        },
      ],
    });

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');
    // The part row prints `part.name` as its own text node and the code in
    // a SEPARATE trailing span (" - ZZT-PART-1"), so it is found by name.
    await screen.findByText('ZZT Part');

    const linesTable = screen.getByRole('table');
    const headerCount = within(linesTable).getAllByRole('columnheader').length;
    const colSpanCells = Array.from(linesTable.querySelectorAll('td[colspan]'));
    expect(colSpanCells.length).toBeGreaterThan(0);
    for (const cell of colSpanCells) {
      expect(Number(cell.getAttribute('colspan'))).toBe(headerCount);
    }
  });
});
