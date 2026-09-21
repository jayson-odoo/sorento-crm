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
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

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
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
  downloadPriceTagPdf,
  requestPriceTagExport: vi.fn(),
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

import { getRequest, requestPriceTagExport } from '../lib/price-tag-request-service';
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

describe('read-only gear: Download PDF (r10 S9)', () => {
  it('AC-S9-5: disables Download PDF with "Available after approval" before approved', async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      status: 'proof_ready',
      has_completed_export: false,
      latest_export_status: null,
    });

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    const item = screen.getByRole('button', { name: /available after approval/i });
    expect(item).toBeDisabled();

    fireEvent.click(item);
    expect(downloadPriceTagPdf).not.toHaveBeenCalled();
  });

  it('AC-S9-6: a READY export at approved+ streams without queueing', async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      status: 'approved',
      has_completed_export: true,
      latest_export_status: 'ready',
    });
    downloadPriceTagPdf.mockResolvedValue(undefined);

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    const item = screen.getByRole('button', { name: /^download pdf$/i });
    expect(item).not.toBeDisabled();

    fireEvent.click(item);
    expect(downloadPriceTagPdf).toHaveBeenCalledWith('req-1');
  });

  it('surfaces a failed download as a named toast, not a silent no-op', async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      status: 'approved',
      has_completed_export: true,
      latest_export_status: 'ready',
    });
    downloadPriceTagPdf.mockRejectedValue(new Error('The stored file is no longer available.'));

    render(<PriceTagRequestForm requestId="req-1" />);

    await screen.findByText('PT-202609-0001');
    fireEvent.click(screen.getByRole('button', { name: /^download pdf$/i }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'The stored file is no longer available.',
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// AC-S9-3, AC-S9-4 (PLAN-price-tag-r10.md S9, fake timers): at approved+ with
// no ready export, a click queues one via `requestPriceTagExport`, the item
// reads "Preparing your PDF" while it polls the request every 5s, and the
// download streams the moment the poll reports `ready`; a `failed` export
// reads "PDF failed, try again" and re-queues on click. Already wired in
// `PriceTagRequestForm.tsx` (`handleDownloadPdf`/the `exportPending` poll
// effect), so these are GREEN regression guards - Phase 1 shipped the real
// polling logic (`downloadPriceTagPdf`/`requestPriceTagExport` were already
// mocked by name in this file's own S9 rewrite, round 1).
// ---------------------------------------------------------------------------

describe('read-only gear: Download PDF poll (r10 S9, AC-S9-3/S9-4)', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('AC-S9-3: queues an export, shows "Preparing your PDF", and streams once the 5s poll reports ready', async () => {
    // Real timers for the initial async render (`waitFor`/`findBy*` poll with
    // the SAME global timer fake timers would also freeze); fake timers are
    // switched on only once mounted, so the 5s poll interval can be driven by
    // hand instead of the test actually waiting 5 real seconds.
    asMock(getRequest).mockResolvedValueOnce({
      ...baseRequest,
      status: 'approved',
      has_completed_export: false,
      latest_export_status: null,
    });
    asMock(requestPriceTagExport).mockResolvedValue({ status: 'pending' });
    downloadPriceTagPdf.mockResolvedValue(undefined);

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    const item = screen.getByRole('button', { name: /^download pdf$/i });
    expect(item).not.toBeDisabled();

    vi.useFakeTimers();
    try {
      fireEvent.click(item);
      // Flushes the click handler's own `await requestPriceTagExport(...)`.
      await act(async () => {});

      expect(requestPriceTagExport).toHaveBeenCalledWith('req-1');
      expect(
        screen.getByRole('button', { name: /preparing your pdf/i }),
      ).toBeInTheDocument();

      asMock(getRequest).mockResolvedValueOnce({
        ...baseRequest,
        status: 'approved',
        has_completed_export: true,
        latest_export_status: 'ready',
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      expect(downloadPriceTagPdf).toHaveBeenCalledWith('req-1');
    } finally {
      vi.useRealTimers();
    }
  });

  it('AC-S9-4: a failed export reads "PDF failed, try again" and re-queues on click', async () => {
    asMock(getRequest).mockResolvedValue({
      ...baseRequest,
      status: 'approved',
      has_completed_export: false,
      latest_export_status: 'failed',
    });
    asMock(requestPriceTagExport).mockResolvedValue({ status: 'pending' });

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    const item = screen.getByRole('button', { name: /pdf failed, try again/i });
    expect(item).not.toBeDisabled();

    fireEvent.click(item);

    await waitFor(() => expect(requestPriceTagExport).toHaveBeenCalledWith('req-1'));
  });
});

// ---------------------------------------------------------------------------
// AC-S9-8 (captain's ruling, phase 3 review): the poll must start on a
// SERVER-SIDE pending export too (e.g. a reload mid-export, or a second tab
// that queued it) - not only after this component's own click sets
// `exportPending`. Today the poll `useEffect` gates strictly on the LOCAL
// `exportPending` state, so a request that loads already `pending` shows the
// right label but never refetches and never streams.
// ---------------------------------------------------------------------------

describe('read-only gear: Download PDF poll starts on a server-side pending (r10 S9, AC-S9-8)', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('mounting on a pending export polls every 5s and streams once ready', async () => {
    asMock(getRequest).mockResolvedValueOnce({
      ...baseRequest,
      status: 'approved',
      has_completed_export: false,
      latest_export_status: 'pending',
    });
    downloadPriceTagPdf.mockResolvedValue(undefined);

    // Fake timers go on BEFORE render, not after: the poll's `setInterval`
    // is armed the moment `exportPreparing` reads true off the FIRST
    // `getRequest` response - on mount here, not on a later click like the
    // AC-S9-3 sibling above. An interval created under real timers is never
    // advanced by `vi.advanceTimersByTimeAsync`, so the render itself has to
    // happen under fake time; `findByText`/`waitFor`'s own real-timer
    // polling would then deadlock, so the initial async render is flushed by
    // hand with repeated zero-length `advanceTimersByTimeAsync` ticks (the
    // same idiom `page.pollBurst.test.tsx` uses), not `findBy*`.
    vi.useFakeTimers();
    try {
      await act(async () => {
        render(<PriceTagRequestForm requestId="req-1" />);
      });
      for (let i = 0; i < 20; i += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
      }

      expect(screen.getByText('PT-202609-0001')).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: /preparing your pdf/i }),
      ).toBeInTheDocument();

      asMock(getRequest).mockResolvedValueOnce({
        ...baseRequest,
        status: 'approved',
        has_completed_export: true,
        latest_export_status: 'ready',
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      expect(getRequest).toHaveBeenCalledTimes(2);
      expect(downloadPriceTagPdf).toHaveBeenCalledWith('req-1');
    } finally {
      vi.useRealTimers();
    }
  });
});
