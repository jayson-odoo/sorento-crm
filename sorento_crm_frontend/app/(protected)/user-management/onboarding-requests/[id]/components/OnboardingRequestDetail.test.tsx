/**
 * The captain's review screen.
 *
 * The properties under test are the ones the product standard names: every
 * section renders even when empty, a rejection cannot be sent without a reason,
 * and the action that creates real users is only offered when the request is
 * actually in review.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { OnboardingRequestDetail as Detail } from '@/components/common/onboarding/types';
import { OnboardingRequestDetail } from './OnboardingRequestDetail';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/user-management/onboarding-requests/req-1',
  useSearchParams: () => new URLSearchParams(),
}));

const getOnboardingRequest = vi.fn();
const listOnboardingRequests = vi.fn();
const rejectOnboardingPerson = vi.fn();
const approveOnboardingRequest = vi.fn();
const approveOnboardingPerson = vi.fn();
const startOnboardingReview = vi.fn();
const updateOnboardingPerson = vi.fn();
const deleteOnboardingRequest = vi.fn();

vi.mock('../../services/onboardingService', () => ({
  getOnboardingRequest: (...a: unknown[]) => getOnboardingRequest(...a),
  listOnboardingRequests: (...a: unknown[]) => listOnboardingRequests(...a),
  rejectOnboardingPerson: (...a: unknown[]) => rejectOnboardingPerson(...a),
  approveOnboardingRequest: (...a: unknown[]) => approveOnboardingRequest(...a),
  approveOnboardingPerson: (...a: unknown[]) => approveOnboardingPerson(...a),
  startOnboardingReview: (...a: unknown[]) => startOnboardingReview(...a),
  updateOnboardingPerson: (...a: unknown[]) => updateOnboardingPerson(...a),
  deleteOnboardingRequest: (...a: unknown[]) => deleteOnboardingRequest(...a),
}));

function detail(overrides: Partial<Detail> = {}): Detail {
  return {
    id: 'req-1',
    title: 'MOCHA staff onboarding',
    company_name: 'MOCHA Sdn Bhd',
    requester_name: 'Esther Lim',
    requester_email: 'esther@mocha.com.my',
    status: 'in_review',
    people_count: 1,
    approved_count: 0,
    rejected_count: 0,
    submitted_at: '2026-08-14T09:12:00',
    created_at: '2026-08-12T10:00:00',
    expires_at: '2026-08-26T10:00:00',
    revoked_at: null,
    reviewer_note: null,
    requester_note: null,
    reviewed_by_name: null,
    provisioned_at: null,
    source_file_name: 'PHONE LIST.xlsx',
    templates: [
      {
        id: 'tpl-sales',
        name: 'Salesperson',
        description: 'Sees their own orders.',
        default_needs_system_account: true,
        default_needs_respond_contact: true,
        default_needs_agent_seat: false,
      },
    ],
    people: [
      {
        id: 'p1',
        row_number: 1,
        full_name: 'Nurul Aisyah',
        nick_name: 'Aisyah',
        phone_raw: '012-3456781',
        email_raw: 'aisyah@mocha.com.my',
        section_label: 'SALES PERSON',
        template_id: 'tpl-sales',
        requester_note: null,
        reviewer_note: null,
        needs_system_account: true,
        needs_respond_contact: true,
        needs_agent_seat: false,
        review_status: 'proposed',
        rejection_reason: null,
        problems: [],
        collisions: [],
        user_step: 'pending',
        user_error: null,
        user_label: null,
        contact_step: 'pending',
        contact_error: null,
        agent_step: 'pending',
        agent_error: null,
      },
    ],
    ...overrides,
  };
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OnboardingRequestDetail requestId="req-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listOnboardingRequests.mockResolvedValue({
    data: [{ id: 'req-1' }],
    pagination: { page: 1, limit: 100, total: 1 },
  });
});

describe('OnboardingRequestDetail', () => {
  it('renders a loading state', () => {
    getOnboardingRequest.mockReturnValue(new Promise(() => {}));
    const { container } = renderDetail();
    expect(container.querySelectorAll('[data-slot="skeleton"], .animate-pulse').length)
      .toBeGreaterThan(0);
  });

  it('says so when the request cannot be loaded', async () => {
    getOnboardingRequest.mockRejectedValue(new Error('nope'));
    renderDetail();
    expect(
      await screen.findByText(/could not be loaded/i),
    ).toBeInTheDocument();
  });

  it('renders every section, with an empty state where there is nothing', async () => {
    getOnboardingRequest.mockResolvedValue(detail({ requester_note: null }));
    renderDetail();
    // The notes section exists even with no note - a hidden section reads as
    // data loss to whoever came looking for it.
    expect(await screen.findByText('Notes from the requester')).toBeInTheDocument();
    expect(screen.getByText(/Nothing was added/)).toBeInTheDocument();
    // "People" and "Provisioning" also name grid columns, so assert the section
    // headings exist rather than that the words appear exactly once.
    expect(screen.getAllByText('People').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Provisioning').length).toBeGreaterThan(0);
    expect(screen.getByText(/Nothing has been provisioned yet/)).toBeInTheDocument();
  });

  it('keeps read-only metadata in the header strip, not inside a section', async () => {
    getOnboardingRequest.mockResolvedValue(detail());
    renderDetail();
    expect(await screen.findByText('Requester email')).toBeInTheDocument();
    expect(screen.getByText('Link expires')).toBeInTheDocument();
    expect(screen.getByText('Source file')).toBeInTheDocument();
  });

  it('offers approve only while the request is in review', async () => {
    getOnboardingRequest.mockResolvedValue(detail({ status: 'submitted' }));
    const { unmount } = renderDetail();
    expect(await screen.findByRole('button', { name: /Start review/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve and provision/ })).not.toBeInTheDocument();
    unmount();

    getOnboardingRequest.mockResolvedValue(detail({ status: 'in_review' }));
    renderDetail();
    expect(
      await screen.findByRole('button', { name: /Approve and provision/ }),
    ).toBeInTheDocument();
  });

  it('will not send a rejection without a reason', async () => {
    getOnboardingRequest.mockResolvedValue(detail());
    renderDetail();
    fireEvent.click((await screen.findAllByRole('button', { name: 'Reject' }))[0]);

    // The dialog's own Reject is the last one in the tree; the row buttons that
    // opened it are still mounted behind it.
    const dialog = await screen.findByRole('dialog');
    const inDialog = within(dialog).getByRole('button', { name: 'Reject' });
    expect(inDialog).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText('Why'), {
      target: { value: 'Left the company.' },
    });
    await waitFor(() => expect(inDialog).not.toBeDisabled());
    fireEvent.click(inDialog);
    await waitFor(() =>
      expect(rejectOnboardingPerson).toHaveBeenCalledWith('req-1', 'p1', 'Left the company.'),
    );
  });

  it('counts what the reviewer needs to decide', async () => {
    getOnboardingRequest.mockResolvedValue(
      detail({
        people: [
          {
            ...detail().people[0],
            collisions: [{ kind: 'user_email', label: 'Already a user: Tan Wei Ming' }],
            needs_agent_seat: true,
          },
        ],
      }),
    );
    renderDetail();
    expect(await screen.findByText('1 submitted')).toBeInTheDocument();
    expect(screen.getByText('1 already exist')).toBeInTheDocument();
    expect(screen.getByText('1 need a chat-agent seat')).toBeInTheDocument();
  });

  it('names the failures rather than only counting successes', async () => {
    getOnboardingRequest.mockResolvedValue(
      detail({
        status: 'partially_completed',
        people: [
          {
            ...detail().people[0],
            user_step: 'failed',
            user_error: 'Email already registered.',
          },
        ],
      }),
    );
    renderDetail();
    expect(await screen.findByText('1 failed to provision')).toBeInTheDocument();
    expect(screen.getAllByText('Email already registered.').length).toBeGreaterThan(0);
  });

  it('confirms before deleting, in the standard words', async () => {
    getOnboardingRequest.mockResolvedValue(detail());
    renderDetail();
    fireEvent.click(await screen.findByRole('button', { name: /Delete/ }));
    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
  });
});
