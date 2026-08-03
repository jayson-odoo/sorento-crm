/**
 * The Edition detail screen's action contract.
 *
 * The rule this slice was built to, and the reason these assertions exist:
 * ONE primary action, chosen by status, with Reject as its outline-destructive
 * counterpart and everything else behind the gear. The Dealer Kit page editor
 * reached six equal-weight header buttons before anybody noticed; a screen with
 * five states can get there faster, one state at a time.
 *
 * Actions that cannot apply are HIDDEN rather than disabled - a disabled
 * Approve on a draft invites somebody to hunt for what would enable it.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/editions/ed-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ editionId: 'ed-1' }),
}));

// Radix only mounts a menu behind a real pointer, which jsdom does not provide.
// Stubbed so placement - header versus gear - is assertable.
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({
    children,
    ariaLabel,
  }: {
    children: React.ReactNode;
    ariaLabel?: string;
  }) => (
    <div data-testid="gear-menu" aria-label={ariaLabel}>
      {children}
    </div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children }: { children: React.ReactNode }) => (
    <div role="menuitem">{children}</div>
  ),
}));

vi.mock('../../../services/editionService', () => ({
  getEdition: vi.fn(),
  getEditionReview: vi.fn(),
  listEditions: vi.fn(),
  createEdition: vi.fn(),
  submitEdition: vi.fn(),
  approveEdition: vi.fn(),
  rejectEdition: vi.fn(),
  reopenEdition: vi.fn(),
  publishEdition: vi.fn(),
}));

import {
  approveEdition,
  getEdition,
  getEditionReview,
  publishEdition,
  rejectEdition,
  submitEdition,
  type Edition,
  type EditionStatus,
} from '../../../services/editionService';
import { EditionDetail } from './EditionDetail';

const mockGet = vi.mocked(getEdition);
const mockReview = vi.mocked(getEditionReview);
const mockSubmit = vi.mocked(submitEdition);
const mockApprove = vi.mocked(approveEdition);
const mockReject = vi.mocked(rejectEdition);
const mockPublish = vi.mocked(publishEdition);

const LABELS: Record<EditionStatus, string> = {
  draft: 'Draft',
  pending_approval: 'Pending approval',
  approved: 'Approved',
  rejected: 'Rejected',
  done: 'Done',
};

function edition(status: EditionStatus, extra: Partial<Edition> = {}): Edition {
  return {
    id: 'ed-1',
    pageId: 'pg-1',
    pageName: 'Sorento Catalogue 2026',
    name: 'Spring 2026',
    status,
    statusLabel: LABELS[status],
    approvedVersionId: null,
    doneVersionId: null,
    previousEditionId: null,
    submittedAt: null,
    approvedAt: null,
    rejectionReason: null,
    createdAt: '2026-08-01T02:00:00',
    ...extra,
  };
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <EditionDetail editionId="ed-1" />
    </QueryClientProvider>,
  );
}

/** Header buttons, excluding anything the gear owns. */
function headerActions(): string[] {
  const gear = screen.getByTestId('gear-menu');
  return Array.from(document.querySelectorAll('button'))
    .filter((element) => !gear.contains(element))
    .map((element) => element.textContent?.trim() ?? '')
    .filter(Boolean);
}

const EMPTY_REVIEW = { members: [], dropped: [], previousEditionName: null };

beforeEach(() => {
  vi.clearAllMocks();
  mockReview.mockResolvedValue(EMPTY_REVIEW);
});

describe('EditionDetail, one decision at a time', () => {
  it.each([
    ['draft', ['Send for approval']],
    ['approved', ['Publish']],
    ['rejected', ['Reopen for editing']],
    ['done', []],
  ] as const)('offers only what %s allows', async (status, expected) => {
    mockGet.mockResolvedValue(edition(status));

    renderDetail();
    await screen.findByText('Spring 2026');

    expect(headerActions()).toEqual(expected);
  });

  it('pairs Approve with Reject while it waits on a decision', async () => {
    // The two halves of ONE decision, so they sit together. Reject is outline
    // destructive rather than a second primary.
    mockGet.mockResolvedValue(edition('pending_approval'));

    renderDetail();
    await screen.findByText('Spring 2026');

    expect(headerActions()).toEqual(['Approve', 'Reject']);
    const reject = screen.getByRole('button', { name: /reject/i });
    expect(reject.className).toMatch(/destructive/);
  });

  it('never disables an action that cannot apply - it omits it', async () => {
    mockGet.mockResolvedValue(edition('draft'));

    renderDetail();
    await screen.findByText('Spring 2026');

    expect(screen.queryByRole('button', { name: /approve/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /publish/i })).toBeNull();
  });

  it('keeps the catalogue link under the gear rather than in the header', async () => {
    mockGet.mockResolvedValue(edition('draft'));

    renderDetail();
    await screen.findByText('Spring 2026');

    const gear = within(screen.getByTestId('gear-menu'));
    expect(gear.getByRole('menuitem', { name: /open the catalogue/i })).toBeInTheDocument();
  });
});

describe('EditionDetail, what it tells the designer', () => {
  it('leads with the rejection reason', async () => {
    // The one thing somebody coming back to rejected work needs to read, so it
    // is on the page rather than a field in a grid.
    mockGet.mockResolvedValue(
      edition('rejected', { rejectionReason: 'Bathtub prices are last season.' }),
    );

    renderDetail();

    expect(await screen.findByTestId('dk-ed-rejection')).toHaveTextContent(
      'Bathtub prices are last season.',
    );
  });

  it('shows no rejection banner when there is nothing to say', async () => {
    mockGet.mockResolvedValue(edition('draft'));

    renderDetail();
    await screen.findByText('Spring 2026');

    expect(screen.queryByTestId('dk-ed-rejection')).toBeNull();
  });

  it('renders the history section even when nothing has happened yet', async () => {
    // Per the CRUD standard: a section that vanishes on missing data reads as
    // a section that failed to load.
    mockGet.mockResolvedValue(edition('draft'));

    renderDetail();
    await screen.findByText('Spring 2026');

    expect(screen.getByText('Sent for approval')).toBeInTheDocument();
    expect(screen.getAllByText('Not yet').length).toBe(2);
  });

  it('prints no uuid anywhere', async () => {
    mockGet.mockResolvedValue(edition('approved', { approvedVersionId: 'v-1' }));

    renderDetail();
    await screen.findByText('Spring 2026');

    expect(document.body.textContent ?? '').not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    );
  });
});

describe('EditionDetail, rejecting', () => {
  it('will not send back without a reason', async () => {
    mockGet.mockResolvedValue(edition('pending_approval'));

    renderDetail();
    await screen.findByText('Spring 2026');
    fireEvent.click(screen.getByRole('button', { name: /reject/i }));

    const send = await screen.findByRole('button', { name: /send back/i });
    expect(send).toBeDisabled();
    expect(mockReject).not.toHaveBeenCalled();
  });

  it('sends the trimmed reason', async () => {
    mockGet.mockResolvedValue(edition('pending_approval'));
    mockReject.mockResolvedValue(edition('rejected', { rejectionReason: 'Fix the prices' }));

    renderDetail();
    await screen.findByText('Spring 2026');
    fireEvent.click(screen.getByRole('button', { name: /reject/i }));

    fireEvent.change(await screen.findByPlaceholderText(/what needs to change/i), {
      target: { value: '  Fix the prices  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send back/i }));

    await waitFor(() => expect(mockReject).toHaveBeenCalledWith('ed-1', 'Fix the prices'));
  });
});

describe('EditionDetail, the transitions fire', () => {
  it('submits from draft', async () => {
    mockGet.mockResolvedValue(edition('draft'));
    mockSubmit.mockResolvedValue(edition('pending_approval'));

    renderDetail();
    await screen.findByText('Spring 2026');
    fireEvent.click(screen.getByRole('button', { name: /send for approval/i }));

    await waitFor(() => expect(mockSubmit).toHaveBeenCalledWith('ed-1'));
  });

  it('approves without publishing', async () => {
    // AC-L7. Approving records that somebody read it; publishing is what
    // readers see, and it is a separate click by a separate right.
    mockGet.mockResolvedValue(edition('pending_approval'));
    mockApprove.mockResolvedValue(edition('approved'));

    renderDetail();
    await screen.findByText('Spring 2026');
    fireEvent.click(screen.getByRole('button', { name: /approve/i }));

    await waitFor(() => expect(mockApprove).toHaveBeenCalledWith('ed-1'));
    expect(mockPublish).not.toHaveBeenCalled();
  });

  it('publishes from approved', async () => {
    mockGet.mockResolvedValue(edition('approved'));
    mockPublish.mockResolvedValue(edition('done'));

    renderDetail();
    await screen.findByText('Spring 2026');
    fireEvent.click(screen.getByRole('button', { name: /publish/i }));

    await waitFor(() => expect(mockPublish).toHaveBeenCalledWith('ed-1'));
  });
});

describe('EditionDetail, what changed since last time', () => {
  it('surfaces a product the resolver silently dropped', async () => {
    // The reason this section exists. resolve_members filters discontinued
    // products out of its candidate set, so the tile does not render struck
    // through - it vanishes and the count quietly falls. This is the only
    // place that says so.
    mockGet.mockResolvedValue(edition('draft'));
    mockReview.mockResolvedValue({
      members: [],
      dropped: [
        {
          productId: 'p-9',
          productCode: 'SRTWC286-SH',
          productName: 'One Piece Water Closet',
          reason: 'discontinued',
        },
      ],
      previousEditionName: 'Autumn 2026',
    });

    renderDetail();

    const dropped = await screen.findByTestId('dk-ed-dropped');
    expect(dropped).toHaveTextContent('SRTWC286-SH');
    expect(dropped).toHaveTextContent(/discontinued/i);
    expect(screen.getByText(/what changed since autumn 2026/i)).toBeInTheDocument();
  });

  it('names a deleted product as deleted rather than hiding it', async () => {
    mockGet.mockResolvedValue(edition('draft'));
    mockReview.mockResolvedValue({
      members: [],
      dropped: [
        { productId: 'p-gone', productCode: null, productName: null, reason: 'missing' },
      ],
      previousEditionName: null,
    });

    renderDetail();

    const dropped = await screen.findByTestId('dk-ed-dropped');
    expect(dropped).toHaveTextContent(/unknown product/i);
    expect(dropped).toHaveTextContent(/deleted/i);
  });

  it('badges what walked into the catalogue on its own', async () => {
    mockGet.mockResolvedValue(edition('draft'));
    mockReview.mockResolvedValue({
      members: [
        {
          productId: 'p-1',
          productCode: 'SRTNEW1',
          productName: 'New Basin',
          stockOnHand: 12,
          isNewSincePrevious: true,
        },
        {
          productId: 'p-2',
          productCode: 'SRTOLD1',
          productName: 'Old Basin',
          stockOnHand: 3,
          isNewSincePrevious: false,
        },
      ],
      dropped: [],
      previousEditionName: 'Autumn 2026',
    });

    renderDetail();

    const fresh = await screen.findByTestId('dk-ed-new-since');
    expect(fresh).toHaveTextContent('SRTNEW1');
    expect(fresh).toHaveTextContent('12 in stock');
    // The unchanged product is counted, not listed - the list is what to look at.
    expect(fresh).not.toHaveTextContent('SRTOLD1');
  });

  it('still renders when nothing changed, because that is the answer', async () => {
    mockGet.mockResolvedValue(edition('draft'));

    renderDetail();

    const counts = await screen.findByTestId('dk-ed-change-counts');
    expect(counts).toHaveTextContent(/no longer available/i);
    expect(screen.queryByTestId('dk-ed-dropped')).toBeNull();
  });
});
