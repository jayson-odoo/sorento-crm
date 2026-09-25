/**
 * #1227: unit price is mandatory on every sponsorship form line, on portal
 * submission. Same validation shape `PriceTagRequestForm` already uses (see
 * `PriceTagRequestForm.validation.test.tsx`): a client-side check before
 * submit that names the offending line, and a server 422 naming
 * `line:<index>`, surfaced as "Line N: <message>".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import type { PortalContact } from '../lib/portal-client';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMe: vi.fn(),
    fetchSubmission: vi.fn(),
    fetchSubmissionNeighbours: vi.fn(),
    saveDraft: vi.fn(),
    submitDraft: vi.fn(),
    deleteDraftSubmission: vi.fn(),
    uploadAttachment: vi.fn(),
    deleteAttachment: vi.fn(),
    lookupSet: vi.fn().mockResolvedValue({ options: [], defaultValue: null }),
  };
});

import {
  fetchMe,
  fetchSubmissionNeighbours,
  saveDraft,
  submitDraft,
} from '../lib/portal-client';
import { SubmissionForm } from './SubmissionForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const CONTACT: PortalContact = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'Darren Lee',
  phone_number: '60123456789',
  expires_at: '2026-08-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  asMock(fetchMe).mockResolvedValue(CONTACT);
  asMock(fetchSubmissionNeighbours).mockResolvedValue({
    prev_id: null,
    next_id: null,
    position: 1,
    total: 1,
  });
  asMock(saveDraft).mockResolvedValue({ id: 'new-1' });
  asMock(submitDraft).mockResolvedValue({ id: 'new-1' });
});

/** Adds one item row and fills its Quantity + (optionally) Unit price cell -
 *  scoped to the products table so the page's OTHER number input ("Total
 *  project value") is never touched by mistake. */
async function addLine({ unitPrice }: { unitPrice?: string } = {}) {
  fireEvent.click(screen.getByRole('button', { name: /Add item/i }));
  const table = screen.getByRole('table');
  const spinbuttons = within(table).getAllByRole('spinbutton');
  // Row order: Quantity, Unit price, Total.
  fireEvent.change(spinbuttons[0], { target: { value: '2' } });
  if (unitPrice !== undefined) {
    fireEvent.change(spinbuttons[1], { target: { value: unitPrice } });
  }
}

function openSubmitConfirm() {
  const submitButtons = screen.getAllByRole('button', {
    name: /Submit sponsorship form/i,
  });
  // The first is the page action that opens the confirm dialog.
  fireEvent.click(submitButtons[0]);
}

function confirmSubmit() {
  const dialog = screen.getByRole('alertdialog');
  fireEvent.click(
    within(dialog).getByRole('button', { name: /Submit sponsorship form/i }),
  );
}

describe('SubmissionForm - sponsorship unit price required on submit (#1227)', () => {
  it('blocks submit client-side and names the line when unit price is missing', async () => {
    render(<SubmissionForm kind="sponsorship_form" />);
    await screen.findByText(CONTACT.name as string);

    await addLine();
    openSubmitConfirm();
    confirmSubmit();

    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith('Line 1: Unit price is required.'),
    );
    expect(await screen.findByText('Unit price is required.')).toBeInTheDocument();
    expect(saveDraft).not.toHaveBeenCalled();
    expect(submitDraft).not.toHaveBeenCalled();
  });

  it('blocks submit client-side for a blank unit price the same as a missing one', async () => {
    render(<SubmissionForm kind="sponsorship_form" />);
    await screen.findByText(CONTACT.name as string);

    await addLine({ unitPrice: '   ' });
    openSubmitConfirm();
    confirmSubmit();

    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith('Line 1: Unit price is required.'),
    );
    expect(submitDraft).not.toHaveBeenCalled();
  });

  it('blocks submit client-side for a negative unit price', async () => {
    render(<SubmissionForm kind="sponsorship_form" />);
    await screen.findByText(CONTACT.name as string);

    await addLine({ unitPrice: '-5' });
    openSubmitConfirm();
    confirmSubmit();

    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith('Line 1: Unit price is required.'),
    );
    expect(submitDraft).not.toHaveBeenCalled();
  });

  it('submits once every line has a unit price', async () => {
    render(<SubmissionForm kind="sponsorship_form" />);
    await screen.findByText(CONTACT.name as string);

    await addLine({ unitPrice: '10.00' });
    openSubmitConfirm();
    confirmSubmit();

    await waitFor(() => expect(submitDraft).toHaveBeenCalled());
    expect(toasts.error).not.toHaveBeenCalled();
  });

  it('surfaces a server 422 naming line:<index> as "Line N: <message>" (mirrors lineErrorToast)', async () => {
    asMock(submitDraft).mockRejectedValue(
      Object.assign(new Error('Unit price is required.'), {
        code: 'SPONSORSHIP_UNIT_PRICE_REQUIRED',
        fields: ['line:0'],
      }),
    );
    render(<SubmissionForm kind="sponsorship_form" />);
    await screen.findByText(CONTACT.name as string);

    // A valid unit price clears the CLIENT check, so this exercises the server
    // refusal path specifically (e.g. a race with another edit).
    await addLine({ unitPrice: '10.00' });
    openSubmitConfirm();
    confirmSubmit();

    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith('Line 1: Unit price is required.'),
    );
    expect(await screen.findByText('Unit price is required.')).toBeInTheDocument();
  });
});
