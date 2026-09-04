/**
 * PLAN-price-tag-feedback-r2 S2: the read-only header's gear carries Download
 * PDF (D19) - enabled only when the request answers `has_completed_export`,
 * disabled with a reason otherwise. The stub toast ("PDF download will be
 * available when export completes") is gone; a click on the enabled item
 * calls the real download.
 *
 * `DetailActionsMenu` and `DropdownMenuItem` are stood in for plain markup
 * here (not rendered via the real Radix DropdownMenu): the real one mounts a
 * Portal + `motion/react` AnimatePresence that, combined with this form's own
 * concurrent lookups, occasionally flickers unrelated sibling text out of the
 * tree for a tick in jsdom - the same class of problem
 * `PriceTagRequestForm.readOnlyAttachments.test.tsx` mocks it away for. The
 * gear's own component (`DetailActionsMenu`, `DropdownMenuItem`) has its own
 * suite; what THIS file owns is the wiring - disabled state, reason text, and
 * which function a click reaches.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

// `vi.mock` factories are hoisted above every import/const, so the spies they
// close over must be created through `vi.hoisted` rather than a plain
// top-level `const` (which the hoist would run before it exists).
const { toastError, downloadPriceTagPdf } = vi.hoisted(() => ({
  toastError: vi.fn(),
  downloadPriceTagPdf: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { error: toastError, success: vi.fn(), info: vi.fn() },
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
  downloadPriceTagPdf,
}));

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

// Plain stand-ins: `DetailActionsMenu` renders its children unconditionally
// (the real one gates them behind an open Radix menu), and `DropdownMenuItem`
// becomes a plain button - both so `disabled`/`onSelect` are directly
// queryable/clickable without a Portal or Radix's menu-item context.
vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: ({ children }: { children?: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

vi.mock('@/components/ui/dropdown-menu', () => ({
  __esModule: true,
  DropdownMenuItem: ({
    children,
    disabled,
    onSelect,
  }: {
    children?: React.ReactNode;
    disabled?: boolean;
    onSelect?: (event: { preventDefault: () => void }) => void;
  }) => (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSelect?.({ preventDefault: () => {} })}
    >
      {children}
    </button>
  ),
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
  needed_by_date: '2026-09-10',
  notes: null,
  status: 'ready',
  line_count: 0,
  created_at: '2026-09-01T00:00:00Z',
  portal_draft_at: null,
  contact_id: 'contact-1',
  lines: [],
  attachments: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('read-only gear: Download PDF (D19)', () => {
  it('disables Download PDF with a reason when no completed export exists', async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      has_completed_export: false,
    });

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    const item = screen.getByRole('button', { name: /download pdf/i });
    expect(item).toBeDisabled();
    expect(screen.getByText('No completed export yet')).toBeInTheDocument();

    fireEvent.click(item);
    expect(downloadPriceTagPdf).not.toHaveBeenCalled();
  });

  it('enables Download PDF and calls the real download when a completed export exists', async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      has_completed_export: true,
    });
    downloadPriceTagPdf.mockResolvedValue(undefined);

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    const item = screen.getByRole('button', { name: /download pdf/i });
    expect(item).not.toBeDisabled();
    expect(screen.queryByText('No completed export yet')).not.toBeInTheDocument();

    fireEvent.click(item);
    expect(downloadPriceTagPdf).toHaveBeenCalledWith('req-1');
  });

  it('surfaces a failed download as a named toast, not a silent no-op', async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      has_completed_export: true,
    });
    downloadPriceTagPdf.mockRejectedValue(new Error('The stored file is no longer available.'));

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    fireEvent.click(screen.getByRole('button', { name: /download pdf/i }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'The stored file is no longer available.',
      ),
    );
  });
});
