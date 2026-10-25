/**
 * PROJECT-REG-PORTAL fix round 1 (reviewer 3 and 4): the form is exactly the legacy fields,
 * so it has no Comments tab and no Attachments card, and AI Extract does not offer to attach.
 *
 * Mocking pattern: SubmissionForm.customerLink.test.tsx (portal-client mocked).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import type {
  PortalContact,
  PortalSubmissionDetail,
} from '../lib/portal-client';

const stableRouter = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => stableRouter }));
vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
const dialogProps = vi.hoisted(() => ({ last: null as Record<string, unknown> | null }));
vi.mock('./AIExtractDialog', () => ({
  AIExtractDialog: (props: Record<string, unknown>) => {
    dialogProps.last = props;
    return null;
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
    saveDraft: vi.fn(),
    submitDraft: vi.fn(),
    lookupDebtors: vi.fn(),
    lookupSet: vi.fn(),
  };
});

import {
  fetchMe,
  fetchRevisions,
  fetchSubmission,
  fetchSubmissionNeighbours,
  lookupDebtors,
  lookupSet,
} from '../lib/portal-client';
import { SubmissionForm } from './SubmissionForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const CONTACT: PortalContact = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'AMINAH EXAMPLE',
  phone_number: '60123456789',
  expires_at: '2026-12-01T00:00:00Z',
  visible_form_types: ['project_registration'],
} as PortalContact;

const ORDER = [
  'Project title',
  'Distributor name',
  'Sales agent',
  'Customer name',
  'Type of building',
  'State',
  'Mukim',
  'Your ref',
  'Developer',
  'Main contractor',
  'Architect',
];

function draft(over: Record<string, unknown> = {}): PortalSubmissionDetail {
  return {
    id: 'reg-1',
    kind: 'project_registration',
    title: 'CADANGAN BLOK PEJABAT',
    reference: null,
    status: 'draft',
    is_editable: true,
    is_draft: true,
    created_at: '2026-10-02T00:00:00Z',
    attachments: [],
    revision_draft: null,
    sales_agent_name: 'Aminah Example',
    possible_duplicates: [],
    reject_reason: null,
    distributor_name: 'Example Distribution Sdn Bhd',
    customer_id: 'cust-1',
    customer_name: 'Example Customer Sdn Bhd',
    type_of_building: 'Office',
    state: 'Johor',
    mukim: 'Kulai',
    your_ref: 'REF-ZZT-1',
    developer_name: 'Example Developer Sdn Bhd',
    main_contractor_name: 'Example Builders Sdn Bhd',
    architect_name: 'Example Architects',
    ...over,
  } as unknown as PortalSubmissionDetail;
}

beforeEach(() => {
  vi.clearAllMocks();
  asMock(fetchMe).mockResolvedValue(CONTACT);
  asMock(fetchSubmissionNeighbours).mockResolvedValue({
    prev_id: null,
    next_id: null,
    position: 1,
    total: 1,
  });
  asMock(fetchRevisions).mockResolvedValue([]);
  asMock(lookupDebtors).mockResolvedValue([]);
  asMock(lookupSet).mockResolvedValue({
    options: [
      { value: 'Johor', label: 'Johor' },
      { value: 'Selangor', label: 'Selangor' },
    ],
    defaultValue: null,
  });
  asMock(fetchSubmission).mockResolvedValue(draft());
});

describe('SubmissionForm - project_registration has no comments and no attachments', () => {
  it('a submitted registration shows no Comments tab', async () => {
    asMock(fetchSubmission).mockResolvedValue(
      draft({ status: 'pending', is_editable: false, is_draft: false }),
    );
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await waitFor(() =>
      expect(container.querySelector('#title')).not.toBeNull(),
    );

    expect(screen.queryByText(/^Comments/)).toBeNull();
    expect(screen.queryByRole('tab', { name: /comments/i })).toBeNull();
  });

  it('shows no Attachments card on a draft', async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await waitFor(() =>
      expect(container.querySelector('#title')).not.toBeNull(),
    );

    expect(screen.queryByText('Attachments')).toBeNull();
  });

  it('AI Extract is told it cannot attach', async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await waitFor(() =>
      expect(container.querySelector('#title')).not.toBeNull(),
    );

    expect(dialogProps.last?.canAttach).toBe(false);
  });
});
