/**
 * The designer rail after D6/D9 (S12-2): no Split/Pick one anywhere, TAG SIZE
 * pinned at the foot of the top panel, after LINES.
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-line-promo-combo-subject-acceptance-criteria.md`
 * AC-S3-1 (no Open badge / Split / Pick one, even for a resolved-by-split tag)
 * and AC-S3-2 (LINES fills the panel, TAG SIZE sits at its foot, directly
 * above the resize handle).
 *
 * Shares its mock stack and fixtures with the sibling
 * `RequestTagDesigner.tags.test.tsx` verbatim (mount/request/line/tag), so a
 * change to either designer surface cannot leave the two disagreeing about
 * how to mount the component.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
// The designer mounts a react-query mutation (the deferred tag Remove), so a
// bare `render` throws "No QueryClient set" before the component exists.
import { renderWithQueryClient as render } from './testQueryClient';

import type {
  LineTagData,
  PlacedTag,
  TagLayer,
  TagSheetDoc,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const push = vi.fn();
const replace = vi.fn();
let searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace, refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1/design',
  useSearchParams: () => searchParams,
}));

vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings', () => ({
  useKitLibrary: () => ({
    assetUrls: {},
    fonts: [],
    specKeys: [],
    fontOptions: [],
    reload: vi.fn(async () => {}),
    remember: vi.fn(),
  }),
}));

/** Records the doc it was handed, so a test can say WHICH tag the canvas opened on. */
const canvasDocs: TagTemplateDoc[] = [];
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor', () => ({
  TagCanvasEditor: ({
    doc,
    onLayersChange,
    leftRail,
  }: {
    doc: TagTemplateDoc;
    onLayersChange?: (layers: TagLayer[]) => void;
    leftRail?: React.ReactNode;
  }) => {
    canvasDocs.push(doc);
    React.useEffect(() => {
      onLayersChange?.(doc.layers);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <div data-testid="canvas-editor">
        <span data-testid="canvas-layers">{doc.layers.length}</span>
        {leftRail}
      </div>
    );
  },
}));

/**
 * "Pick one" is a `SearchableSelect` (AC-X-1): one choice with N answers, not N
 * buttons. The real control is a Radix popover whose options exist only while it
 * is open - testing it would test the popover - so it is stubbed as a native
 * select, the same stand-in `ProductCombosSection.test.tsx` and the portal form
 * specs use.
 */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <select
      aria-label={props.placeholder ?? ''}
      value={props.value}
      disabled={props.disabled}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

/** The deferred tag Remove (D7): the countdown is parked on the SERVER, so there
 *  is nothing in the browser to wait out - what a test can assert is that the
 *  row dispatched the action for ITS tag. */
const deferredRun = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: deferredRun, targetId: null, isPending: false }),
}));

vi.mock('./ArrangeSheetView', () => ({
  ArrangeSheetView: () => <div data-testid="arrange-view">arrange open</div>,
}));

vi.mock('../../../../services/tagTemplateService', () => ({
  listPublishedTemplates: vi.fn(),
  createTemplateFromTag: vi.fn(),
  updateTemplate: vi.fn(),
  publishTemplate: vi.fn(),
}));
vi.mock('../../../../services/priceTagRequestService', () => ({
  resolveRequestTags: vi.fn(),
  getPriceTagRequest: vi.fn(),
  updateRequestTag: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
}));
vi.mock('../../../../tag-sizes/hooks/useTagSizes', () => ({
  useTagSizesQuery: () => ({ data: [] as unknown[] }),
  useDeleteTagSizePreset: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useCreateTagSize: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
}));
// S8 (AC-S8-1/S8-2) needs a non-zero open-pins count on the rail; unmocked
// elsewhere in this file it silently resolves to nothing (caught), which is
// what every OTHER test here already relies on (0 pins, no badge at all).
vi.mock('../../../../services/priceTagReviewService', () => ({
  listReviewComments: vi.fn(async () => []),
  setReviewCommentResolved: vi.fn(),
}));

import { listPublishedTemplates } from '../../../../services/tagTemplateService';
import { listReviewComments } from '../../../../services/priceTagReviewService';
import {
  getPriceTagRequest,
  resolveRequestTags,
  updateRequestTag,
} from '../../../../services/priceTagRequestService';
import { RequestTagDesigner } from './RequestTagDesigner';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
  PriceTagRequestTag,
} from '../../../../services/priceTagRequestService';

const mockListTemplates = vi.mocked(listPublishedTemplates);
const mockResolve = vi.mocked(resolveRequestTags);
const mockComments = vi.mocked(listReviewComments);
const mockGetRequest = vi.mocked(getPriceTagRequest);
const mockUpdateTag = vi.mocked(updateRequestTag);

// ---------------------------------------------------------------------------
// Fixtures - one line, one open Basin group, four candidates
// ---------------------------------------------------------------------------

const BASIN_CANDIDATES = [
  { product_id: 'p-basin-wh', code: 'SRTBS900-WH' },
  { product_id: 'p-basin-bk', code: 'SRTBS900-BK' },
  { product_id: 'p-basin-gy', code: 'SRTBS900-GY' },
  { product_id: 'p-basin-bg', code: 'SRTBS900-BG' },
];

function tag(overrides: Partial<PriceTagRequestTag> = {}): PriceTagRequestTag {
  return {
    id: 'tag-1a',
    sort_order: 0,
    label: '1a',
    quantity: 1,
    choices_display: [],
    open_groups: [],
    marketing_price_override: null,
    marketing_override_reason: null,
    list_price: 1599,
    sell_price: null,
    ...overrides,
  };
}

function line(overrides: Partial<PriceTagRequestLine> = {}): PriceTagRequestLine {
  return {
    id: 'line-1',
    line_type: 'product',
    product_id: 'prod-cabinet',
    product_set_id: null,
    name: 'ZZT Cabinet',
    code: 'SRTBF11834',
    show_promo_price: false,
    quantity: 1,
    included_accessories: null,
    remarks: null,
    sort_order: 0,
    list_price: 1599,
    sell_price: null,
    parts: [],
    package_warning: null,
    tags: [tag()],
    ...overrides,
  };
}

function request(overrides: Partial<PriceTagRequestDetail> = {}): PriceTagRequestDetail {
  return {
    id: 'req-1',
    doc_number: 'PT-000001',
    debtor_code: null,
    debtor_name: null,
    needed_by_date: null,
    notes: null,
    status: 'designing',
    line_count: 1,
    created_at: '2026-09-01T00:00:00Z',
    assigned_to_id: 'user-1',
    assigned_to_name: 'Marketing Mei',
    contact_name: 'Sales Sam',
    contact_id: 'contact-1',
    lines: [line()],
    ...overrides,
  };
}

function row(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    tag_id: 'tag-1a',
    line_id: 'line-1',
    tag_label: '1a',
    open_groups: [],
    parts: [],
    code: 'SRTBF11834',
    name: 'ZZT Cabinet',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: '',
    specs: [],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
    ...overrides,
  };
}

/** A saved document with ONE placement, keyed by TAG id (S3). */
function docFor(tagId: string, layers: TagLayer[] = []): TagSheetDoc {
  const placed: PlacedTag = {
    id: `${tagId}-c0`,
    template_id: 'tpl-1',
    request_tag_id: tagId,
    x_mm: 5,
    y_mm: 5,
    width_mm: 95,
    height_mm: 44.5,
    layers,
  };
  return {
    kind: 'tag_sheet',
    imposition: {
      preset: 'auto',
      page_width_mm: 210,
      page_height_mm: 297,
      bleed_mm: 3,
      gap_mm: 2,
    },
    sheets: [{ id: 'sheet-1', tags: [placed] }],
  };
}

function savedLayer(id: string): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 1,
    y_mm: 1,
    width_mm: 30,
    height_mm: 8,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: 'code',
    text_override: null,
    props: {
      kind: 'text',
      text: '',
      align: 'left',
      color: '#000',
      fontSize: 10,
      fontFamily: 'Jost',
      fontWeight: 400,
      lineHeight: 1.2,
      letterSpacing: 0,
    },
  };
}

const OPEN_TAG = tag({ open_groups: [{ role: 'Basin', candidates: BASIN_CANDIDATES }] });

beforeEach(() => {
  vi.clearAllMocks();
  canvasDocs.length = 0;
  searchParams = new URLSearchParams();
  mockListTemplates.mockResolvedValue([]);
  mockResolve.mockResolvedValue([row()]);
});

async function mount(detail: PriceTagRequestDetail, initialDoc: TagSheetDoc | null = null) {
  const result = render(
    <RequestTagDesigner
      request={detail}
      initialDoc={initialDoc}
      onSave={vi.fn(async () => {})}
      onAutosave={vi.fn(async () => {})}
    />,
  );
  await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
  return result;
}

// ---------------------------------------------------------------------------
// AC-S3-1 - no Split, no Pick one, anywhere in the rail
// ---------------------------------------------------------------------------

describe('RequestTagDesigner rail (S12-2)', () => {
  it('a tag resolved by auto-split (choices set, no open_groups) offers no Split button and no Pick one select', async () => {
    const splitTag = tag({
      id: 'tag-1a',
      label: '1a',
      choices_display: [{ role: 'Basin', code: 'SRTBS900-WH' }],
      open_groups: [],
    });
    await mount(request({ lines: [line({ tags: [splitTag] })] }));

    expect(screen.queryByRole('button', { name: /split into/i })).toBeNull();
    expect(screen.queryByLabelText('Pick one')).toBeNull();
    expect(screen.queryByText(/^Open:/)).toBeNull();
  });

  it('TAG SIZE renders after LINES inside the same top-panel container', async () => {
    await mount(request());

    const linesHeading = screen.getByText('Lines');
    const tagSizeHeading = screen.getByText('Tag Size');

    // Both are handed to the canvas as ONE `leftRail` node (D9: one panel,
    // no new splitter) - the mocked `TagCanvasEditor` renders it straight
    // inside `canvas-editor`, so that is the shared container LINES and
    // TAG SIZE both live under. `compareDocumentPosition` is the structural
    // check; `DOCUMENT_POSITION_FOLLOWING` means "comes after".
    const container = screen.getByTestId('canvas-editor');
    expect(container).toContainElement(linesHeading);
    expect(container).toContainElement(tagSizeHeading);
    // eslint-disable-next-line no-bitwise
    expect(
      linesHeading.compareDocumentPosition(tagSizeHeading) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// F9 - the rail renders no React "unique key" warning
// ---------------------------------------------------------------------------

describe('RequestTagDesigner rail - no React key warning (F9)', () => {
  it('renders a split line (two tags) alongside a plain line with no "unique key" console.error', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const splitLine = line({
      id: 'line-1',
      code: 'SRTBF11834',
      tags: [
        tag({ id: 'tag-1a', label: '1a' }),
        tag({ id: 'tag-1b', label: '1b', sort_order: 1 }),
      ],
    });
    const plainLine = line({
      id: 'line-2',
      code: 'SRTKS2435',
      product_id: 'prod-sink',
      name: 'ZZT Kitchen Sink',
      sort_order: 1,
      tags: [tag({ id: 'tag-2a', label: '1a' })],
    });

    mockResolve.mockResolvedValue([
      row({ tag_id: 'tag-1a', line_id: 'line-1' }),
      row({ tag_id: 'tag-1b', line_id: 'line-1' }),
      row({ tag_id: 'tag-2a', line_id: 'line-2', code: 'SRTKS2435', name: 'ZZT Kitchen Sink' }),
    ]);

    await mount(request({ lines: [splitLine, plainLine] }));

    // Both lines actually rendered, so the warning (if any) had a chance to
    // fire - not a false green from a line silently failing to mount.
    await screen.findByText('SRTBF11834');
    await screen.findByText('SRTKS2435');

    const keyWarning = errorSpy.mock.calls.find((call) =>
      String(call[0]).includes('unique "key" prop'),
    );
    expect(keyWarning).toBeUndefined();

    errorSpy.mockRestore();
  });
});
