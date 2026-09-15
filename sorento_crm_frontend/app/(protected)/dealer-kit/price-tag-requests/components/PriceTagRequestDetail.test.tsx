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
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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

/**
 * Void is a server-deferred pending action since r9 (D7 / Apple Alignment S6):
 * no dialog asks first, the button becomes a countdown with a Cancel, and the
 * server commits when the window lapses even if the tab is closed.
 *
 * The engine - parking the action, running the clock, committing - is
 * `hooks/useDeferredAction.test.tsx`'s job. What belongs HERE is the wiring:
 * the right action key and entity, that the gear item starts it rather than
 * opening anything, and that the countdown reaches the record card. Mocking
 * the hook also means no test in this file owns a real timer, so none can let
 * a countdown lapse.
 */
const voidStart = vi.fn();
const voidCancel = vi.fn();
const useDeferredActionInput = vi.fn();
let voidIsPending = false;
let voidCountdown: React.ReactNode = null;
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: unknown) => {
    useDeferredActionInput(input);
    return {
      pending: voidIsPending ? { id: 'pending-1' } : null,
      isPending: voidIsPending,
      isBlocked: false,
      start: voidStart,
      cancel: voidCancel,
      countdown: voidCountdown,
    };
  },
}));

vi.mock('../../services/priceTagRequestService', () => ({
  getPriceTagRequest: vi.fn(),
  getTagSheetDoc: vi.fn(),
  claimPriceTagRequest: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
  listPriceTagRequests: vi.fn(),
  // r9 S1/D3: the Request tab now opens with `RequestDesignSection`, which
  // asks for the payload on mount. Resolving to null is the "no design yet"
  // answer, which is what every fixture in this file is.
  getRequestDesignPayload: vi.fn(async () => null),
}));

import {
  getPriceTagRequest,
  getTagSheetDoc,
  listPriceTagRequests,
  type PriceTagRequestDetail as PriceTagRequestDetailType,
  type PriceTagRequestLine,
  type PriceTagRequestLinePart,
  type PriceTagRequestTag,
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

/**
 * The rail/table label for a line's default tag.
 *
 * The product builds "1a"/"1b" from the line's position plus a letter; a
 * fixture only needs two lines' tag rows to be separately addressable, so the
 * label reuses the line id's own suffix ('line-2' -> '2a').
 */
function tagLabelFor(lineId: string): string {
  return `${lineId.split('-').pop() ?? '1'}a`;
}

/**
 * The one tag a line carries by default (S3, AC-S3-1). Its id IS the line id:
 * submit mints exactly one tag per line, and only a Split gives a line a
 * second one. The override and its reason live HERE now, not on the line.
 */
function tagWith(
  lineId: string,
  overrides: Partial<PriceTagRequestTag> = {},
): PriceTagRequestTag {
  return {
    id: lineId,
    sort_order: 0,
    label: tagLabelFor(lineId),
    quantity: 1,
    choices: {},
    choices_display: [],
    open_groups: [],
    marketing_price_override: null,
    marketing_override_reason: null,
    list_price: 100,
    sell_price: null,
    ...overrides,
  };
}

function lineWith(overrides: Partial<PriceTagRequestLine> = {}): PriceTagRequestLine {
  const merged = {
    id: 'line-1',
    line_type: 'product' as const,
    product_id: 'prod-1' as string | null,
    product_set_id: null as string | null,
    name: 'Kitchen Sink',
    code: 'SRT-1',
    show_promo_price: false,
    quantity: 1,
    included_accessories: null as string | null,
    sort_order: 0,
    list_price: 100 as number | null,
    sell_price: null as number | null,
    parts: [],
    package_warning: null,
    ...overrides,
  };
  return {
    ...merged,
    tags: overrides.tags ?? [tagWith(merged.id, { quantity: merged.quantity })],
  } as PriceTagRequestLine;
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
    // D14 (AC-S10-1, PLAN-price-tag-ai-extract-resolver.md): approved goes
    // back to the designer to print and hand over - Open design leads.
    ['approved', 'user-1', 'Open design'],
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

  it('never offers Void once a self print request is approved and therefore finished', () => {
    // r9 D8 retired `ready`: a self print request ENDS at `approved`, so the
    // only thing left is the design entry point and the export - no void.
    // D14 (PLAN-price-tag-ai-extract-resolver.md) adds `design` leading it;
    // the office half of this matrix, and the `ready`-less status set, live
    // in `priceTagRequestActions.test.ts`.
    expect(priceTagActions('approved', 'user-1', 0, 'self').map((a) => a.action)).toEqual([
      'design',
      'export',
    ]);
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
    expect(screen.queryByRole('button', { name: 'Mark design ready' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Void' })).toBeNull();

    const gear = within(screen.getByTestId('gear-menu'));
    expect(gear.getByRole('menuitem', { name: /Mark design ready/ })).toBeTruthy();
    expect(gear.getByRole('menuitem', { name: /Void/ })).toBeTruthy();
  });

  it('offers "Check product data" from the gear (owner round finding 3)', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();

    await screen.findByTestId('gear-menu');
    const gear = within(screen.getByTestId('gear-menu'));
    expect(gear.getByRole('menuitem', { name: /Check product data/ })).toBeTruthy();
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

    switchTab('Sales Order');
    expect(await screen.findByText('No sales order files attached.')).toBeTruthy();
  });

  it('voids on a countdown rather than asking first', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();

    await screen.findByTestId('gear-menu');
    const gear = within(screen.getByTestId('gear-menu'));
    fireEvent.click(gear.getByRole('menuitem', { name: /Void/ }));

    expect(voidStart).toHaveBeenCalledTimes(1);
    // The retired behaviour, named so it cannot come back: no dialog, and
    // nothing that asks a question before the action runs.
    expect(screen.queryByText('Void this request?')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('parks the void against the right action key and entity', async () => {
    mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
    renderDetail();
    await screen.findByTestId('gear-menu');

    expect(useDeferredActionInput).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'price_tag_request.void',
        entityType: 'price_tag_request',
        entityId: 'req-1',
      }),
    );
  });

  it('shows the countdown and its Cancel on the record card while it runs', async () => {
    voidIsPending = true;
    voidCountdown = (
      <button type="button" data-testid="void-countdown" onClick={voidCancel}>
        Voiding in 10s - Cancel
      </button>
    );
    try {
      mockGet.mockResolvedValue(requestWith({ status: 'designing' }));
      renderDetail();

      const countdown = await screen.findByTestId('void-countdown');
      expect(countdown).toHaveTextContent('Cancel');

      fireEvent.click(countdown);
      expect(voidCancel).toHaveBeenCalledTimes(1);
    } finally {
      voidIsPending = false;
      voidCountdown = null;
    }
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
    switchTab('Sales Order');

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
// Tabs (D25, D10, AC-S1-6, AC-S1-7): Request / Lines / Sales Order replace
// the four stacked cards; the standalone Proof card, the Proof TAB and their
// duplicate "Open the designer" button are gone - the design lives in the
// designer, one click away through the header's own primary CTA. The Lines
// tab carries a per-row Design action and a per-line tag status.
// ---------------------------------------------------------------------------

describe('PriceTagRequestDetail - tabs', () => {
  it('renders the tabs in order: Request, Lines, Sales Order', async () => {
    mockGet.mockResolvedValue(requestWith());
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabLabels).toEqual(['Request', 'Lines', 'Sales Order']);
  });

  it('has no standalone Proof card and no Proof tab at all, at any status (D10)', async () => {
    // AC-S1-6: "No Proof tab at any status" - swept across the statuses that
    // used to carry it (designing had the standalone card; proof_ready and
    // approved are the statuses r7 explicitly calls out for the portal's
    // design preview, so the CRM side is checked at the same three).
    for (const status of ['designing', 'proof_ready', 'approved']) {
      mockGet.mockResolvedValue(requestWith({ status }));
      const { unmount } = renderDetail();

      await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
      expect(screen.queryByRole('tab', { name: 'Proof' })).toBeNull();
      expect(screen.queryByRole('heading', { name: 'Proof' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Open the designer' })).toBeNull();
      const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent);
      expect(tabLabels).toEqual(['Request', 'Lines', 'Sales Order']);

      unmount();
    }
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

    fireEvent.click(
      await screen.findByRole('button', { name: `Design tag ${tagLabelFor('line-2')}` }),
    );
    expect(push).toHaveBeenCalledWith(
      '/dealer-kit/price-tag-requests/req-1/design?tag=line-2',
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
              request_tag_id: 'line-1',
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

    // Designed/No tag is a TAG fact since S3, so it is read off the tag's
    // own row - here the folded line row itself (D7: one tag, no parts),
    // found by the line's code rather than by the ordinal text a folded
    // row no longer renders.
    const tag1Row = (await screen.findByText('SRT-1')).closest('tr');
    const tag2Row = screen.getByText('SRT-2').closest('tr');
    expect(tag1Row).not.toBeNull();
    expect(tag2Row).not.toBeNull();
    expect(within(tag1Row as HTMLElement).getByText('Designed')).toBeTruthy();
    expect(within(tag2Row as HTMLElement).getByText('No tag')).toBeTruthy();
  });

  // Review: the row Design action was ungated - it rendered on every line
  // regardless of status, while the header CTA (and the deleted Proof-card
  // button) only ever offered Design when `priceTagActions` legalizes it.
  // The row must use the exact same predicate. `collected` is the status to
  // prove it with since D14 (PLAN-price-tag-ai-extract-resolver.md): design
  // now leads at `approved` too, so that status no longer demonstrates the
  // gate - `collected` still offers nothing but `export`.
  it('hides the Actions column entirely on a request Design is not legal for', async () => {
    mockGet.mockResolvedValue(
      requestWith({ status: 'collected', lines: [lineWith({ id: 'line-1', code: 'SRT-1' })] }),
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

    expect(
      await screen.findByRole('button', { name: `Design tag ${tagLabelFor('line-1')}` }),
    ).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// S7 - the collection dates are read in Malaysia, off a naive UTC timestamp
// ---------------------------------------------------------------------------

describe('the collection subline (AC-S3-8)', () => {
  /**
   * FastAPI serialises a naive `datetime` with no zone: `2026-09-14T16:30:00`
   * means 16:30 UTC, which is 00:30 on the 15th in Malaysia. The card builds
   * its dates with `new Date(...)` (which reads that string as LOCAL time) and
   * `formatDate` (which reads LOCAL getters), so the day printed is whatever
   * the reader's browser happens to be set to - and on the one boundary that
   * matters it is the wrong day.
   *
   * TZ is pinned so the assertion means the same thing on this machine
   * (Asia/Kuala_Lumpur) and on a CI runner (UTC).
   */
  const originalTz = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = 'UTC';
  });
  afterAll(() => {
    process.env.TZ = originalTz;
  });

  it('reads a naive backend timestamp as UTC and prints the Malaysia date', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        status: 'ready_for_collection',
        print_by: 'office',
        ready_for_collection_at: '2026-09-14T16:30:00',
      } as never),
    );

    renderDetail();

    // 16:30 UTC on the 14th is 00:30 on the 15th in Malaysia.
    expect(await screen.findByText(/Ready since 15\/09\/2026/)).toBeInTheDocument();
  });

  it('dates the auto-collect the same way, seven days on', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        status: 'ready_for_collection',
        print_by: 'office',
        ready_for_collection_at: '2026-09-14T16:30:00',
      } as never),
    );

    renderDetail();

    expect(
      await screen.findByText(/auto-collects 22\/09\/2026/),
    ).toBeInTheDocument();
  });

  it('dates a collected request in Malaysia too', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        status: 'collected',
        print_by: 'office',
        collected_at: '2026-09-14T16:30:00',
      } as never),
    );

    renderDetail();

    expect(await screen.findByText(/Collected 15\/09\/2026/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// AC-S3-2 - the Lines tab nests parts and tags under the line
//
// Marketing opens the request and has to be able to read, in one pass, what the
// salesperson asked for (the line), what came with it (the parts) and what will
// actually print (the tags). Three levels in one table, so what each row IS has
// to be unambiguous - a part row that looked like a tag row would invite
// somebody to design it.
// ---------------------------------------------------------------------------

describe('PriceTagRequestDetail - Lines tab, parts and tags under the line (S3)', () => {
  const MIRROR: PriceTagRequestLinePart = {
    id: 'part-mirror',
    product_id: 'p-mirror',
    code: 'SRTMR502-BL',
    name: 'ZZT Mirror',
    role: null,
    candidates: [],
    sort_order: 0,
  };

  const OPEN_BASIN: PriceTagRequestLinePart = {
    id: 'part-basin',
    product_id: null,
    code: null,
    name: null,
    role: 'Basin',
    candidates: [
      { product_id: 'p-basin-wh', code: 'SRTBS900-WH', name: 'ZZT Basin White' },
      { product_id: 'p-basin-bk', code: 'SRTBS900-BK', name: 'ZZT Basin Black' },
    ],
    sort_order: 1,
  };

  function cabinetLine(overrides: Partial<PriceTagRequestLine> = {}) {
    return lineWith({
      id: 'line-1',
      code: 'SRTBF11834',
      name: 'ZZT Cabinet',
      parts: [MIRROR, OPEN_BASIN],
      ...overrides,
    });
  }

  it('lists each part under its line, a resolved one by code and an open one by group', async () => {
    mockGet.mockResolvedValue(requestWith({ lines: [cabinetLine()] }));
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    expect(await screen.findByText(/SRTMR502-BL/)).toBeInTheDocument();
    // The open group reads as the CHOICE it is, not as two more products in the
    // package.
    expect(
      screen.getByText(/Basin: SRTBS900-WH \/ SRTBS900-BK/),
    ).toBeInTheDocument();
  });

  it('shows the line\'s package warning on the line row, once', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          cabinetLine({
            package_warning: 'Missing: SRTMR502-BL',
            tags: [
              tagWith('line-1'),
              tagWith('line-1', { id: 'tag-1b', label: '1b', sort_order: 1 }),
            ],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    expect(await screen.findByText('Package warning')).toBeInTheDocument();
    expect(screen.getByText('Missing: SRTMR502-BL')).toBeInTheDocument();
    // Two tags, one warning: it is a fact about the ask, not about each print.
    expect(screen.getAllByText('Package warning')).toHaveLength(1);
  });

  it('lists every tag under the line by ordinal, with its resolved choice and price', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          cabinetLine({
            show_promo_price: true,
            tags: [
              tagWith('line-1', {
                choices_display: [{ role: 'Basin', code: 'SRTBS900-WH' }],
                list_price: 1898,
                sell_price: 1599,
              }),
              tagWith('line-1', {
                id: 'tag-1b',
                label: '1b',
                sort_order: 1,
                choices_display: [{ role: 'Basin', code: 'SRTBS900-BK' }],
                list_price: 1948,
                sell_price: 1649,
              }),
            ],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    expect(await screen.findByText('1a')).toBeInTheDocument();
    expect(screen.getByText('1b')).toBeInTheDocument();
    // The choice is shown as a CODE - never the stored product id (AC-X-2).
    expect(screen.getByText('SRTBS900-WH')).toBeInTheDocument();
    expect(screen.getByText('SRTBS900-BK')).toBeInTheDocument();
    expect(screen.queryByText('tag-1b')).toBeNull();
    // Price is a tag fact since D4: the two basins cost different money.
    expect(screen.getByText('RM 1898.00')).toBeInTheDocument();
    expect(screen.getByText('RM 1948.00')).toBeInTheDocument();
    expect(screen.getByText('RM 1599.00')).toBeInTheDocument();
  });

  it('an unresolved tag says which group is open, and how many options it has', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          cabinetLine({
            tags: [
              tagWith('line-1', {
                open_groups: [
                  {
                    role: 'Basin',
                    candidates: [
                      { product_id: 'p-basin-wh', code: 'SRTBS900-WH' },
                      { product_id: 'p-basin-bk', code: 'SRTBS900-BK' },
                    ],
                  },
                ],
              }),
            ],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    expect(await screen.findByText('Open: Basin (2)')).toBeInTheDocument();
  });

  it('the marketing override is shown against the TAG it was set on', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          cabinetLine({
            tags: [
              tagWith('line-1', { list_price: 1898 }),
              tagWith('line-1', {
                id: 'tag-1b',
                label: '1b',
                sort_order: 1,
                list_price: 1948,
                marketing_price_override: 1499,
                marketing_override_reason: 'ZZT roadshow bundle',
              }),
            ],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    const overrides = await screen.findAllByText(/Override: RM\s*1499\.00/);
    // Exactly one: the override belongs to 1b, and showing it on 1a as well
    // would state a price nobody set.
    expect(overrides).toHaveLength(1);
  });

  it('each tag carries its own Design action, pointing at THAT tag', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        status: 'designing',
        assigned_to_id: 'user-1',
        lines: [
          cabinetLine({
            tags: [
              tagWith('line-1'),
              tagWith('line-1', { id: 'tag-1b', label: '1b', sort_order: 1 }),
            ],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    fireEvent.click(await screen.findByRole('button', { name: 'Design tag 1b' }));
    expect(push).toHaveBeenCalledWith(
      '/dealer-kit/price-tag-requests/req-1/design?tag=tag-1b',
    );
  });

  it('a plain product line with no package shows its one tag and no part rows', async () => {
    mockGet.mockResolvedValue(
      requestWith({ lines: [lineWith({ id: 'line-1', code: 'SRT-1' })] }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');

    // D7: one tag, no parts - the line folds to ONE row (no separate "1a"
    // row, so no ordinal text), which by itself proves no part row either.
    expect(await screen.findByText('SRT-1')).toBeInTheDocument();
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1);
    expect(screen.queryByText(tagLabelFor('line-1'))).toBeNull();
    expect(screen.queryByText('Package warning')).toBeNull();
    expect(screen.queryByText(/Open:/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// S3 (D7) - a line with exactly ONE tag and NO parts folds into ONE row.
//
// PLAN-price-tag-ai-extract-resolver.md D7 / price-tag-ai-extract-resolver-
// acceptance-criteria.md S3 (AC-S3-1..S3-4). NOTE this supersedes two
// assertions above in this same file that read a single-tag/no-parts line's
// ordinal as separate, visible text ("shows each line's tag status...",
// "a plain product line with no package shows its one tag..."): both will
// need their `screen.getByText(tagLabelFor(...))` swapped for a scoped
// `within(row)` read once D7 lands, since the ordinal text itself goes away
// on a folded row (the aria-labels on Design/Review do not).
// ---------------------------------------------------------------------------

describe('PriceTagRequestDetail - Lines tab, one row for a single-tag no-parts line (S3)', () => {
  it('AC-S3-1: renders ONE row carrying the tag\'s price, status and actions - no ordinal text', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        status: 'designing',
        assigned_to_id: 'user-1',
        lines: [
          lineWith({
            id: 'line-1',
            code: 'SRT-1',
            name: 'Kitchen Sink',
            show_promo_price: true,
            tags: [tagWith('line-1', { list_price: 300, sell_price: 250 })],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    await screen.findByText('SRT-1');

    const rows = document.querySelectorAll('tbody tr');
    // Today this is TWO rows (the line row, then the "1a" tag row) - D7 folds
    // them into one, which is what this length assertion pins.
    expect(rows).toHaveLength(1);
    const row = rows[0] as HTMLElement;

    expect(within(row).getByText('Product')).toBeInTheDocument();
    expect(within(row).getByText('SRT-1')).toBeInTheDocument();
    expect(within(row).getByText('Kitchen Sink')).toBeInTheDocument();
    expect(within(row).getByText('RM 300.00')).toBeInTheDocument();
    expect(within(row).getByText('RM 250.00')).toBeInTheDocument();
    expect(within(row).getByText('No tag')).toBeInTheDocument();
    expect(
      within(row).getByRole('button', { name: `Design tag ${tagLabelFor('line-1')}` }),
    ).toBeInTheDocument();
    expect(screen.queryByText(tagLabelFor('line-1'))).toBeNull();
  });

  it('AC-S3-2: a line with two tags still renders the line row plus 1a and 1b tag rows', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          lineWith({
            id: 'line-1',
            code: 'SRT-1',
            tags: [
              tagWith('line-1'),
              tagWith('line-1', { id: 'tag-1b', label: '1b', sort_order: 1 }),
            ],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    await screen.findByText('SRT-1');

    expect(document.querySelectorAll('tbody tr')).toHaveLength(3);
    expect(screen.getByText('1a')).toBeInTheDocument();
    expect(screen.getByText('1b')).toBeInTheDocument();
  });

  it('AC-S3-3: a line with one tag and a part keeps the line row, the part row and the 1a tag row', async () => {
    const mirror: PriceTagRequestLinePart = {
      id: 'part-mirror',
      product_id: 'p-mirror',
      code: 'SRTMR502-BL',
      name: 'ZZT Mirror',
      role: null,
      candidates: [],
      sort_order: 0,
    };
    mockGet.mockResolvedValue(
      requestWith({
        lines: [
          lineWith({
            id: 'line-1',
            code: 'SRTBF11834',
            name: 'ZZT Cabinet',
            parts: [mirror],
            tags: [tagWith('line-1')],
          }),
        ],
      }),
    );
    renderDetail();

    await screen.findByRole('heading', { name: /PT-202608-0001/, level: 1 });
    switchTab('Lines');
    await screen.findByText('SRTBF11834');

    expect(document.querySelectorAll('tbody tr')).toHaveLength(3);
    expect(screen.getByText('1a')).toBeInTheDocument();
    expect(screen.getByText(/SRTMR502-BL/)).toBeInTheDocument();
  });

  it('AC-S3-4: Design on the folded row opens the designer for that tag', async () => {
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
    // Exactly one row - the fold - so this Design button IS the folded row's.
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1);

    fireEvent.click(
      await screen.findByRole('button', { name: `Design tag ${tagLabelFor('line-1')}` }),
    );
    expect(push).toHaveBeenCalledWith(
      '/dealer-kit/price-tag-requests/req-1/design?tag=line-1',
    );
  });
});

// ---------------------------------------------------------------------------
// AC-S10-2 (PLAN-price-tag-ai-extract-resolver.md D14): an approved request
// goes back to the designer to print and hand over, not just to export.
// ---------------------------------------------------------------------------

describe('PriceTagRequestDetail - approved goes back to the designer (AC-S10-2)', () => {
  it('the primary CTA reads "Open design" and the per-tag Design button is in the Actions column', async () => {
    mockGet.mockResolvedValue(
      requestWith({
        status: 'approved',
        assigned_to_id: 'user-1',
        lines: [lineWith({ id: 'line-1', code: 'SRT-1' })],
      }),
    );
    renderDetail();

    const primary = await screen.findByTestId('price-tag-primary-cta');
    expect(primary.textContent).toContain('Open design');

    switchTab('Lines');
    expect(
      await screen.findByRole('button', { name: `Design tag ${tagLabelFor('line-1')}` }),
    ).toBeInTheDocument();
  });
});
