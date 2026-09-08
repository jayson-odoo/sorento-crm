/**
 * PLAN-price-tag-feedback-r2 S2, AC-S2-1: the read-only view renders the SAME
 * sections in the SAME order as the edit form - Customer, Promotion, Price,
 * Need by, Notes, Lines, Sales Order (r7 renamed Debtor -> Customer, Needed
 * by -> Need by, Purchase Order -> Sales Order, and added the Price field -
 * PLAN-price-tag-r7-request-ux D1/D4/D5).
 *
 * The other read-only suites assert individual sections' content; this one
 * asserts nothing about content and everything about ORDER, reading the
 * rendered `Label` (`data-slot="label"`) and `CardTitle`
 * (`data-slot="card-title"`) text nodes in DOCUMENT order - the same order a
 * screen reader or a human scanning top-to-bottom encounters them in, not the
 * order they appear in the source.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

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
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  deleteRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  downloadPriceTagPdf: vi.fn(),
}));

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

// Same reasoning as the sibling read-only suites: the real DetailActionsMenu
// mounts a Radix DropdownMenu (Portal + `motion/react` AnimatePresence),
// which is unrelated to what this file asserts (section order) and flickers
// in jsdom.
vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: () => null,
}));

import { getRequest } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('read-only view section order (AC-S2-1)', () => {
  it('renders Customer, Promotion, Price, Need by, Notes, Lines, Sales Order in that order', async () => {
    asMock(getRequest).mockResolvedValue({
      id: 'req-1',
      doc_number: 'PT-202609-0001',
      debtor_code: 'ZZTD01',
      debtor_name: 'ZZT Dealer',
      promotion_id: 'promo-1',
      promotion_name: 'ZZT August Promo',
      needed_by_date: '2026-09-10',
      notes: 'Handle with care',
      // A non-editable, non-design-preview status: r7 widened the design
      // preview to proof_ready|changes_requested|approved|ready (D11), so
      // this now has to pick a status OUTSIDE that set to stay isolated to
      // the base layout order, which is all this test asserts (AC-S2-2 /
      // AC-S4-1 cover the design preview section itself).
      status: 'rejected',
      line_count: 1,
      created_at: '2026-09-01T00:00:00Z',
      portal_draft_at: null,
      contact_id: 'contact-1',
      has_completed_export: false,
      lines: [
        {
          id: 'line-1',
          line_type: 'product',
          product_id: 'prod-1',
          product_set_id: null,
          name: 'ZZT Kitchen Sink',
          code: 'ZZT-SINK-1',
          show_promo_price: true,
          quantity: 2,
          alternatives: [],
          included_accessories: null,
        },
      ],
      attachments: [],
    });

    const { container } = render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');

    const nodes = Array.from(
      container.querySelectorAll('[data-slot="label"], [data-slot="card-title"]'),
    );
    const texts = nodes.map((n) => n.textContent?.trim() ?? '');

    // `Lines` renders as `Lines (1)`; normalized to the bare word so the whole
    // sequence can be compared as one list against the AC's order.
    const normalized = texts.map((t) => (t.startsWith('Lines') ? 'Lines' : t));

    expect(normalized).toEqual([
      'Customer',
      'Promotion',
      'Price',
      'Need by',
      'Notes',
      'Lines',
      'Sales Order',
    ]);
  });
});
