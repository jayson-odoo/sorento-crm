/**
 * The design leads the portal read view (r9 S1/D3, AC-S1-2).
 *
 * A salesperson opens a proof-ready request to look at the tags. Everything
 * else on the page - the dealer, the lines, the price mode - is what they
 * already typed, so it is the reference and not the headline. From
 * `proof_ready` onward the design sits FIRST, right after the status row;
 * before it there is nothing to show and the section is absent entirely rather
 * than an empty frame with a spinner in it.
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
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
  downloadPriceTagPdf: vi.fn(),
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...actual,
    getPriceTagDesign: vi.fn(async () => null),
    uploadAttachment: vi.fn(),
    fetchSubmissionNeighbours: vi.fn(async () => ({ prev: null, next: null })),
  };
});

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: () => null,
}));

// The viewer itself is asserted in `components/dealer-kit/DesignViewer.test.tsx`;
// here it only has to be findable in document order.
vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  __esModule: true,
  default: () => <div data-testid="design-section">Design</div>,
}));

import { getRequest } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

function request(status: string) {
  return {
    id: 'req-1',
    doc_number: 'PT-202609-0001',
    debtor_code: 'ZZTD01',
    debtor_name: 'ZZT Dealer',
    promotion_id: null,
    promotion_name: null,
    needed_by_date: '2026-09-20',
    notes: null,
    status,
    print_by: 'office',
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
        show_promo_price: false,
        quantity: 1,
        alternatives: [],
        included_accessories: null,
      },
    ],
    attachments: [],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('where the design sits (AC-S1-2)', () => {
  it.each(['proof_ready', 'changes_requested', 'approved'])(
    'is the first section at %s',
    async (status) => {
      asMock(getRequest).mockResolvedValue(request(status));

      const { container } = render(<PriceTagRequestForm requestId="req-1" />);
      await screen.findByText('PT-202609-0001');

      const design = await screen.findByTestId('design-section');
      const firstSectionHeader = container.querySelector(
        '[data-slot="collapsible-trigger"]',
      );
      expect(firstSectionHeader).not.toBeNull();
      // Node.DOCUMENT_POSITION_FOLLOWING: the first ordinary section comes
      // AFTER the design in document order.
      expect(
        design.compareDocumentPosition(firstSectionHeader as Node) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    },
  );

  it.each(['new', 'designing'])('is absent at %s', async (status) => {
    asMock(getRequest).mockResolvedValue(request(status));

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    expect(screen.queryByTestId('design-section')).toBeNull();
  });

  it('is still there once the tags have been collected', async () => {
    asMock(getRequest).mockResolvedValue(request('collected'));

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    expect(await screen.findByTestId('design-section')).toBeInTheDocument();
  });
});
