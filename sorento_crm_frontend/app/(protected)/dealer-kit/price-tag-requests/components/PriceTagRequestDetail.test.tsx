/**
 * The CRM request detail page's chrome (D50, D52).
 *
 * What is pinned here is the part the captain asked for and the part that is
 * easiest to undo by accident: there is exactly ONE primary CTA, it is the next
 * lifecycle action for the status, and everything else that is legal is in the
 * gear menu rather than beside it. The action table itself is asserted directly
 * so every status is covered without mounting eight pages.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1',
  useSearchParams: () => new URLSearchParams(),
}));

// Radix only mounts a menu behind a real pointer, which jsdom does not provide.
// Stubbed so placement - header versus gear - is assertable. Same idiom as
// EditionDetail.test.tsx.
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
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode;
    onSelect?: (event: { preventDefault: () => void }) => void;
  }) => (
    <div role="menuitem" onClick={() => onSelect?.({ preventDefault: () => {} })}>
      {children}
    </div>
  ),
}));

vi.mock('../../services/priceTagRequestService', () => ({
  getPriceTagRequest: vi.fn(),
  claimPriceTagRequest: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
  listPriceTagRequests: vi.fn(),
}));

import {
  getPriceTagRequest,
  listPriceTagRequests,
  type PriceTagRequestDetail as PriceTagRequestDetailType,
} from '../../services/priceTagRequestService';
import PriceTagRequestDetail from './PriceTagRequestDetail';
import { priceTagActions } from './priceTagRequestActions';

const mockGet = vi.mocked(getPriceTagRequest);
const mockList = vi.mocked(listPriceTagRequests);

function requestWith(
  overrides: Partial<PriceTagRequestDetailType> = {},
): PriceTagRequestDetailType {
  return {
    id: 'req-1',
    doc_number: 'PT-202608-0001',
    debtor_code: 'ARD001',
    debtor_name: 'ARDENCY CONSTRUCTION',
    promotion_id: null,
    promotion_name: null,
    needed_by_date: '2026-09-05',
    notes: null,
    status: 'designing',
    line_count: 1,
    created_at: '2026-08-30T02:00:00Z',
    assigned_to_id: 'user-1',
    assigned_to_name: 'Marketing Mei',
    contact_name: 'Sales Sam',
    contact_id: 'contact-1',
    lines: [],
    attachments: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockList.mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1, limit: 500 },
  });
});

// ---------------------------------------------------------------------------
// The action table (D52)
// ---------------------------------------------------------------------------

describe('priceTagActions', () => {
  it.each([
    ['new', null, 'Claim'],
    ['new', 'user-1', 'Design tags'],
    ['designing', 'user-1', 'Design tags'],
    ['changes_requested', 'user-1', 'Design tags'],
    ['proof_ready', 'user-1', 'View design'],
    ['approved', 'user-1', 'Export PDF'],
    ['ready', 'user-1', 'Export PDF'],
  ])('%s is led by %s', (status, assignee, label) => {
    expect(priceTagActions(status, assignee)[0].label).toBe(label);
  });

  it.each(['rejected', 'void'])('%s offers nothing at all', (status) => {
    expect(priceTagActions(status, 'user-1')).toEqual([]);
  });

  it('does not offer Design before the request is claimed', () => {
    const labels = priceTagActions('new', null).map((a) => a.label);
    expect(labels).not.toContain('Design tags');
  });

  it('marks Void destructive so it has to be confirmed', () => {
    const voidAction = priceTagActions('designing', 'user-1').find(
      (a) => a.action === 'void',
    );
    expect(voidAction?.destructive).toBe(true);
  });

  it('never offers Void once the sheet has been exported', () => {
    expect(priceTagActions('ready', 'user-1').map((a) => a.action)).toEqual(['export']);
  });
});

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------

describe('PriceTagRequestDetail', () => {
  it('shows the document number, the status pill and the record metadata in the header', async () => {
    mockGet.mockResolvedValue(requestWith());
    render(<PriceTagRequestDetail requestId="req-1" />);

    expect(
      await screen.findByRole('heading', { name: /PT-202608-0001/ }),
    ).toBeTruthy();
    expect(screen.getByText('Designing')).toBeTruthy();
    expect(screen.getByText(/Assigned to: Marketing Mei/)).toBeTruthy();
  });

  it('renders exactly one primary CTA and puts the rest in the gear', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    render(<PriceTagRequestDetail requestId="req-1" />);

    const primary = await screen.findByTestId('price-tag-primary-cta');
    expect(primary.textContent).toContain('Design tags');
    // The secondary actions are NOT beside it.
    expect(screen.queryByRole('button', { name: 'Mark proof ready' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Void' })).toBeNull();

    const gear = within(screen.getByTestId('gear-menu'));
    expect(gear.getByRole('menuitem', { name: /Mark proof ready/ })).toBeTruthy();
    expect(gear.getByRole('menuitem', { name: /Void/ })).toBeTruthy();
  });

  it('has no gear at all when nothing is legal', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'void' }));
    render(<PriceTagRequestDetail requestId="req-1" />);

    await screen.findByRole('heading', { name: /PT-202608-0001/ });
    expect(screen.queryByTestId('price-tag-primary-cta')).toBeNull();
    expect(screen.queryByTestId('gear-menu')).toBeNull();
  });

  it('the primary CTA on a designing request opens the designer', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    render(<PriceTagRequestDetail requestId="req-1" />);

    fireEvent.click(await screen.findByTestId('price-tag-primary-cta'));
    expect(push).toHaveBeenCalledWith('/dealer-kit/price-tag-requests/req-1/design');
  });

  it('carries prev/next record navigation', async () => {
    mockGet.mockResolvedValue(requestWith());
    render(<PriceTagRequestDetail requestId="req-1" />);

    await screen.findByRole('heading', { name: /PT-202608-0001/ });
    expect(screen.getByRole('button', { name: 'Previous price tag request' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Next price tag request' })).toBeTruthy();
  });

  it('has no ad-hoc back button: the breadcrumb is the way back', async () => {
    mockGet.mockResolvedValue(requestWith());
    render(<PriceTagRequestDetail requestId="req-1" />);

    await screen.findByRole('heading', { name: /PT-202608-0001/ });
    expect(screen.queryByText('Back to list')).toBeNull();
  });

  it('gives every section an empty state rather than hiding it', async () => {
    mockGet.mockResolvedValue(requestWith({ notes: null, lines: [], attachments: [] }));
    render(<PriceTagRequestDetail requestId="req-1" />);

    await screen.findByRole('heading', { name: /PT-202608-0001/ });
    expect(screen.getByText('No lines in this request.')).toBeTruthy();
    expect(screen.getByText('No PO attachments uploaded.')).toBeTruthy();
    expect(screen.getByText('The salesperson left no notes.')).toBeTruthy();
    expect(screen.getByText(/Mark the proof ready to send it/)).toBeTruthy();
  });

  it('asks before voiding rather than voiding on the click', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    render(<PriceTagRequestDetail requestId="req-1" />);

    await screen.findByTestId('gear-menu');
    const gear = within(screen.getByTestId('gear-menu'));
    fireEvent.click(gear.getByRole('menuitem', { name: /Void/ }));

    await waitFor(() => {
      expect(screen.getByText('Void this request?')).toBeTruthy();
    });
  });
});
