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
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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

// The real modal pulls in embla-carousel, which needs layout APIs jsdom
// lacks. A thin stand-in that surfaces the `items` prop is enough to prove
// what the card WIRED into it (AC-S1-6): attachment_id on downloadUrl,
// link_id as the item id.
const previewPropsSpy = vi.fn();
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: (props: {
    open: boolean;
    items: { id: string; name: string; downloadUrl?: string }[];
  }) => {
    previewPropsSpy(props);
    return null;
  },
}));

vi.mock('../../services/priceTagRequestService', () => ({
  getPriceTagRequest: vi.fn(),
  getTagSheetDoc: vi.fn(),
  claimPriceTagRequest: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
  listPriceTagRequests: vi.fn(),
}));

import {
  getPriceTagRequest,
  getTagSheetDoc,
  listPriceTagRequests,
  type PriceTagRequestDetail as PriceTagRequestDetailType,
  type PriceTagRequestLine,
} from '../../services/priceTagRequestService';
import PriceTagRequestDetail from './PriceTagRequestDetail';
import { priceTagActions } from './priceTagRequestActions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

const mockGet = vi.mocked(getPriceTagRequest);
const mockList = vi.mocked(listPriceTagRequests);
const mockGetDoc = vi.mocked(getTagSheetDoc);

/** Radix activates a tab on mousedown, which jsdom does not synthesize from a click. */
function switchTab(name: string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

/**
 * The page-scoped pager reads its list page through React Query (S3-03), so the
 * record has to be mounted inside a provider or `useListPager` throws before
 * anything on the page renders.
 */
function renderDetail(requestId = 'req-1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PriceTagRequestDetail requestId={requestId} />
    </QueryClientProvider>,
  );
}

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

function lineWith(overrides: Partial<PriceTagRequestLine> = {}): PriceTagRequestLine {
  return {
    id: 'line-1',
    line_type: 'product',
    product_id: 'prod-1',
    product_set_id: null,
    name: 'Kitchen Sink',
    code: 'SRT-1',
    show_promo_price: false,
    quantity: 1,
    alternatives: [],
    included_accessories: null,
    sort_order: 0,
    marketing_price_override: null,
    marketing_override_reason: null,
    list_price: 100,
    sell_price: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  // The page the pager walks: this record plus one neighbour, so the chevrons
  // have something to be enabled about.
  mockList.mockResolvedValue({
    data: [{ id: 'req-1' }, { id: 'req-2' }] as never,
    pagination: { total: 2, page: 1, limit: 50 },
  });
  // No design yet unless a test says otherwise.
  mockGetDoc.mockResolvedValue(null);
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
    renderDetail();

    expect(
      await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 }),
    ).toBeTruthy();
    expect(screen.getByText('Designing')).toBeTruthy();
    expect(screen.getByText(/Assigned to: Marketing Mei/)).toBeTruthy();
  });

  it('renders exactly one primary CTA and puts the rest in the gear', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();

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
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    expect(screen.queryByTestId('price-tag-primary-cta')).toBeNull();
    expect(screen.queryByTestId('gear-menu')).toBeNull();
  });

  it('the primary CTA on a designing request opens the designer', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();

    fireEvent.click(await screen.findByTestId('price-tag-primary-cta'));
    expect(push).toHaveBeenCalledWith('/dealer-kit/price-tag-requests/req-1/design');
  });

  it('carries prev/next record navigation', async () => {
    mockGet.mockResolvedValue(requestWith());
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    expect(screen.getByRole('button', { name: 'Previous price tag request' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Next price tag request' })).toBeTruthy();
  });

  it('carries the house Back, and no ad-hoc one beside it', async () => {
    mockGet.mockResolvedValue(requestWith());
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    // The one way out, `BackToList`, which carries the list query the row click
    // wrote. Anything else in this slot is the ad-hoc button S3 removed.
    expect(
      screen.getByRole('link', { name: 'Back to price tag requests' }),
    ).toBeTruthy();
    expect(screen.queryByText('Back to list')).toBeNull();
  });

  it('gives every section an empty state rather than hiding it', async () => {
    mockGet.mockResolvedValue(requestWith({ notes: null, lines: [], attachments: [] }));
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    // Request tab is open by default.
    expect(screen.getByText('The salesperson left no notes.')).toBeTruthy();

    switchTab('Lines');
    expect(await screen.findByText('No lines in this request.')).toBeTruthy();

    switchTab('PO Attachments');
    expect(await screen.findByText('No PO attachments uploaded.')).toBeTruthy();

    switchTab('Proof');
    expect(await screen.findByText(/Mark the proof ready to send it/)).toBeTruthy();
  });

  it('asks before voiding rather than voiding on the click', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();

    await screen.findByTestId('gear-menu');
    const gear = within(screen.getByTestId('gear-menu'));
    fireEvent.click(gear.getByRole('menuitem', { name: /Void/ }));

    await waitFor(() => {
      expect(screen.getByText('Void this request?')).toBeTruthy();
    });
  });

  // AC-S1-6: the response's attachments carry `entity_attachment_service
  // .list_attachments_for_entity`'s shape (link_id/attachment_id/filename/
  // size/url/content_type/uploaded_at/...), NOT the old ad-hoc {id, created_at}
  // one - a drift the type checker could not catch because the field was
  // typed `list[dict]` on the wire. Wrong keys read as "download does
  // nothing, date is blank", not a crash, so this has to be asserted.
  it('reads the real attachment shape: attachment_id on the download url, uploaded_at for the date', async () => {
    const uploadedAt = '2026-08-30T03:15:00Z';
    mockGet.mockResolvedValue(
      requestWith({
        attachments: [
          {
            link_id: 'link-1',
            attachment_id: 'att-1',
            filename: 'ZZT-po.pdf',
            size: 2048,
            url: 'https://cdn.test/zzt-po.pdf',
            content_type: 'application/pdf',
            uploaded_at: uploadedAt,
            uploader_kind: 'contact',
            uploaded_by_name: 'Sales Sam',
            uploaded_by_role: 'contact',
            can_unlink: true,
          },
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('PO Attachments');

    expect(await screen.findByText('ZZT-po.pdf')).toBeInTheDocument();
    expect(
      screen.getByText(formatDateTimeInMalaysia(uploadedAt)),
    ).toBeInTheDocument();

    expect(previewPropsSpy).toHaveBeenCalled();
    const items = previewPropsSpy.mock.calls.at(-1)?.[0].items;
    expect(items).toEqual([
      expect.objectContaining({
        id: 'link-1',
        downloadUrl: expect.stringContaining('att-1'),
      }),
    ]);
  });
});

// ---------------------------------------------------------------------------
// Tabs (D25, AC-S10-1..3): Request / Lines / PO Attachments / Proof replace
// the four stacked cards; the standalone Proof card and its duplicate "Open
// the designer" button are gone; the Lines tab carries a per-row Design
// action and a per-line tag status.
// ---------------------------------------------------------------------------

describe('PriceTagRequestDetail - tabs', () => {
  it('renders the tabs in order: Request, Lines, PO Attachments, Proof', async () => {
    mockGet.mockResolvedValue(requestWith());
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabLabels).toEqual(['Request', 'Lines', 'PO Attachments', 'Proof']);
  });

  it('has no standalone Proof card outside the Proof tab, and no duplicate Open the designer button', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();

    // Request tab is open by default - the old standalone Proof card lived
    // alongside it as a fourth stacked card, so its heading must not appear
    // here any more.
    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    expect(screen.queryByRole('heading', { name: 'Proof' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Open the designer' })).toBeNull();

    switchTab('Proof');
    expect(await screen.findByRole('heading', { name: 'Proof' })).toBeTruthy();
    // The action moved into the header (the primary CTA), so the tab body
    // never grows its own copy of it back.
    expect(screen.queryByRole('button', { name: 'Open the designer' })).toBeNull();
  });

  it('keeps exactly one Design entry point in the header for a claimed, designable request', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();

    const primary = await screen.findByTestId('price-tag-primary-cta');
    expect(primary.textContent).toContain('Design tags');
  });

  it("a line's Design action opens the designer with THAT line preselected", async () => {
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          lineWith({ id: 'line-1', code: 'SRT-1' }),
          lineWith({ id: 'line-2', code: 'SRT-2', name: 'Bath Tub' }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    fireEvent.click(await screen.findByRole('button', { name: 'Design SRT-2' }));
    expect(push).toHaveBeenCalledWith(
      '/dealer-kit/price-tag-requests/req-1/design?line=line-2',
    );
  });

  it("shows each line's tag status: Designed once a tag exists for it, No tag otherwise", async () => {
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          lineWith({ id: 'line-1', code: 'SRT-1' }),
          lineWith({ id: 'line-2', code: 'SRT-2', name: 'Bath Tub' }),
        ],
      }),
    );
    mockGetDoc.mockResolvedValue({
      kind: 'tag_sheet',
      imposition: {
        preset: 'a4_3up',
        page_width_mm: 210,
        page_height_mm: 297,
        bleed_mm: 3,
        gap_mm: 2,
      },
      sheets: [
        {
          id: 'sheet-1',
          tags: [
            {
              id: 'tag-1',
              template_id: 'tmpl-1',
              request_line_id: 'line-1',
              x_mm: 0,
              y_mm: 0,
              width_mm: 85,
              height_mm: 58,
              layers: [],
            },
          ],
        },
      ],
    });
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    const line1Row = (await screen.findByText('SRT-1')).closest('tr');
    const line2Row = screen.getByText('SRT-2').closest('tr');
    expect(line1Row).not.toBeNull();
    expect(line2Row).not.toBeNull();
    expect(within(line1Row as HTMLElement).getByText('Designed')).toBeTruthy();
    expect(within(line2Row as HTMLElement).getByText('No tag')).toBeTruthy();
  });

  // Review: the row Design action was ungated - it rendered on every line
  // regardless of status, while the header CTA (and the deleted Proof-card
  // button) only ever offered Design when `priceTagActions` legalizes it.
  // The row must use the exact same predicate.
  it('hides the Actions column entirely on a request Design is not legal for', async () => {
    mockGet.mockResolvedValue(
      requestWith({ status: 'approved', lines: [lineWith({ id: 'line-1', code: 'SRT-1' })] }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    await screen.findByText('SRT-1');
    expect(screen.queryByRole('columnheader', { name: 'Actions' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Design /i })).toBeNull();
  });

  it('shows the row Design action on a claimed, designing request', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        status: 'designing',
        assigned_to_id: 'user-1',
        lines: [lineWith({ id: 'line-1', code: 'SRT-1' })],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    expect(await screen.findByRole('button', { name: 'Design SRT-1' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeTruthy();
  });
});
