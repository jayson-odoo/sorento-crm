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

// Container pulls SettingsProvider context this unit test does not need.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const routerPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
  usePathname: () => '/user-management/onboarding-requests/req-1',
  useSearchParams: () => new URLSearchParams(),
}));

// The pager reads a backend `/neighbours` endpoint; nothing answers it here.
vi.mock('@/hooks/useRecordNeighbours', () => ({
  useRecordNeighbours: () => ({
    prevId: null,
    nextId: null,
    index: 1,
    total: 1,
    isLoading: false,
  }),
}));

const copyToClipboard = vi.fn();
vi.mock('@/hooks/use-copy-to-clipboard', () => ({
  useCopyToClipboard: ({ onCopy }: { onCopy?: () => void } = {}) => ({
    isCopied: false,
    copyToClipboard: (value: string) => {
      copyToClipboard(value);
      onCopy?.();
    },
  }),
}));

const getOnboardingRequest = vi.fn();
const rejectOnboardingPerson = vi.fn();
const approveOnboardingRequest = vi.fn();
const approveOnboardingPerson = vi.fn();
const startOnboardingReview = vi.fn();
const updateOnboardingPerson = vi.fn();
const deleteOnboardingRequest = vi.fn();
const revokeOnboardingRequest = vi.fn();
const regenerateOnboardingToken = vi.fn();
const sendOnboardingRequest = vi.fn();

vi.mock('../../services/onboardingService', () => ({
  ONBOARDING_NEIGHBOURS_PATH: '/api/user-management/onboarding/requests/neighbours',
  getOnboardingRequest: (...a: unknown[]) => getOnboardingRequest(...a),
  listOnboardingRequests: vi.fn(),
  createOnboardingRequest: vi.fn(),
  rejectOnboardingPerson: (...a: unknown[]) => rejectOnboardingPerson(...a),
  approveOnboardingRequest: (...a: unknown[]) => approveOnboardingRequest(...a),
  approveOnboardingPerson: (...a: unknown[]) => approveOnboardingPerson(...a),
  startOnboardingReview: (...a: unknown[]) => startOnboardingReview(...a),
  updateOnboardingPerson: (...a: unknown[]) => updateOnboardingPerson(...a),
  deleteOnboardingRequest: (...a: unknown[]) => deleteOnboardingRequest(...a),
  revokeOnboardingRequest: (...a: unknown[]) => revokeOnboardingRequest(...a),
  regenerateOnboardingToken: (...a: unknown[]) => regenerateOnboardingToken(...a),
  sendOnboardingRequest: (...a: unknown[]) => sendOnboardingRequest(...a),
}));

/**
 * Record actions live behind the gear menu, so open it before clicking one.
 * Radix opens on pointerdown, which jsdom does not synthesize from a click, so
 * drive it by keyboard instead (ArrowDown opens and focuses the first item).
 */
async function openGearMenu() {
  const trigger = await screen.findByRole('button', { name: /Request actions/i });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
  return screen.findByRole('menu');
}

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
    intake_url: 'https://crm.example.com/onboarding/TOKEN',
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
    expect(await screen.findByText('Notes')).toBeInTheDocument();
    expect(screen.getByText('No notes.')).toBeInTheDocument();
    // "People" and "Provisioning" also name grid columns, so assert the section
    // headings exist rather than that the words appear exactly once.
    expect(screen.getAllByText('People').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Provisioning').length).toBeGreaterThan(0);
    expect(screen.getByText('Nothing provisioned yet.')).toBeInTheDocument();
    expect(screen.getByText('Intake link')).toBeInTheDocument();
  });

  it('shows the link is live without ever printing the tokenised URL', async () => {
    getOnboardingRequest.mockResolvedValue(detail({ status: 'sent' }));
    const { container } = renderDetail();
    expect(await screen.findByText('Link active')).toBeInTheDocument();
    // A tokenised URL on screen is a credential on screen: it is copied from
    // the gear menu, never rendered.
    expect(container.textContent).not.toContain('onboarding/TOKEN');
  });

  it('says when the link was revoked instead of offering it', async () => {
    getOnboardingRequest.mockResolvedValue(
      detail({ status: 'sent', revoked_at: '2026-08-15T09:00:00' }),
    );
    renderDetail();
    expect(await screen.findByText(/^Revoked on /)).toBeInTheDocument();
    expect(screen.queryByText('Link active')).not.toBeInTheDocument();
  });

  it('says so when no link could be built at all', async () => {
    getOnboardingRequest.mockResolvedValue(detail({ status: 'sent', intake_url: null }));
    renderDetail();
    expect(await screen.findByText('No intake link available.')).toBeInTheDocument();
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

    fireEvent.change(within(dialog).getByLabelText('Reason'), {
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
    expect(await screen.findByText('Submitted 1')).toBeInTheDocument();
    expect(screen.getByText('Existing 1')).toBeInTheDocument();
    expect(screen.getByText('Agent seats 1')).toBeInTheDocument();
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
    expect(await screen.findByText('Failed 1')).toBeInTheDocument();
    expect(screen.getAllByText('Email already registered.').length).toBeGreaterThan(0);
  });

  it('puts the record actions behind the gear, not in a flat button row', async () => {
    getOnboardingRequest.mockResolvedValue(detail({ status: 'sent' }));
    renderDetail();
    const menu = await openGearMenu();
    for (const label of ['Copy link', 'Revoke link', 'Issue a new link', 'Delete']) {
      expect(within(menu).getByRole('menuitem', { name: label })).toBeInTheDocument();
    }
  });

  it('copies the link from the gear rather than showing it', async () => {
    getOnboardingRequest.mockResolvedValue(detail({ status: 'sent' }));
    renderDetail();
    const menu = await openGearMenu();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Copy link' }));
    expect(copyToClipboard).toHaveBeenCalledWith('https://crm.example.com/onboarding/TOKEN');
  });

  it('confirms before deleting, in the standard words', async () => {
    getOnboardingRequest.mockResolvedValue(detail());
    renderDetail();
    const menu = await openGearMenu();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }));
    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
    expect(deleteOnboardingRequest).not.toHaveBeenCalled();
  });

  it('carries the reviewer back to the queue', async () => {
    getOnboardingRequest.mockResolvedValue(detail());
    renderDetail();
    expect(
      await screen.findByRole('link', { name: /Back to onboarding requests/ }),
    ).toHaveAttribute('href', '/user-management/onboarding-requests');
  });
});
