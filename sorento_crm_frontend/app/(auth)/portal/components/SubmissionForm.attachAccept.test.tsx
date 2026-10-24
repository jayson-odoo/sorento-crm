/**
 * ATTACH-ACCEPT: the attachments box on a portal form offers the file types
 * the "Portal Submission" attachment type allows, read off the `/me` the
 * form already fetches (still exactly one `/me`, D7 r3).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

import type { PortalContact } from '../lib/portal-client';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMe: vi.fn(),
    fetchSubmission: vi.fn(),
    lookupSet: vi.fn().mockResolvedValue({ options: [], defaultValue: null }),
  };
});

import { fetchMe } from '../lib/portal-client';
import { SubmissionForm } from './SubmissionForm';

const CONTACT: PortalContact = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'CONTACT X Lee',
  phone_number: '60123456789',
  expires_at: '2026-08-01T00:00:00Z',
  visible_form_types: ['complaint'],
  attachment_allowed_extensions: ['csv', 'pdf', 'png', 'xlsx'],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SubmissionForm attachments box (ATTACH-ACCEPT)', () => {
  it('offers the attachment type allowed extensions, from the one /me fetch', async () => {
    vi.mocked(fetchMe).mockResolvedValue(CONTACT);
    const { container } = render(<SubmissionForm kind="complaint" />);

    await waitFor(() =>
      expect(container.querySelector('input[type="file"]')?.getAttribute('accept')).toBe(
        '.csv,.pdf,.png,.xlsx',
      ),
    );
    expect(fetchMe).toHaveBeenCalledTimes(1);
  });
});
