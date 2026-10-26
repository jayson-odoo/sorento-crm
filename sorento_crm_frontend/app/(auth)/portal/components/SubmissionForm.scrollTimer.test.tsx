/** PORTAL-TIMER-FLAKE: the "scroll to the first invalid field" timer never outlives the form.
 *  A pending timer that fired after jsdom teardown failed CI with "document is not defined". */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import type { PortalContact } from '../lib/portal-client';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

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

import { fetchMe, fetchSubmissionNeighbours, saveDraft, submitDraft } from '../lib/portal-client';
import { SubmissionForm } from './SubmissionForm';

const CONTACT: PortalContact = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'CONTACT X Lee',
  phone_number: '60123456789',
  expires_at: '2026-08-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  (fetchMe as Mock).mockResolvedValue(CONTACT);
  (fetchSubmissionNeighbours as Mock).mockResolvedValue({ prev_id: null, next_id: null, position: 1, total: 1 });
  (saveDraft as Mock).mockResolvedValue({ id: 'new-1' });
  (submitDraft as Mock).mockResolvedValue({ id: 'new-1' });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function submitEmpty() {
  fireEvent.click(screen.getAllByRole('button', { name: /Submit sponsorship form/i })[0]);
  const dialog = screen.queryByRole('alertdialog');
  if (dialog) {
    fireEvent.click(within(dialog).getByRole('button', { name: /Submit sponsorship form/i }));
  }
  expect(toasts.error).toHaveBeenCalledWith(expect.stringMatching(/^Missing \d+ required field/));
}

function fieldLookups(spy: ReturnType<typeof vi.spyOn>) {
  return spy.mock.calls.filter(([sel]) => String(sel).startsWith('[data-field-name='));
}

describe('SubmissionForm scroll-to-invalid timer', () => {
  it('still scrolls to the first invalid field while mounted', async () => {
    render(<SubmissionForm kind="sponsorship_form" />);
    await screen.findByText(CONTACT.name as string);
    vi.useFakeTimers();
    const spy = vi.spyOn(document, 'querySelector');

    submitEmpty();
    vi.advanceTimersByTime(100);

    expect(fieldLookups(spy).length).toBe(1);
  });

  it('a timer pending at unmount is cleared and never touches document', async () => {
    const { unmount } = render(<SubmissionForm kind="sponsorship_form" />);
    await screen.findByText(CONTACT.name as string);
    vi.useFakeTimers();
    const spy = vi.spyOn(document, 'querySelector');

    submitEmpty();
    unmount();
    vi.advanceTimersByTime(100);

    expect(fieldLookups(spy)).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
  });
});
