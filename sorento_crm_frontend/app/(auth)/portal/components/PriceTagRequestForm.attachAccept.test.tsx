/**
 * ATTACH-ACCEPT: the price tag form's Sales Order box offers the file types
 * the "Portal Submission" attachment type allows, read off the form's own
 * `/me` (still exactly one `/me`, D7 r3).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

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
}));

const fetchMe = vi.fn();
vi.mock('../lib/portal-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/portal-client')>()),
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(() => Promise.resolve(null)),
  fetchMe: (...a: unknown[]) => fetchMe(...a),
}));

const dropzoneProps = vi.hoisted(
  () => [] as { readOnly?: boolean; allowedExtensions?: string[] }[],
);
vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: (props: { readOnly?: boolean; allowedExtensions?: string[] }) => {
    dropzoneProps.push(props);
    return null;
  },
}));

import { getRequest } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

beforeEach(() => {
  vi.clearAllMocks();
  dropzoneProps.length = 0;
});

describe('PriceTagRequestForm Sales Order box (ATTACH-ACCEPT)', () => {
  it('hands the dropzone the attachment type allowed extensions from the one /me fetch', async () => {
    fetchMe.mockResolvedValue({
      visible_form_types: ['price_tag_request'],
      attachment_allowed_extensions: ['csv', 'pdf', 'xlsx'],
    });
    render(<PriceTagRequestForm />);

    // The Sales Order section starts collapsed on a new request.
    fireEvent.click(await screen.findByRole('button', { name: /Sales Order & Lines/ }));

    await waitFor(() => {
      const editable = dropzoneProps.filter((p) => !p.readOnly);
      expect(editable.length).toBeGreaterThan(0);
      expect(editable.at(-1)?.allowedExtensions).toEqual(['csv', 'pdf', 'xlsx']);
    });
    expect(fetchMe).toHaveBeenCalledTimes(1);
  });

  it('hands the list to the Sales Order box on a saved draft too, with no visibility block', async () => {
    // The visibility check is /new-only (the GET by id is the gate there), so a
    // /me without price_tag_request must not block a draft that loaded.
    fetchMe.mockResolvedValue({
      visible_form_types: ['stock_inquiry'],
      attachment_allowed_extensions: ['csv', 'xlsx'],
    });
    vi.mocked(getRequest).mockResolvedValue({
      id: 'req-1',
      doc_number: 'PT-202609-0009',
      debtor_code: 'ZZTD01',
      debtor_name: 'ZZT Dealer Sdn Bhd',
      promotion_id: null,
      promotion_name: null,
      price_mode: 'list',
      needed_by_date: null,
      notes: null,
      status: 'new',
      line_count: 0,
      created_at: '2026-09-01T00:00:00Z',
      portal_draft_at: '2026-09-01T00:00:00Z',
      contact_id: 'contact-1',
      has_completed_export: false,
      is_editable: true,
      revision_no: 0,
      last_revised_at: null,
      revision: null,
      attachments: [],
      lines: [],
    } as never);
    render(<PriceTagRequestForm requestId="req-1" />);

    fireEvent.click(await screen.findByRole('button', { name: /Sales Order & Lines/ }));

    await waitFor(() => {
      const editable = dropzoneProps.filter((p) => !p.readOnly);
      expect(editable.length).toBeGreaterThan(0);
      expect(editable.at(-1)?.allowedExtensions).toEqual(['csv', 'xlsx']);
    });
    expect(fetchMe).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByText('Price Tag Request is not available for your account.'),
    ).toBeNull();
  });
});
