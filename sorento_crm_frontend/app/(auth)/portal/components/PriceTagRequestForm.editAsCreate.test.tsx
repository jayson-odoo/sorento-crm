/**
 * PRICETAG-REQUEST-LAYOUT, owner hand test 11 Nov: "the preview can be a button to open the
 * lightbox popup so it doesn't bloat the view page, CTA is Edit and I think the editing should
 * follow the create path, don't need this submit revision, this is not really revision, it is
 * editing of your own request, so the preview approve step should still be here".
 *
 * Mocks follow `PriceTagRequestForm.edit.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
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
  lookupTagPreviewForRequest: vi.fn(),
  lookupLinePricing: vi.fn(async (_mode: string, lines: Array<{ key: string }>) =>
    lines.map((l) => ({ key: l.key, list_price: 320, promotion_options: [], auto_promotion_id: null, sell_price: null, sell_price_basis: 'list', parts_at_list: [], candidates: [] })),
  ),
  lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
  lookupProductTagTemplates: vi.fn(async () => []),
  lookupVariantMembers: vi.fn(async () => ({ members: [], own_list_price: null })),
  lookupTagPreview: vi.fn(),
  requestChanges: vi.fn(),
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
  downloadPriceTagPdf: vi.fn(),
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchSubmissionNeighbours: vi.fn(),
    uploadAttachment: vi.fn(),
    getPriceTagDesign: vi.fn(() => Promise.resolve(null)),
  };
});

// Same generic hooks `SubmissionForm` already reads for the legacy kinds
// (`app/(auth)/portal/hooks/useRevisions.ts`) - R3-1 has `PriceTagRequestForm`
// reuse them rather than a second revise mechanism (plan D-P1/"R3-1").
const { revisePolicyMock, reviseMock, revisionHistoryMock, revisionReloadMock } = vi.hoisted(() => ({
  revisePolicyMock: vi.fn(),
  reviseMock: vi.fn(),
  revisionHistoryMock: vi.fn(),
  revisionReloadMock: vi.fn(),
}));
vi.mock('../hooks/useRevisions', () => ({
  useRevisionPolicy: revisePolicyMock,
  useReviseSubmission: () => ({ revise: reviseMock, submitting: false }),
  useRevisionHistory: revisionHistoryMock,
}));

// The design components on the view page: what this file owns is that they are popups now.
const designProps = vi.hoisted(() => ({ review: [] as Record<string, unknown>[], self: [] as Record<string, unknown>[] }));
vi.mock('@/components/dealer-kit/PriceTagDesignReview', () => ({
  PriceTagDesignReview: (props: Record<string, unknown>) => {
    designProps.review.push(props);
    const popup = props.popup as { open: boolean } | undefined;
    return popup?.open ? <div data-testid="design-popup" /> : popup ? null : <div data-testid="design-inline" />;
  },
}));
vi.mock('@/components/dealer-kit/PriceTagSelfApproval', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  PriceTagSelfApproval: (props: Record<string, unknown>) => {
    designProps.self.push(props);
    const popup = props.popup as { open: boolean } | undefined;
    return popup?.open ? <div data-testid="design-popup" /> : popup ? null : <div data-testid="design-inline" />;
  },
  buildSelfProof: () => ({ doc: { sheets: [{ tags: [{ request_tag_id: 't1' }] }] }, payload: {} }),
  linesWithoutTemplate: () => [],
}));

// The edit form's whole-request preview: its popup renders its footer (Back to edit + Approve).
vi.mock('@/components/dealer-kit/PriceTagLivePreview', async () => {
  const React = await import('react');
  return {
    PriceTagLivePreview: (props: Record<string, unknown>) => {
      const popup = props.popup as { open: boolean; footer?: React.ReactNode } | undefined;
      React.useEffect(() => {
        (props.onReadyChange as ((s: unknown) => void) | undefined)?.({ missing: [], drawn: true, failed: false });
      }, [props.onReadyChange]);
      if (props.lineKey !== undefined) return null;
      return popup?.open ? <div data-testid="sheet-popup">{popup.footer}</div> : null;
    },
  };
});

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

// Plain stand-ins: `DetailActionsMenu` renders its children unconditionally,
// wrapped so the test can assert there is exactly ONE of them on the page
// (AC-R7/R3-5: one gear, not two).
vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="gear-menu">{children}</div>
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

let capturedOnPendingFilesChange: ((files: File[]) => void) | undefined;
vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: (props: { onPendingFilesChange?: (files: File[]) => void }) => {
    capturedOnPendingFilesChange = props.onPendingFilesChange;
    return <div data-testid="so-dropzone" />;
  },
}));

import { approveRequest, getRequest, lookupTagPreviewForRequest } from '../lib/price-tag-request-service';
import { fetchSubmissionNeighbours, uploadAttachment } from '../lib/portal-client';
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
    revision_no: 0,
    last_revised_at: null,
    // Review round 3: `revisionPolicy` now reads straight off the
    // re-fetched request's own `revision` block (`request?.revision ??
    // null`), not a second GET through `useRevisionPolicy` - so every test
    // that wants a policy sets it here, not on the (now-unused) hook mock.
    revision: null,
    ...over,
  };
}

const ALLOWED_POLICY = {
  enabled: true,
  allowed: true,
  used: 0,
  max: 3,
  remaining: 3,
  blocked_reason: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  designProps.review.length = 0;
  designProps.self.length = 0;
  // Dead import kept mocked so it never crashes if something still calls
  // it; the component no longer reads its RETURN value for the policy.
  revisePolicyMock.mockReturnValue({ policy: null, loading: false });
  reviseMock.mockResolvedValue({
    submission: baseRequest({ debtor_name: 'ZZT Revised Dealer' }),
    revision: ALLOWED_POLICY,
    revision_no: 1,
  });
  revisionHistoryMock.mockReturnValue({
    entries: [],
    loading: false,
    error: null,
    reload: revisionReloadMock,
  });
  asMock(fetchSubmissionNeighbours).mockResolvedValue({
    prev_id: null,
    next_id: null,
    position: 1,
    total: 1,
  });
});


const APPROVED = () =>
  baseRequest({
    status: 'approved',
    revision: ALLOWED_POLICY,
    lines: [{
      id: 'line-1', line_type: 'product', product_id: 'prod-1', product_set_id: null,
      name: 'ZZT Basin', code: 'ZZTWB501', show_promo_price: false, quantity: 1,
      alternatives: [], included_accessories: null, parts: [], tags: [{ id: 't1', quantity: 1 }],
    }],
    attachments: [],
  });

describe('view page: compact, Edit is the CTA, the design opens in a popup', () => {
  it('shows Edit and Preview as buttons, and no inline design', async () => {
    asMock(getRequest).mockResolvedValue(APPROVED());
    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview' })).toBeInTheDocument();
    expect(screen.queryByTestId('design-inline')).toBeNull();
    expect(within(screen.getByTestId('gear-menu')).queryByText('Edit')).toBeNull();
  });

  it('Preview opens the design popup', async () => {
    asMock(getRequest).mockResolvedValue(APPROVED());
    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    expect(screen.queryByTestId('design-popup')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    expect(screen.getByTestId('design-popup')).toBeInTheDocument();
  });

  it('the Price tags card has no Sales Order or Lines headings', async () => {
    asMock(getRequest).mockResolvedValue(APPROVED());
    const { container } = render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');
    const labels = Array.from(container.querySelectorAll('[data-slot="label"]')).map((n) => n.textContent?.trim());
    expect(labels).not.toContain('Sales Order');
    expect(labels.some((t) => t?.startsWith('Lines'))).toBe(false);
  });

  it('history is called History, never Revisions', async () => {
    asMock(getRequest).mockResolvedValue(APPROVED());
    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');
    expect(screen.getByRole('tab', { name: /History/ })).toBeInTheDocument();
    expect(screen.queryByText(/revision/i)).toBeNull();
  });
});

describe('Edit follows the create path', () => {
  async function openEdit() {
    asMock(getRequest).mockResolvedValue(APPROVED());
    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await screen.findByRole('button', { name: 'Preview' });
  }

  it('has no Reason box and no Submit revision; Preview is the main button', async () => {
    await openEdit();
    expect(screen.queryByLabelText(/reason/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /submit revision/i })).toBeNull();
    expect(screen.queryByText(/revision/i)).toBeNull();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('Preview then Approve saves the edit and approves it, with no reason asked', async () => {
    asMock(lookupTagPreviewForRequest).mockResolvedValue({ lines: [], templates: {}, assets: {}, images: {}, fonts: [] });
    asMock(approveRequest).mockResolvedValue({ status: 'approved' });
    await openEdit();

    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const popup = await screen.findByTestId('sheet-popup');
    fireEvent.click(within(popup).getByRole('button', { name: /^approve$/i }));

    await waitFor(() => expect(approveRequest).toHaveBeenCalled());
    expect(reviseMock).toHaveBeenCalledWith(expect.objectContaining({ reason: '' }));
    expect(asMock(approveRequest).mock.calls[0][0]).toBe('req-1');
    expect(asMock(approveRequest).mock.calls[0][1]).toBeTruthy();
    expect(toasts.success).toHaveBeenCalledWith('Tag approved');
  });

  it('a file added while editing is uploaded when the edit is approved', async () => {
    asMock(lookupTagPreviewForRequest).mockResolvedValue({ lines: [], templates: {}, assets: {}, images: {}, fonts: [] });
    asMock(approveRequest).mockResolvedValue({ status: 'approved' });
    asMock(uploadAttachment).mockResolvedValue({
      link_id: 'link-1', attachment_id: 'att-1', filename: 'ZZT-po.pdf', size: 3,
      url: 'https://cdn.test/ZZT-po.pdf', content_type: 'application/pdf',
    });
    await openEdit();
    fireEvent.click(screen.getByRole('button', { name: 'Upload a file instead' }));
    act(() => {
      capturedOnPendingFilesChange?.([new File(['zzt'], 'ZZT-po.pdf', { type: 'application/pdf' })]);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const popup = await screen.findByTestId('sheet-popup');
    fireEvent.click(within(popup).getByRole('button', { name: /^approve$/i }));

    await waitFor(() => expect(uploadAttachment).toHaveBeenCalled());
    await waitFor(() => expect(approveRequest).toHaveBeenCalled());
  });

  it('keeps the request\'s Need by unchanged when the edit is saved', async () => {
    asMock(lookupTagPreviewForRequest).mockResolvedValue({ lines: [], templates: {}, assets: {}, images: {}, fonts: [] });
    asMock(approveRequest).mockResolvedValue({ status: 'approved' });
    await openEdit();
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const popup = await screen.findByTestId('sheet-popup');
    fireEvent.click(within(popup).getByRole('button', { name: /^approve$/i }));
    await waitFor(() => expect(reviseMock).toHaveBeenCalled());
    expect(reviseMock.mock.calls[0][0].fields.needed_by_date).toBe('2026-09-10');
  });

  it('a failure after the edit is saved lands on the request page, where Preview then Approve finishes it', async () => {
    asMock(lookupTagPreviewForRequest).mockRejectedValue(new Error('The preview could not be drawn.'));
    await openEdit();
    asMock(getRequest).mockResolvedValue({ ...APPROVED(), status: 'proof_ready', self_review: true, revision_no: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    const popup = await screen.findByTestId('sheet-popup');
    fireEvent.click(within(popup).getByRole('button', { name: /^approve$/i }));

    expect(await screen.findByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Preview' })).toBeInTheDocument();
    expect(approveRequest).not.toHaveBeenCalled();
    expect(toasts.error).toHaveBeenCalled();
  });

  it('Cancel goes back to the view page without saving', async () => {
    await openEdit();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(await screen.findByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(reviseMock).not.toHaveBeenCalled();
  });
});

describe('struck labels on the edit form', () => {
  it('typed mode has no "Lines" heading; upload mode has no "Sales Order" heading', async () => {
    asMock(getRequest).mockResolvedValue(APPROVED());
    const { container } = render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await screen.findByRole('button', { name: 'Upload a file instead' });
    const labels = () =>
      Array.from(container.querySelectorAll('[data-slot="label"]')).map((n) => n.textContent?.trim());
    expect(labels()).not.toContain('Lines');

    fireEvent.click(screen.getByRole('button', { name: 'Upload a file instead' }));
    expect(screen.getByTestId('so-dropzone')).toBeInTheDocument();
    expect(labels()).not.toContain('Sales Order');
  });
});
