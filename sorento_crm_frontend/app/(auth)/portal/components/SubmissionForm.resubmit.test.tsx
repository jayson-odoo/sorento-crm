/**
 * RESUBMITTED-STATUS (owner, 27 Oct): a portal form that was rejected is sent back
 * with "Resubmit", not "Submit". Every portal kind surfaces a rejected record as
 * `status: 'rejected'` (PR/SF via the backend's effective status), so one rule
 * covers them all. Mocking pattern mirrors `SubmissionForm.revisingBanner.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { submitVerb } from '../lib/portal-client';
import type {
  PortalContact,
  PortalRevisionEntry,
  PortalRevisionPolicy,
  PortalSubmissionDetail,
} from '../lib/portal-client';

const push = vi.fn();
const replace = vi.fn();
const router = { push, replace };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original =
    await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMe: vi.fn(),
    fetchSubmission: vi.fn(),
    fetchSubmissionNeighbours: vi.fn(),
    fetchRevisions: vi.fn(),
    reviseSubmission: vi.fn(),
    saveDraft: vi.fn(),
    submitDraft: vi.fn(),
    deleteDraftSubmission: vi.fn(),
    uploadAttachment: vi.fn(),
    deleteAttachment: vi.fn(),
    lookupSet: vi.fn().mockResolvedValue({ options: [], defaultValue: null }),
  };
});

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

import {
  fetchMe,
  fetchRevisions,
  fetchSubmission,
  fetchSubmissionNeighbours,
} from '../lib/portal-client';
import { SubmissionForm } from './SubmissionForm';
import { waitForSectionLoaded } from '@/test-utils';

const CONTACT: PortalContact = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'CONTACT X Lee',
  phone_number: '60123456789',
  expires_at: '2026-09-01T00:00:00Z',
};

function policy(
  over: Partial<PortalRevisionPolicy> = {},
): PortalRevisionPolicy {
  return {
    enabled: true,
    allowed: true,
    used: 1,
    max: 3,
    remaining: 2,
    blocked_reason: null,
    ...over,
  };
}

function detail(
  over: Partial<PortalSubmissionDetail> = {},
): PortalSubmissionDetail {
  return {
    id: 'si-1',
    kind: 'stock_inquiry',
    title: 'Stock inquiry',
    reference: 'SI-26-0184',
    status: 'responded',
    is_editable: false,
    is_draft: false,
    created_at: '2026-07-20T00:00:00Z',
    revision_no: 1,
    attachments: [],
    revision: policy(),
    product_code: 'ABC-123',
    item_description: 'Panel',
    quantity: '5',
    delivery_date: '',
    project_customer: '',
    project_name: '',
    salesperson_contact_id: 'contact-1',
    salesperson: 'CONTACT X Lee',
    remark: '',
    additional_remark: '',
    ...over,
  } as PortalSubmissionDetail;
}

const ORIGINAL: PortalRevisionEntry = {
  id: 'rev-0',
  version_no: 0,
  revision_no: 0,
  kind: 'original',
  label: 'Original',
  reason: null,
  submitted_at: '2026-07-20T02:00:00',
  submitted_by: 'CONTACT X Lee',
  is_reconstructed: false,
  snapshot: {},
  attachments: [],
  invalidated: null,
  voided_stage_code: null,
  voided_assignee_name: null,
  changes: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  (fetchMe as ReturnType<typeof vi.fn>).mockResolvedValue(CONTACT);
  (fetchSubmissionNeighbours as ReturnType<typeof vi.fn>).mockResolvedValue({
    prev_id: null,
    next_id: null,
    position: 1,
    total: 1,
  });
  (fetchRevisions as ReturnType<typeof vi.fn>).mockResolvedValue([ORIGINAL]);
  window.history.replaceState({}, '', '/portal/stock_inquiry/si-1');
});

async function renderAt(over: Partial<PortalSubmissionDetail> = {}) {
  (fetchSubmission as ReturnType<typeof vi.fn>).mockResolvedValue(detail(over));
  render(<SubmissionForm kind="stock_inquiry" submissionId="si-1" />);
  await waitForSectionLoaded();
  // The form reloads once more when /me resolves (contact-derived defaults).
  await waitFor(() =>
    expect(
      (fetchSubmission as ReturnType<typeof vi.fn>).mock.calls.length,
    ).toBeGreaterThanOrEqual(2),
  );
}


describe('submitVerb', () => {
  it('is Resubmit for a rejected form and Submit otherwise', () => {
    expect(submitVerb('rejected')).toBe('Resubmit');
    expect(submitVerb('draft')).toBe('Submit');
    expect(submitVerb(null)).toBe('Submit');
    expect(submitVerb(undefined)).toBe('Submit');
  });
});

describe('SubmissionForm - the submit button after a rejection', () => {
  it('reads "Resubmit" on a rejected form, and the confirm dialog says so too', async () => {
    await renderAt({ status: 'rejected', is_editable: true });

    const button = await screen.findByRole('button', {
      name: 'Resubmit stock inquiry',
    });
    expect(screen.queryByRole('button', { name: 'Submit stock inquiry' })).toBeNull();

    fireEvent.click(button);
    expect(
      await screen.findByText('Resubmit this stock inquiry?'),
    ).toBeInTheDocument();
  });

  it('still reads "Submit" on a draft', async () => {
    await renderAt({ status: 'draft', is_editable: true, is_draft: true });

    expect(
      await screen.findByRole('button', { name: 'Submit stock inquiry' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Resubmit/ })).toBeNull();
  });
});
