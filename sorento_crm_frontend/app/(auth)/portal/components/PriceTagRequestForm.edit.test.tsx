/**
 * PLAN-portal-price-tag-journey-r8, Round 3 (R3-1, R3-5, AC-R7).
 *
 * REPLACES the S8-era Edit / Save / Cancel contract this file used to pin
 * (post-submit PUT via an "Edit" header button): R3-1 reverses that - a
 * submitted price tag request is read-only exactly like a stock inquiry, and
 * a change goes through the portal revision engine instead. So:
 *
 *  - No "Edit" button ever renders for a submitted (non-draft) request.
 *  - The header holds exactly ONE gear (`DetailActionsMenu`) with Duplicate,
 *    Download PDF, and Revise - Revise present only when the revision policy
 *    (`useRevisionPolicy`, the same hook `SubmissionForm` reads) allows it;
 *    otherwise the policy's `blocked_reason` renders in the header line and
 *    no Revise item exists at all.
 *  - Tapping Revise switches to a revise mode: a reason field, the sections
 *    editable, and a "Submit revision" button (never "Save"/"Save draft").
 *    Submit revision calls the revise action (`useReviseSubmission`, the
 *    same hook `SubmissionForm` reads to call `reviseSubmission`) and
 *    returns to the read view on success.
 *
 * `DetailActionsMenu` / `DropdownMenuItem` are stood in for plain markup
 * (not the real Radix DropdownMenu) - same reasoning as
 * `PriceTagRequestForm.readOnlyGear.test.tsx`: the real one mounts a Portal +
 * `motion/react` AnimatePresence that flickers sibling text in jsdom, and
 * what this file owns is the wiring, not the menu primitive itself.
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
  downloadPriceTagPdf: vi.fn(),
}));

// Same generic hooks `SubmissionForm` already reads for the legacy kinds
// (`app/(auth)/portal/hooks/useRevisions.ts`) - R3-1 has `PriceTagRequestForm`
// reuse them rather than a second revise mechanism (plan D-P1/"R3-1").
const { revisePolicyMock, reviseMock, revisionHistoryMock } = vi.hoisted(() => ({
  revisePolicyMock: vi.fn(),
  reviseMock: vi.fn(),
  revisionHistoryMock: vi.fn(),
}));
vi.mock('../hooks/useRevisions', () => ({
  useRevisionPolicy: revisePolicyMock,
  useReviseSubmission: () => ({ revise: reviseMock, submitting: false }),
  useRevisionHistory: revisionHistoryMock,
}));

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

vi.mock('./AttachmentDropzone', () => ({
  AttachmentDropzone: () => null,
}));

import { getRequest } from '../lib/price-tag-request-service';
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

const BLOCKED_POLICY = {
  enabled: true,
  allowed: false,
  used: 3,
  max: 3,
  remaining: 0,
  blocked_reason: 'You have used all 3 revisions.',
};

beforeEach(() => {
  vi.clearAllMocks();
  revisePolicyMock.mockReturnValue({ policy: ALLOWED_POLICY, loading: false });
  reviseMock.mockResolvedValue({
    submission: baseRequest({ debtor_name: 'ZZT Revised Dealer' }),
    revision: ALLOWED_POLICY,
    revision_no: 1,
  });
  revisionHistoryMock.mockReturnValue({
    entries: [],
    loading: false,
    error: null,
    reload: vi.fn(),
  });
});

describe('PriceTagRequestForm - no Edit after submit (R3-1, AC-R7)', () => {
  it.each(['new', 'changes_requested', 'designing', 'proof_ready', 'approved', 'ready', 'void'])(
    'never shows an Edit button for a submitted request at status %s',
    async (status) => {
      asMock(getRequest).mockResolvedValue(baseRequest({ status, portal_draft_at: null }));

      render(<PriceTagRequestForm requestId="req-1" />);

      await screen.findByText('PT-202609-0001');
      expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    },
  );
});

describe('PriceTagRequestForm - one gear with Duplicate, Download PDF, Revise (AC-R7)', () => {
  it('renders exactly one gear, holding Duplicate, Download PDF and Revise when the policy allows it', async () => {
    revisePolicyMock.mockReturnValue({ policy: ALLOWED_POLICY, loading: false });
    asMock(getRequest).mockResolvedValue(baseRequest({ status: 'new', portal_draft_at: null }));

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    expect(screen.getAllByTestId('gear-menu')).toHaveLength(1);
    const gear = screen.getByTestId('gear-menu');
    expect(screen.getByText('Duplicate')).toBeInTheDocument();
    expect(screen.getByText('Download PDF')).toBeInTheDocument();
    expect(gear).toHaveTextContent('Revise');
  });

  it('hides Revise and shows the blocked reason in the header line when the policy refuses it', async () => {
    revisePolicyMock.mockReturnValue({ policy: BLOCKED_POLICY, loading: false });
    asMock(getRequest).mockResolvedValue(baseRequest({ status: 'ready', portal_draft_at: null }));

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    expect(screen.getByTestId('gear-menu')).not.toHaveTextContent('Revise');
    expect(screen.getByText('You have used all 3 revisions.')).toBeInTheDocument();
  });
});

describe('PriceTagRequestForm - Revise mode (AC-R7)', () => {
  it('tapping Revise shows a reason field and a Submit revision button', async () => {
    asMock(getRequest).mockResolvedValue(baseRequest({ status: 'new', portal_draft_at: null }));

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    fireEvent.click(screen.getByText('Revise'));

    expect(await screen.findByLabelText(/reason/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit revision' })).toBeInTheDocument();
  });

  it('Submit revision calls the revise action and returns to the read view', async () => {
    asMock(getRequest).mockResolvedValue(baseRequest({ status: 'new', portal_draft_at: null }));

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    fireEvent.click(screen.getByText('Revise'));
    const reasonField = await screen.findByLabelText(/reason/i);
    fireEvent.change(reasonField, { target: { value: 'Dealer changed their mind' } });

    fireEvent.click(screen.getByRole('button', { name: 'Submit revision' }));

    await waitFor(() =>
      expect(reviseMock).toHaveBeenCalledWith(
        expect.objectContaining({ reason: 'Dealer changed their mind' }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Submit revision' })).toBeNull(),
    );
    expect(screen.getByText('PT-202609-0001')).toBeInTheDocument();
  });
});

describe('PriceTagRequestForm - Revisions tab (AC-R7 second half)', () => {
  it('a saved request with an enabled policy shows a Revisions tab listing the history rows', async () => {
    revisePolicyMock.mockReturnValue({ policy: ALLOWED_POLICY, loading: false });
    revisionHistoryMock.mockReturnValue({
      entries: [
        {
          id: 'rev-0',
          version_no: 0,
          revision_no: 0,
          kind: 'original',
          label: 'Original',
          reason: null,
          submitted_at: '2026-09-01T00:00:00Z',
          submitted_by: 'ZZT Dealer',
          is_reconstructed: false,
          snapshot: {},
          snapshot_fields: [],
          attachments: [],
          invalidated: null,
          voided_stage_code: null,
          voided_assignee_name: null,
          voided_stages: [],
          changes: [],
        },
        {
          id: 'rev-1',
          version_no: 1,
          revision_no: 1,
          kind: 'revision',
          label: 'Revision 1',
          reason: 'Dealer changed their mind',
          submitted_at: '2026-09-05T00:00:00Z',
          submitted_by: 'ZZT Dealer',
          is_reconstructed: false,
          snapshot: {},
          snapshot_fields: [],
          attachments: [],
          invalidated: null,
          voided_stage_code: null,
          voided_assignee_name: null,
          voided_stages: [],
          changes: [],
        },
      ],
      loading: false,
      error: null,
      reload: vi.fn(),
    });
    asMock(getRequest).mockResolvedValue(baseRequest({ status: 'new', portal_draft_at: null }));

    render(<PriceTagRequestForm requestId="req-1" />);
    await screen.findByText('PT-202609-0001');

    const revisionsTab = screen.getByRole('tab', { name: /Revisions/ });
    // Radix Tabs' default `activationMode="automatic"` switches on FOCUS,
    // which a bare `fireEvent.click` does not synthesize in jsdom.
    revisionsTab.focus();
    fireEvent.click(revisionsTab);
    await waitFor(() => expect(revisionsTab).toHaveAttribute('data-state', 'active'));

    expect(await screen.findByText('Original')).toBeInTheDocument();
    expect(screen.getByText('Revision 1')).toBeInTheDocument();
  });
});
