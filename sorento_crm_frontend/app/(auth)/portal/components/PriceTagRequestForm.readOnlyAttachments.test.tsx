/**
 * PLAN-price-tag-feedback-r2 S1: `PriceTagRequestDetail.attachments` was
 * retyped in Phase 1 from an ad-hoc `{id, filename, content_type, url,
 * created_at}` shape to the real `PortalAttachment` shape
 * (`link_id`/`attachment_id`/uploader fields/`can_unlink`) - the shape
 * `entity_attachment_service.list_attachments_for_entity` actually answers
 * with (S1 Phase 2). This is the round-trip regression: a response in that
 * real shape has to render in the read-only view, keyed on `link_id`, not
 * silently show nothing because the row no longer has an `id` field.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock('sonner', () => ({
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
}));

import { getRequest } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

// The real AttachmentPreviewModal pulls in embla-carousel, which needs layout
// APIs jsdom lacks (same swap as AttachmentDropzone.test.tsx) - a thin stand-in
// that surfaces the `items` prop is enough to prove what was WIRED to it.
const previewPropsSpy = vi.fn();
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: (props: {
    open: boolean;
    items: { id: string; name: string; downloadUrl?: string }[];
  }) => {
    previewPropsSpy(props);
    return null;
  },
}));

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('read-only view attachments (PortalAttachment shape)', () => {
  it('lists an attachment answered in the real link_id/attachment_id shape', async () => {
    asMock(getRequest).mockResolvedValue({
      id: 'req-1',
      doc_number: 'PT-202609-0001',
      debtor_code: 'ZZTD01',
      debtor_name: 'ZZT Dealer',
      promotion_id: null,
      promotion_name: null,
      needed_by_date: '2026-09-10',
      notes: null,
      status: 'approved',
      line_count: 0,
      created_at: '2026-09-01T00:00:00Z',
      portal_draft_at: null,
      contact_id: 'contact-1',
      lines: [],
      // The real service shape (S1 Phase 2), not the old ad-hoc one - no `id`
      // or `created_at` field on the row itself.
      attachments: [
        {
          link_id: 'link-1',
          attachment_id: 'att-1',
          filename: 'ZZT-po.pdf',
          size: 1024,
          url: 'https://cdn.test/zzt-po.pdf',
          content_type: 'application/pdf',
          uploaded_at: '2026-09-01T00:00:00Z',
          uploader_kind: 'contact',
          uploaded_by_name: 'ZZT Sales Sam',
          uploaded_by_role: 'contact',
          can_unlink: true,
        },
      ],
    });

    render(<PriceTagRequestForm requestId="req-1" />);

    expect(await screen.findByText('ZZT-po.pdf')).toBeInTheDocument();
    expect(screen.getByText('PT-202609-0001')).toBeInTheDocument();

    // The round trip, not just the filename text (which happens to be spelled
    // the same in both the old and the new shape): `toPreviewItem` keys the
    // item on `link_id` and only sets `downloadUrl` from `attachment_id` -
    // fields the OLD ad-hoc `{id, filename, content_type, url, created_at}`
    // shape never had, so this is what would go quietly missing if the type
    // ever regressed to it.
    expect(previewPropsSpy).toHaveBeenCalled();
    const items = previewPropsSpy.mock.calls.at(-1)?.[0].items;
    expect(items).toEqual([
      expect.objectContaining({
        id: 'link-1',
        name: 'ZZT-po.pdf',
        downloadUrl: expect.stringContaining('att-1'),
      }),
    ]);
  });

  it('renders no PO Attachments card when the request carries none', async () => {
    asMock(getRequest).mockResolvedValue({
      id: 'req-2',
      doc_number: 'PT-202609-0002',
      debtor_code: 'ZZTD01',
      debtor_name: 'ZZT Dealer',
      promotion_id: null,
      promotion_name: null,
      needed_by_date: '2026-09-10',
      notes: null,
      status: 'approved',
      line_count: 0,
      created_at: '2026-09-01T00:00:00Z',
      portal_draft_at: null,
      contact_id: 'contact-1',
      lines: [],
      attachments: [],
    });

    render(<PriceTagRequestForm requestId="req-2" />);

    await screen.findByText('PT-202609-0002');
    expect(screen.queryByText('PO Attachments')).not.toBeInTheDocument();
  });
});
