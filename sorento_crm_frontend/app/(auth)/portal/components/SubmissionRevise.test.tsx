/**
 * SubmissionForm in revise mode
 * (UAC-portal-submission-revisions B2 / B3 / D1 / E1 / E1a / E2 / AB2 / G3).
 *
 * Scoped to `kind="stock_inquiry"` (simplest field set), which exercises the
 * branch shared verbatim by the other revisable kinds.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import type {
  PortalContact,
  PortalRevisionEntry,
  PortalRevisionPolicy,
  PortalSubmissionDetail,
} from '../lib/portal-client';

const push = vi.fn();
const replace = vi.fn();
// One stable router object: a fresh one per render would change the identity
// the load effect depends on and refetch the submission forever.
const router = { push, replace };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
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
  reviseSubmission,
} from '../lib/portal-client';
import { SubmissionForm } from './SubmissionForm';

const CONTACT: PortalContact = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'Darren Lee',
  phone_number: '60123456789',
  expires_at: '2026-09-01T00:00:00Z',
};

function policy(over: Partial<PortalRevisionPolicy> = {}): PortalRevisionPolicy {
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

function detail(over: Partial<PortalSubmissionDetail> = {}): PortalSubmissionDetail {
  return {
    id: 'si-1',
    kind: 'stock_inquiry',
    title: 'Stock inquiry',
    reference: 'SI-26-0184',
    status: 'pending_purchasing',
    is_editable: false,
    is_draft: false,
    created_at: '2026-07-20T00:00:00Z',
    attachments: [],
    revision: policy(),
    product_code: 'ABC-123',
    item_description: 'Panel',
    quantity: '5',
    delivery_date: '',
    project_customer: '',
    project_name: '',
    salesperson_contact_id: 'contact-1',
    salesperson: 'Darren Lee',
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
  submitted_by: 'Darren Lee',
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
  // The `?revise=1` cases below drive the URL; reset it so one case cannot leak a
  // deep link into the next.
  window.history.replaceState({}, '', '/portal/stock_inquiry/si-1');
});

async function waitForLoaded() {
  await waitFor(() => expect(screen.queryByText(/^loading/i)).toBeNull());
}

async function renderRevisable(over: Partial<PortalSubmissionDetail> = {}) {
  (fetchSubmission as ReturnType<typeof vi.fn>).mockResolvedValue(detail(over));
  render(<SubmissionForm kind="stock_inquiry" submissionId="si-1" />);
  await waitForLoaded();
  // The form reloads once more when /me resolves (contact-derived defaults).
  // Settle it before touching fields, or that reload lands mid-test and looks
  // like the edit was thrown away.
  await waitFor(() =>
    expect(
      (fetchSubmission as ReturnType<typeof vi.fn>).mock.calls.length,
    ).toBeGreaterThanOrEqual(2),
  );
  await waitFor(() => expect(screen.queryByText(/^loading/i)).toBeNull());
}

/** Open the composer and type a valid reason. */
async function openComposer(reason = 'Customer moved the delivery date.') {
  fireEvent.click(await screen.findByRole('button', { name: 'Revise' }));
  const box = screen.getByLabelText(/what changed, and why\?/i);
  fireEvent.change(box, { target: { value: reason } });
  return box;
}

describe('SubmissionForm - revise entry point', () => {
  it('shows the action and the remaining budget when the policy allows it', async () => {
    await renderRevisable();

    expect(await screen.findByRole('button', { name: 'Revise' })).toBeInTheDocument();
    expect(screen.getByText('2 of 3 revisions left')).toBeInTheDocument();
  });

  it('renders one sentence and no action when the cap is used up', async () => {
    await renderRevisable({
      revision: policy({
        allowed: false,
        used: 3,
        remaining: 0,
        blocked_reason: 'You have used all 3 revisions.',
      }),
    });

    expect(screen.queryByRole('button', { name: 'Revise' })).toBeNull();
    expect(screen.getByText('You have used all 3 revisions.')).toBeInTheDocument();
  });

  it('renders one sentence and no action when the type is disabled', async () => {
    await renderRevisable({
      revision: policy({
        enabled: false,
        allowed: false,
        max: 0,
        remaining: 0,
        blocked_reason: 'This form cannot be revised.',
      }),
    });

    expect(screen.queryByRole('button', { name: 'Revise' })).toBeNull();
    expect(screen.getByText('This form cannot be revised.')).toBeInTheDocument();
  });

  it('renders one sentence and no action on a terminal status', async () => {
    await renderRevisable({
      status: 'closed',
      revision: policy({
        allowed: false,
        blocked_reason: 'This stock inquiry is closed and can no longer be revised.',
      }),
    });

    expect(screen.queryByRole('button', { name: 'Revise' })).toBeNull();
    expect(
      screen.getByText('This stock inquiry is closed and can no longer be revised.'),
    ).toBeInTheDocument();
  });

  it('always renders the revision history section', async () => {
    await renderRevisable({
      revision: policy({ allowed: false, blocked_reason: 'This form cannot be revised.' }),
    });

    expect(await screen.findByText('Revision history')).toBeInTheDocument();
    expect(screen.getByText('Original')).toBeInTheDocument();
  });
});

describe('SubmissionForm - revise composer', () => {
  it('opens the form pre-filled and keeps the requestor frozen', async () => {
    await renderRevisable();
    fireEvent.click(await screen.findByRole('button', { name: 'Revise' }));

    // Pre-filled with the current values, and editable again.
    const quantity = document.getElementById('quantity') as HTMLInputElement;
    expect(quantity.value).toBe('5');
    expect(quantity.disabled).toBe(false);
    // The requestor is the routing key: not editable on a revision (AB2).
    const salesperson = document.getElementById('salesperson_contact_id');
    expect(salesperson).toHaveAttribute('disabled');
  });

  it('refuses a blank reason: no confirm dialog, one message', async () => {
    await renderRevisable();
    fireEvent.click(await screen.findByRole('button', { name: 'Revise' }));
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));

    expect(screen.getByText('Tell us what changed and why.')).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(reviseSubmission).not.toHaveBeenCalled();
  });

  it('accepts a short reason: no character floor, by explicit decision', async () => {
    await renderRevisable();
    await openComposer('hi');
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(screen.queryByText('Tell us what changed and why.')).toBeNull();
  });

  it('states the three consequences in the confirm dialog, in the contact’s terms', async () => {
    await renderRevisable();
    await openComposer();
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Send revision 2?');
    // No `restart_stage_label` on this policy, so the generic sentence stands.
    expect(dialog).toHaveTextContent(
      'The office stops work on the current version. This stock inquiry goes back to the start of its approval flow. You will have 1 revision left.',
    );
    // PR and SF do not route to purchasing, so the copy never names it (E1a).
    expect(dialog.textContent).not.toMatch(/purchasing/i);
  });

  /**
   * The dialog must not promise a destination the revision does not go to (E1a).
   * The backend computes `restart_stage_label` from this type's config precisely so
   * the copy can name it: a purchase request restarting at Project Sales has to say
   * Project Sales. The generic sentence above is the fallback, not the target.
   */
  it('names the restart destination the backend supplies', async () => {
    await renderRevisable({ revision: policy({ restart_stage_label: 'Project Sales' }) });
    await openComposer();
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent(
      'The office stops work on the current version. This stock inquiry goes back to Project Sales. You will have 1 revision left.',
    );
    expect(dialog.textContent).not.toContain('the start of its approval flow');
    expect(dialog.textContent).not.toMatch(/purchasing/i);
  });

  it('names a different destination for a type that restarts elsewhere', async () => {
    await renderRevisable({ revision: policy({ restart_stage_label: 'Customer Service' }) });
    await openComposer();
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));

    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'goes back to Customer Service.',
    );
  });

  it('falls back to the generic sentence when the backend names nothing', async () => {
    await renderRevisable({ revision: policy({ restart_stage_label: null }) });
    await openComposer();
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));

    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'This stock inquiry goes back to the start of its approval flow.',
    );
  });

  it('cancelling the dialog sends nothing and leaves the edit intact', async () => {
    await renderRevisable();
    await openComposer();
    const quantity = document.getElementById('quantity') as HTMLInputElement;
    fireEvent.change(quantity, { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    expect(reviseSubmission).not.toHaveBeenCalled();
    expect((document.getElementById('quantity') as HTMLInputElement).value).toBe('9');
  });

  it('sends the reason plus the version the contact was looking at', async () => {
    await renderRevisable();
    (reviseSubmission as ReturnType<typeof vi.fn>).mockResolvedValue({
      submission: detail({ revision: policy({ used: 2, remaining: 1 }) }),
      revision: policy({ used: 2, remaining: 1 }),
      revision_no: 2,
    });
    await openComposer();
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send revision' }));

    await waitFor(() => expect(reviseSubmission).toHaveBeenCalled());
    const [kind, id, input] = (reviseSubmission as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(kind).toBe('stock_inquiry');
    expect(id).toBe('si-1');
    expect(input.reason).toBe('Customer moved the delivery date.');
    // Echoed so a double tap comes back 409 instead of applying twice.
    expect(input.expectedRevisionNo).toBe(1);
    expect(input.fields.quantity).toBe('5');
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Revision sent.'));
  });

  it('surfaces the server sentence on a 409 (someone revised it first)', async () => {
    await renderRevisable();
    (reviseSubmission as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error(
        'This stock inquiry was revised while you were working on it. Reload to see revision 2.',
      ),
    );
    await openComposer();
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send revision' }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'This stock inquiry was revised while you were working on it. Reload to see revision 2.',
      ),
    );
  });

  it('surfaces the server sentence on a 422 (policy refused it)', async () => {
    await renderRevisable();
    (reviseSubmission as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('You have used all 3 revisions.'),
    );
    await openComposer();
    fireEvent.click(screen.getByRole('button', { name: 'Send revision' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send revision' }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('You have used all 3 revisions.'),
    );
  });
});

/**
 * The `?revise=1` deep link (UAC B2 / B6).
 *
 * The long-press preview card links here with the composer pre-opened. That link is
 * bookmarkable and shareable, so it outlives the eligibility that produced it: the
 * policy decides, not the URL. Opening the composer on a submission the policy
 * refuses unlocks every field and asks for a reason, then fails at submit with a
 * 422 - the affordance has to be absent instead.
 */
describe('SubmissionForm - the ?revise=1 deep link', () => {
  const deepLink = () =>
    window.history.replaceState({}, '', '/portal/stock_inquiry/si-1?revise=1');

  it('opens the composer when the policy allows it', async () => {
    deepLink();
    await renderRevisable();

    expect(await screen.findByLabelText(/what changed, and why\?/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send revision' })).toBeInTheDocument();
  });

  it('does not open the composer when the policy blocks it', async () => {
    deepLink();
    await renderRevisable({
      status: 'closed',
      revision: policy({
        allowed: false,
        blocked_reason: 'This stock inquiry is closed and can no longer be revised.',
      }),
    });

    expect(screen.queryByLabelText(/what changed, and why\?/i)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Send revision' })).toBeNull();
    // And the form stays locked - the harm is not just the missing button, it is
    // that the contact could retype the whole submission.
    expect(document.getElementById('quantity')).toHaveAttribute('disabled');
    expect(
      screen.getByText('This stock inquiry is closed and can no longer be revised.'),
    ).toBeInTheDocument();
  });

  it('strips the parameter either way, so a refresh does not re-enter it', async () => {
    deepLink();
    await renderRevisable();
    expect(window.location.search).toBe('');

    deepLink();
    await renderRevisable({
      revision: policy({ allowed: false, blocked_reason: 'This form cannot be revised.' }),
    });
    expect(window.location.search).toBe('');
  });

  it('leaves the composer closed with no deep link, whatever the policy says', async () => {
    await renderRevisable();

    expect(screen.queryByLabelText(/what changed, and why\?/i)).toBeNull();
    expect(await screen.findByRole('button', { name: 'Revise' })).toBeInTheDocument();
  });
});
