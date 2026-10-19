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
vi.mock('../lib/portal-client', () => ({
  uploadAttachment: vi.fn(),
  getPriceTagDesign: vi.fn(),
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
});
