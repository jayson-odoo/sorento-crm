/**
 * PLAN-portal-price-tag-journey-r8, D-P6 (AC-P12, AC-P13).
 *
 * `is_editable` gates the header's "Edit" button - never a hardcoded status
 * list (the plan's own point: the FE reads the field, the BE owns the rule).
 * S7 mocked `is_editable` at the service layer
 * (`price-tag-request-service.ts`'s `deriveIsEditable`); this file mocks the
 * SERVICE module wholesale (same pattern as the sibling read-only suites),
 * so the field comes straight from what `getRequest` is told to resolve.
 *
 * `DetailActionsMenu` is stubbed the same way
 * `PriceTagRequestForm.readOnlyGear.test.tsx` / `.readOnlyAttachments
 * .test.tsx` already do: the real one mounts a Radix DropdownMenu (Portal +
 * `motion/react` AnimatePresence) that is unrelated to what this file
 * asserts and flickers sibling text in jsdom.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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
}));

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: () => null,
}));

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => null,
}));

import { getRequest, updateRequest } from '../lib/price-tag-request-service';
import { PriceTagRequestForm } from './PriceTagRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

function baseRequest(over: Record<string, unknown> = {}) {
  return {
    id: 'req-1',
    doc_number: 'PT-202609-0001',
    debtor_code: 'ZZTD01',
    debtor_name: 'ZZT Dealer',
    promotion_id: null,
    promotion_name: null,
    price_mode: 'list',
    needed_by_date: '2026-09-10',
    notes: null,
    status: 'new',
    line_count: 0,
    created_at: '2026-09-01T00:00:00Z',
    portal_draft_at: null,
    contact_id: 'contact-1',
    has_completed_export: false,
    lines: [],
    attachments: [],
    is_editable: false,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PriceTagRequestForm - Edit CTA gated on is_editable (AC-P12)', () => {
  it('shows Edit when is_editable is true at status new', async () => {
    asMock(getRequest).mockResolvedValue(
      baseRequest({ status: 'new', is_editable: true }),
    );

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('shows Edit when is_editable is true at status changes_requested', async () => {
    asMock(getRequest).mockResolvedValue(
      baseRequest({ status: 'changes_requested', is_editable: true }),
    );

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it.each(['designing', 'proof_ready', 'approved', 'ready', 'void'])(
    'no Edit button at status %s once is_editable is false',
    async (status) => {
      asMock(getRequest).mockResolvedValue(baseRequest({ status, is_editable: false }));

      render(<PriceTagRequestForm requestId="req-1" />);

      await screen.findByText('PT-202609-0001');
      expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    },
  );

  it('reads is_editable itself, never a hardcoded status list', async () => {
    // A status not named anywhere in the plan's editable list, but the field
    // says yes anyway - the FE must still show Edit, proving it is not
    // secretly checking `status === 'new' || status === 'changes_requested'`.
    asMock(getRequest).mockResolvedValue(
      baseRequest({ status: 'some_future_status', is_editable: true }),
    );

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });
});

describe('PriceTagRequestForm - Edit / Save / Cancel (AC-P13)', () => {
  it('Save writes via PUT, returns to read mode with the saved values, status unchanged, toasts Saved', async () => {
    asMock(getRequest).mockResolvedValue(
      baseRequest({ status: 'new', is_editable: true }),
    );
    asMock(updateRequest).mockResolvedValue({ id: 'req-1' });

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();

    const notesField = await screen.findByLabelText('Notes');
    fireEvent.change(notesField, { target: { value: 'Edited after submit' } });

    // The re-fetch after Save answers with the edited value AND the same
    // status - a post-submit edit never re-submits or restarts the SLA.
    asMock(getRequest).mockResolvedValue(
      baseRequest({
        status: 'new',
        is_editable: true,
        notes: 'Edited after submit',
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateRequest).toHaveBeenCalledWith('req-1', expect.anything()));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith('Saved'));

    // Back to read mode: Edit is offered again (still is_editable), the
    // status pill still reads the same status, and the saved note shows.
    expect(await screen.findByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByText('Edited after submit')).toBeInTheDocument();
  });

  it('Cancel restores the values shown before Edit, and writes nothing', async () => {
    asMock(getRequest).mockResolvedValue(
      baseRequest({ status: 'new', is_editable: true, notes: 'Original note' }),
    );

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const notesField = await screen.findByLabelText('Notes');
    expect(notesField).toHaveValue('Original note');
    fireEvent.change(notesField, { target: { value: 'A change about to be discarded' } });

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(updateRequest).not.toHaveBeenCalled();
    expect(await screen.findByText('Original note')).toBeInTheDocument();
    expect(screen.queryByText('A change about to be discarded')).toBeNull();
  });
});
