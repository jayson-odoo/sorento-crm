/**
 * The designer, once a line carries several tags (S3, D3).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
 * AC-S3-3 (the rail nests tags under lines, selecting a tag edits THAT tag, the
 * doc keys geometry by tag id, `?tag=` replaces `?line=`) and AC-S3-4 (Split and
 * Pick one on an open tag).
 *
 * The one thing that would look like a working feature while being broken: the
 * document is keyed on `request_tag_id` now, so a saved design opened through a
 * line-keyed lookup returns nothing and every tag reads as never designed. The
 * `tagsFromDoc` cases below are that, on the component rather than on the helper
 * (`lib/dealer-kit/request-tags.test.ts` pins the helper itself).
 *
 * Split is asserted as a SERVICE CALL, not as a local state change: the siblings
 * and their geometry are minted on the server (the tag keeps its id, its pins
 * and its placement), so a designer that split in the browser would lose them on
 * the next reload.
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
  splitRequestTag: vi.fn(),
  updateRequestTag: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
}));
vi.mock('../../../../tag-sizes/hooks/useTagSizes', () => ({
  useTagSizesQuery: () => ({ data: [] as unknown[] }),
  useDeleteTagSizePreset: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useCreateTagSize: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
}));

import { listPublishedTemplates } from '../../../../services/tagTemplateService';
import {
  getPriceTagRequest,
  resolveRequestTags,
  splitRequestTag,
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
const mockGetRequest = vi.mocked(getPriceTagRequest);
const mockSplit = vi.mocked(splitRequestTag);
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
    choices: {},
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
    promotion_id: null,
    promotion_name: null,
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
// AC-S3-3 - the rail nests tags under lines
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - tags under a line (S3)', () => {
  it('the rail shows the line once, with its tags nested under it by ordinal', async () => {
    const detail = request({
      lines: [line({ tags: [tag(), tag({ id: 'tag-1b', label: '1b', sort_order: 1 })] })],
    });
    mockResolve.mockResolvedValue([
      row(),
      row({ tag_id: 'tag-1b', tag_label: '1b' }),
    ]);
    await mount(detail);

    // ONE line row - the request keeps showing what the salesperson asked for,
    // which is why cloning lines was rejected.
    expect(screen.getAllByText('SRTBF11834')).toHaveLength(1);
    // Two tag rows, named by ordinal and never by id (AC-X-2).
    expect(screen.getByText('1a')).toBeInTheDocument();
    expect(screen.getByText('1b')).toBeInTheDocument();
    expect(screen.queryByText('tag-1a')).toBeNull();
  });

  it('reads a saved design by TAG id, so every tag opens on what was drawn for it', async () => {
    const detail = request({
      lines: [line({ tags: [tag(), tag({ id: 'tag-1b', label: '1b', sort_order: 1 })] })],
    });
    mockResolve.mockResolvedValue([row(), row({ tag_id: 'tag-1b', tag_label: '1b' })]);

    await mount(detail, docFor('tag-1b', [savedLayer('saved-1'), savedLayer('saved-2')]));

    // 1a has no placement of its own: it clones a starter. 1b's saved two-layer
    // design must be there when it is opened - a lookup by LINE id would find
    // nothing and silently re-clone over the top of it.
    fireEvent.click(screen.getByText('1b'));
    await waitFor(() =>
      expect(screen.getByTestId('canvas-layers').textContent).toBe('2'),
    );
  });

  it('selecting a tag edits THAT tag, not its sibling', async () => {
    const detail = request({
      lines: [line({ tags: [tag(), tag({ id: 'tag-1b', label: '1b', sort_order: 1 })] })],
    });
    mockResolve.mockResolvedValue([
      row({ code: 'AAA-1' }),
      row({ tag_id: 'tag-1b', tag_label: '1b', code: 'AAA-1' }),
    ]);
    await mount(detail, docFor('tag-1b', [savedLayer('saved-1')]));

    // Opens on 1a (the first tag), which has nothing drawn yet.
    const before = canvasDocs.length;
    fireEvent.click(screen.getByText('1b'));
    await waitFor(() => expect(canvasDocs.length).toBeGreaterThan(before));
    await waitFor(() =>
      expect(screen.getByTestId('canvas-layers').textContent).toBe('1'),
    );

    fireEvent.click(screen.getByText('1a'));
    await waitFor(() =>
      expect(screen.getByTestId('canvas-layers').textContent).not.toBe('1'),
    );
  });

  it('?tag= opens that tag, and the deep param is dropped once it has done its job', async () => {
    searchParams = new URLSearchParams('tag=tag-1b');
    const detail = request({
      lines: [line({ tags: [tag(), tag({ id: 'tag-1b', label: '1b', sort_order: 1 })] })],
    });
    mockResolve.mockResolvedValue([row(), row({ tag_id: 'tag-1b', tag_label: '1b' })]);

    await mount(detail, docFor('tag-1b', [savedLayer('saved-1')]));

    await waitFor(() =>
      expect(screen.getByTestId('canvas-layers').textContent).toBe('1'),
    );
    expect(replace).toHaveBeenCalledWith(
      '/dealer-kit/price-tag-requests/req-1/design',
      { scroll: false },
    );
  });

  it('?line= still works, resolving to that line\'s FIRST tag', async () => {
    // Every link written before S3 names a line - the CRM detail page's own row
    // action did until this slice - so they must not dead-end.
    searchParams = new URLSearchParams('line=line-2');
    const detail = request({
      lines: [
        line(),
        line({
          id: 'line-2',
          code: 'BBB-2',
          product_id: 'prod-2',
          sort_order: 1,
          tags: [tag({ id: 'tag-2a', label: '2a' })],
        }),
      ],
    });
    mockResolve.mockResolvedValue([
      row(),
      row({ tag_id: 'tag-2a', line_id: 'line-2', tag_label: '2a', code: 'BBB-2' }),
    ]);

    await mount(detail, docFor('tag-2a', [savedLayer('a'), savedLayer('b'), savedLayer('c')]));

    await waitFor(() =>
      expect(screen.getByTestId('canvas-layers').textContent).toBe('3'),
    );
  });

  // -------------------------------------------------------------------------
  // AC-S3-4 - Split and Pick one
  // -------------------------------------------------------------------------

  it('an open tag says which group is open and offers Split into N tags', async () => {
    await mount(request({ lines: [line({ tags: [OPEN_TAG] })] }));

    expect(screen.getByText('Open: Basin')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Split into 4 tags' }),
    ).toBeInTheDocument();
    // Pick one offers the four candidates by CODE - one choice with four
    // answers, which is the alternative to splitting.
    const pickOne = screen.getByLabelText('Pick one');
    expect(
      within(pickOne).getAllByRole('option').map((option) => option.textContent),
    ).toEqual(['Pick one', ...BASIN_CANDIDATES.map((c) => c.code)]);
  });

  it('Split calls the server and re-reads the request, rather than splitting locally', async () => {
    const before = request({ lines: [line({ tags: [OPEN_TAG] })] });
    const after = request({
      lines: [
        line({
          tags: BASIN_CANDIDATES.map((candidate, index) =>
            tag({
              id: `tag-1${'abcd'[index]}`,
              label: `1${'abcd'[index]}`,
              sort_order: index,
              choices: { Basin: candidate.product_id },
              choices_display: [{ role: 'Basin', code: candidate.code }],
            }),
          ),
        }),
      ],
    });
    mockSplit.mockResolvedValue(after.lines[0].tags);
    mockGetRequest.mockResolvedValue(after);
    await mount(before);

    fireEvent.click(screen.getByRole('button', { name: 'Split into 4 tags' }));

    await waitFor(() =>
      expect(mockSplit).toHaveBeenCalledWith('req-1', OPEN_TAG.id, 'Basin'),
    );
    // The siblings and their copied geometry are minted on the SERVER, so the
    // designer has to re-read rather than invent them.
    await waitFor(() => expect(mockGetRequest).toHaveBeenCalledWith('req-1'));
    await waitFor(() => expect(screen.getByText('1d')).toBeInTheDocument());
    expect(screen.queryByText('Open: Basin')).toBeNull();
  });

  it('Pick one patches THIS tag\'s choices and adds no sibling', async () => {
    const before = request({ lines: [line({ tags: [OPEN_TAG] })] });
    const picked = request({
      lines: [
        line({
          tags: [
            tag({
              choices: { Basin: BASIN_CANDIDATES[1].product_id },
              choices_display: [{ role: 'Basin', code: BASIN_CANDIDATES[1].code }],
            }),
          ],
        }),
      ],
    });
    mockUpdateTag.mockResolvedValue(picked.lines[0].tags[0]);
    mockGetRequest.mockResolvedValue(picked);
    await mount(before);

    fireEvent.change(screen.getByLabelText('Pick one'), {
      target: { value: BASIN_CANDIDATES[1].product_id },
    });

    await waitFor(() =>
      expect(mockUpdateTag).toHaveBeenCalledWith('req-1', OPEN_TAG.id, {
        choices: { Basin: BASIN_CANDIDATES[1].product_id },
      }),
    );
    expect(mockSplit).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText('Open: Basin')).toBeNull());
    expect(screen.queryByText('1b')).toBeNull();
  });

  // -------------------------------------------------------------------------
  // AC-S3-6 - a tag can be removed, never the line's last
  // -------------------------------------------------------------------------

  it('a tag row offers Remove, disabled with a reason while the line has only one tag', async () => {
    await mount(request({ lines: [line({ tags: [tag()] })] }));

    const remove = screen.getByRole('button', { name: 'Remove tag 1a' });
    expect(remove).toBeDisabled();
    // Disabled with no explanation reads as a broken button. The server answers
    // this case with a named 422 (LAST_TAG); the UI says the same thing before
    // the click rather than after it.
    expect(remove).toHaveAttribute('title', expect.stringMatching(/only tag|last tag/i));
    expect(deferredRun).not.toHaveBeenCalled();
  });

  it('on a two-tag line Remove parks the deferred action for THAT tag', async () => {
    const detail = request({
      lines: [line({ tags: [tag(), tag({ id: 'tag-1b', label: '1b', sort_order: 1 })] })],
    });
    mockResolve.mockResolvedValue([row(), row({ tag_id: 'tag-1b', tag_label: '1b' })]);
    await mount(detail);

    const remove = screen.getByRole('button', { name: 'Remove tag 1b' });
    expect(remove).not.toBeDisabled();
    fireEvent.click(remove);

    // Deferred, not confirmed: no dialog, and the countdown is the server's
    // (D7), so what this asserts is the dispatch and its subject.
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(deferredRun).toHaveBeenCalledTimes(1);
    expect(deferredRun).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'tag-1b' }),
    );
  });

  it('shows the line\'s package warning on the LINE, not on its tags', async () => {
    await mount(
      request({
        lines: [line({ package_warning: 'Missing: SRTMR502-BL', tags: [tag()] })],
      }),
    );

    const warning = screen.getByText('Missing: SRTMR502-BL');
    expect(warning).toBeInTheDocument();
    // The warning is about what the salesperson asked for, so it belongs to the
    // line; repeating it on every split tag would be four copies of one fact.
    const tagRow = screen.getByText('1a').closest('button');
    expect(tagRow).not.toBeNull();
    expect(within(tagRow as HTMLElement).queryByText('Missing: SRTMR502-BL')).toBeNull();
  });
});
