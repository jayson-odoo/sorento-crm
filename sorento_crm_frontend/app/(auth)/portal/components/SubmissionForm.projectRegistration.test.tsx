/**
 * PROJECT-REG-PORTAL UAC G1 (and A4's display side): the Project Registration form shows
 * exactly the legacy fields in the legacy order, the sales agent read-only as a NAME, and the
 * existing AI Extract button.
 *
 * Mocking pattern: SubmissionForm.customerLink.test.tsx (portal-client mocked).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import type {
  PortalContact,
  PortalSubmissionDetail,
} from '../lib/portal-client';

const stableRouter = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => stableRouter }));
vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock('./AIExtractDialog', () => ({ AIExtractDialog: () => null }));

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
  saveDraft,
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

function labelOrder(container: HTMLElement): string[] {
  const texts = Array.from(container.querySelectorAll('label')).map((l) =>
    (l.textContent ?? '').replace(/\s*\*\s*$/, '').trim(),
  );
  return ORDER.filter((name) => texts.includes(name)).sort(
    (a, b) => texts.indexOf(a) - texts.indexOf(b),
  );
}

describe('SubmissionForm - project_registration (G1)', () => {
  it('shows exactly the legacy fields in the legacy order', async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await screen.findByText('Project Registration', { selector: 'h2' });
    await waitFor(() =>
      expect(container.querySelector('#title')).not.toBeNull(),
    );

    expect(labelOrder(container)).toEqual(ORDER);
    // Nothing else sits in the field grid: no status, no id, no hidden customer id.
    const grid = container.querySelector('.grid.grid-cols-1') as HTMLElement;
    const labels = Array.from(grid.querySelectorAll('label'))
      .map((l) => (l.textContent ?? '').replace(/\s*\*\s*$/, '').trim())
      .filter((text) => text !== 'Date'); // the read-only submitted date is asserted on its own
    expect(labels).toEqual(ORDER);
  });

  it('shows the sales agent as read-only text carrying the NAME', async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await waitFor(() =>
      expect(container.querySelector('#sales_agent_name')).not.toBeNull(),
    );

    const agent = container.querySelector(
      '#sales_agent_name',
    ) as HTMLInputElement;
    expect(agent.value).toBe('Aminah Example');
    expect(agent.disabled || agent.readOnly).toBe(true);
  });

  it('prefills the saved values, including the debtor name and the typed developer', async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await waitFor(() =>
      expect(container.querySelector('#developer_name')).not.toBeNull(),
    );

    expect(
      (container.querySelector('#developer_name') as HTMLInputElement).value,
    ).toBe('Example Developer Sdn Bhd');
    expect(
      (container.querySelector('#customer_name') as HTMLInputElement).value,
    ).toBe('Example Customer Sdn Bhd');
    expect((container.querySelector('#mukim') as HTMLInputElement).value).toBe(
      'Kulai',
    );
  });

  it('marks Project title, State and Developer required', async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await waitFor(() =>
      expect(container.querySelector('#title')).not.toBeNull(),
    );

    const required = Array.from(container.querySelectorAll('label'))
      .filter((l) => (l.textContent ?? '').includes('*'))
      .map((l) => (l.textContent ?? '').replace(/\s*\*\s*$/, '').trim());
    expect(required).toEqual(['Project title', 'State', 'Developer']);
  });

  it('offers the existing AI Extract button on an editable registration', async () => {
    render(<SubmissionForm kind="project_registration" submissionId="reg-1" />);

    expect(await screen.findByTestId('ai-extract-trigger')).toHaveTextContent(
      'AI Extract',
    );
  });

  it('a new registration also opens with the form, the same field order and AI Extract', async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" />,
    );
    await screen.findByText('Project Registration', { selector: 'h2' });

    expect(labelOrder(container)).toEqual(ORDER);
    expect(await screen.findByTestId('ai-extract-trigger')).toBeInTheDocument();
    const agent = container.querySelector(
      '#sales_agent_name',
    ) as HTMLInputElement;
    expect(agent.disabled || agent.readOnly).toBe(true);
  });

  it('a submitted registration is read-only: no AI Extract', async () => {
    asMock(fetchSubmission).mockResolvedValue(
      draft({ status: 'pending', is_editable: false, is_draft: false }),
    );
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    await waitFor(() =>
      expect(container.querySelector('#title')).not.toBeNull(),
    );

    expect(screen.queryByTestId('ai-extract-trigger')).toBeNull();
    expect(
      (container.querySelector('#title') as HTMLTextAreaElement).disabled,
    ).toBe(true);
  });

  it('shows a read-only Date, the submitted date as DD/MM/YYYY (audit round 3, item 11)', async () => {
    asMock(fetchSubmission).mockResolvedValue(
      draft({
        status: 'pending',
        is_editable: false,
        is_draft: false,
        submitted_at: '2026-10-02T08:00:00',
      }),
    );
    const { container } = render(
      <SubmissionForm kind="project_registration" submissionId="reg-1" />,
    );
    const label = await screen.findByText('Date', { selector: 'label' });
    const input = container.querySelector(
      `#${label.getAttribute('for')}`,
    ) as HTMLInputElement;
    expect(input.value).toBe('02/10/2026');
    expect(input.disabled || input.readOnly).toBe(true);
  });

  it('the Customer name picker takes a pick only: typed free text is not kept (audit round 3, item 8)', async () => {
    asMock(saveDraft).mockResolvedValue({ id: 'new-1' });
    const { container } = render(
      <SubmissionForm kind="project_registration" />,
    );
    await screen.findByText('Project Registration', { selector: 'h2' });
    const input = container.querySelector('#customer_name') as HTMLInputElement;

    fireEvent.change(input, { target: { value: 'WALK-IN BUYER' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.blur(input);
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Save as draft' })[0],
    );

    await waitFor(() => expect(saveDraft).toHaveBeenCalled());
    const sent = asMock(saveDraft).mock.calls.at(-1)?.[1] as Record<
      string,
      unknown
    >;
    expect([null, undefined, '']).toContain(sent.customer_name);
    expect([null, undefined, '']).toContain(sent.customer_id);
    expect(input.value).not.toBe('WALK-IN BUYER');
  });

  it('a pick still works and sends the debtor (audit round 3, item 8)', async () => {
    asMock(saveDraft).mockResolvedValue({ id: 'new-1' });
    asMock(lookupDebtors).mockResolvedValue([
      {
        customer_id: 'cust-1',
        debtor_name: 'DEBTOR ONE SDN BHD',
        customer_code: 'D-1',
        sales_type: null,
      },
    ]);
    const { container } = render(
      <SubmissionForm kind="project_registration" />,
    );
    await screen.findByText('Project Registration', { selector: 'h2' });
    const input = container.querySelector('#customer_name') as HTMLInputElement;

    fireEvent.focus(input);
    fireEvent.click(
      await screen.findByRole('option', { name: /DEBTOR ONE SDN BHD/ }),
    );
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Save as draft' })[0],
    );

    await waitFor(() => expect(saveDraft).toHaveBeenCalled());
    const sent = asMock(saveDraft).mock.calls.at(-1)?.[1] as Record<
      string,
      unknown
    >;
    expect(sent.customer_id).toBe('cust-1');
    expect(sent.customer_name).toBe('DEBTOR ONE SDN BHD');
  });

  it("asks the lookup for this kind, so only the agent's own debtors are offered (item 2)", async () => {
    const { container } = render(
      <SubmissionForm kind="project_registration" />,
    );
    await screen.findByText('Project Registration', { selector: 'h2' });
    fireEvent.focus(
      container.querySelector('#customer_name') as HTMLInputElement,
    );

    await waitFor(() => expect(lookupDebtors).toHaveBeenCalled());
    const args = asMock(lookupDebtors)
      .mock.calls.flat()
      .map((a) => JSON.stringify(a));
    expect(args.join(' ')).toContain('project_registration');
  });
});
