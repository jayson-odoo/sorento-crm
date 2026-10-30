/**
 * PORTAL-P4-REQUESTS R2 (PAR-2): the portal's own SubmissionForm is unchanged. A sponsorship form opened on the portal
 * with no seed sends no project_id; the ?project_id= seeding lives on the CRM side only.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { PortalContact } from '../lib/portal-client';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('project_id=5b0c1d2e-aaaa-4bbb-8ccc-0123456789ab'),
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock('../lib/portal-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/portal-client')>()),
  fetchMe: vi.fn(),
  fetchSubmission: vi.fn(),
  fetchSubmissionNeighbours: vi.fn(),
  fetchRevisions: vi.fn(),
  saveDraft: vi.fn(),
  lookupSet: vi.fn().mockResolvedValue({ options: [], defaultValue: null }),
  lookupProjects: vi.fn().mockResolvedValue([]),
}));
import { fetchMe, saveDraft } from '../lib/portal-client';
import { SubmissionForm } from './SubmissionForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const CONTACT: PortalContact = {
  contact_id: 'contact-1', space_id: 'space-1', name: 'Contact A', phone_number: '60123456789', expires_at: '2030-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  asMock(fetchMe).mockResolvedValue(CONTACT);
  asMock(saveDraft).mockResolvedValue({ id: 'new-1' });
});

describe('portal SubmissionForm sponsorship_form never reads a project seed', () => {
  it('Save as draft sends no project_id even when the URL carries ?project_id=', async () => {
    render(<SubmissionForm kind="sponsorship_form" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Save as draft' }));
    await waitFor(() => expect(saveDraft).toHaveBeenCalled());
    const fields = asMock(saveDraft).mock.calls[0][1] as Record<string, unknown>;
    expect(fields.project_id ?? null).toBeNull();
  });
});
