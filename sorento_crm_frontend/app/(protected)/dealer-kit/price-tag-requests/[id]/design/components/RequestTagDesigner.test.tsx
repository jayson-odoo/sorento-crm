/**
 * The design page's own state machine: it must never dead-end (#476, S3).
 *
 * `TagCanvasEditor` needs Konva, fonts and the asset library - none of which
 * exist in jsdom - so it is stood in for by a thin stub that records what it
 * was asked to draw. What is under test here is entirely RequestTagDesigner's
 * OWN logic: which of "loading templates / templates failed / resolving
 * prices / no lines / the canvas" it shows, and which template - a real one or
 * the product-block starter (D6/D13) - a line's tag gets cloned from.
 */

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PRODUCT_BLOCK_SIZE } from '@/lib/dealer-kit/product-block';
import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const push = vi.fn();
const replace = vi.fn();
// Empty by default; the ?line= preselection tests below build their own
// URLSearchParams and stub this per-test.
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

// The stand-in records the doc it was asked to draw so a test can tell a real
// template's clone apart from the starter's, the same idiom
// TagCanvasEditor.preview.test.tsx uses for react-konva/KonvaTagLayer.
//
// It also mirrors the ONE real behaviour Fix B (design lost on Design ->
// Arrange -> Design) turns on: the real editor reads `doc` once, on mount,
// keeps the layers in its OWN state from then on, and its mount effect fires
// `onLayersChange` with whatever it was handed. A stub that just rendered
// `doc.layers` directly would never reproduce a stale remount snapshot.
type TagSheetDocCapture = { doc: TagTemplateDoc };
const canvasDocs: TagSheetDocCapture[] = [];
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
    canvasDocs.push({ doc });
    const [layers, setLayers] = React.useState<TagLayer[]>(doc.layers);
    React.useEffect(() => {
      onLayersChange?.(doc.layers);
      // Mount-only, matching "reads its document once, on mount" - doc is
      // deliberately excluded from the deps so a doc PROP update after mount
      // (which does not happen for the real editor either) cannot re-fire it.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <div data-testid="canvas-editor">
        canvas open
        {leftRail}
        <button
          type="button"
          onClick={() => {
            const next = [...layers, addedLayer(layers.length)];
            setLayers(next);
            onLayersChange?.(next);
          }}
        >
          Add layer
        </button>
        <button
          type="button"
          onClick={() => {
            setLayers([]);
            onLayersChange?.([]);
          }}
        >
          Clear layers
        </button>
      </div>
    );
  },
}));

/** A minimal, valid text layer for the "add a layer" stub button above. */
function addedLayer(index: number): TagLayer {
  return {
    id: `added-${index}`,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 20,
    height_mm: 10,
    rotation_deg: 0,
    z_index: index,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text: 'Added',
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

// Arrange draws through real react-konva/Konva, which needs a real canvas -
// unavailable in jsdom. Toggling to Arrange is exercised by the Fix B tests
// below, so it needs a stand-in the same way TagCanvasEditor does above.
vi.mock('./ArrangeSheetView', () => ({
  ArrangeSheetView: () => <div data-testid="arrange-view">arrange open</div>,
}));

vi.mock('../../../../services/tagTemplateService', () => ({
  listPublishedTemplates: vi.fn(),
}));
vi.mock('../../../../services/priceTagRequestService', () => ({
  resolveRequestLines: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
}));

import { listPublishedTemplates } from '../../../../services/tagTemplateService';
import { resolveRequestLines } from '../../../../services/priceTagRequestService';
import { RequestTagDesigner } from './RequestTagDesigner';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
} from '../../../../services/priceTagRequestService';
import type { LineTagData, TagTemplate } from '@/lib/dealer-kit/tag-template-types';

const mockListTemplates = vi.mocked(listPublishedTemplates);
const mockResolveRequestLines = vi.mocked(resolveRequestLines);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function line(overrides: Partial<PriceTagRequestLine> = {}): PriceTagRequestLine {
  return {
    id: 'line-1',
    line_type: 'product',
    product_id: 'prod-1',
    product_set_id: null,
    name: 'Kitchen Sink',
    code: 'SRT-1234',
    show_promo_price: false,
    quantity: 1,
    alternatives: [],
    included_accessories: null,
    sort_order: 0,
    marketing_price_override: null,
    marketing_override_reason: null,
    list_price: 1599,
    sell_price: null,
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
    assigned_to_name: 'Jayson',
    contact_name: 'Ziv Beh',
    contact_id: 'contact-1',
    lines: [line()],
    ...overrides,
  };
}

function lineTagData(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    line_id: 'line-1',
    code: 'SRT-1234',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: 'Stainless steel',
    specs: [],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    ...overrides,
  };
}

function realTemplate(overrides: Partial<TagTemplate> = {}): TagTemplate {
  return {
    id: 'tpl-1',
    name: 'Ala carte',
    family: 'ala_carte',
    doc: {
      layers: [
        {
          id: 'l1',
          type: 'text',
          x_mm: 0,
          y_mm: 0,
          width_mm: 20,
          height_mm: 10,
          rotation_deg: 0,
          z_index: 0,
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
        },
      ],
      // A distinct size from PRODUCT_BLOCK_SIZE, so a test can tell "cloned
      // from the real template" apart from "built the starter" on sight.
      width_mm: 60,
      height_mm: 40,
    },
    print_size: { width_mm: 60, height_mm: 40 },
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    ...overrides,
  };
}

/** A promise the test controls the resolution of, to pin transient states. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderDesigner(req: PriceTagRequestDetail = request()) {
  return render(
    <RequestTagDesigner request={req} initialDoc={null} onSave={vi.fn(async () => {})} />,
  );
}

beforeEach(() => {
  canvasDocs.length = 0;
  mockListTemplates.mockReset();
  mockResolveRequestLines.mockReset();
  searchParams = new URLSearchParams();
  push.mockReset();
  replace.mockReset();
});

// ---------------------------------------------------------------------------
// Which template a line's tag is cloned from
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - which template a line clones', () => {
  it('clones the product-block starter exactly when templates loaded empty (AC-S3-1)', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);

    renderDesigner();

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const drawn = canvasDocs[canvasDocs.length - 1].doc;
    expect(drawn.width_mm).toBe(PRODUCT_BLOCK_SIZE.width_mm);
    expect(drawn.height_mm).toBe(PRODUCT_BLOCK_SIZE.height_mm);
  });

  it('clones the real published template when one exists (AC-S3-4)', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);

    renderDesigner();

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const drawn = canvasDocs[canvasDocs.length - 1].doc;
    // The template's own print size (60x40), never the starter's (85x58).
    expect(drawn.width_mm).toBe(60);
    expect(drawn.height_mm).toBe(40);
  });

  it('binds the starter to the line\'s REAL product id, not the line id (review #2, #3)', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);

    renderDesigner(request({ lines: [line({ id: 'line-1', product_id: 'prod-1' })] }));

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const drawn = canvasDocs[canvasDocs.length - 1].doc;
    const group = drawn.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_id: 'prod-1' } });
    expect(group?.props).not.toMatchObject({ binding: { product_id: 'line-1' } });
  });

  it('builds a set-block starter, bound to the real set id, for a product_set line (review #1)', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({
        line_id: 'line-2',
        code: 'BF-SET-01',
        name: 'Bathroom Set',
        set_members: '- A1 (Basin)\n- A2 (Tap)',
      }),
    ]);

    renderDesigner(
      request({
        lines: [
          line({
            id: 'line-2',
            line_type: 'product_set',
            product_id: null,
            product_set_id: 'set-1',
          }),
        ],
      }),
    );

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const drawn = canvasDocs[canvasDocs.length - 1].doc;
    // The set footprint (85x62), not the product footprint (85x58).
    expect(drawn.width_mm).toBe(85);
    expect(drawn.height_mm).toBe(62);

    const membersLayer = drawn.layers.find((l) => l.slot_binding === 'set_members');
    expect(membersLayer?.props).toMatchObject({ text: '- A1 (Basin)\n- A2 (Tap)' });

    const group = drawn.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_set_id: 'set-1' } });
  });
});

// ---------------------------------------------------------------------------
// Full screen (S7, AC-S6-1): the shared FocusShell, same as the room designer.
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - full screen (AC-S6-1)', () => {
  it('wraps the canvas in the shared FocusShell, and Escape exits', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);

    renderDesigner();

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    expect(document.querySelector('[data-dk-focus-mode]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Full screen/ }));
    expect(document.querySelector('[data-dk-focus-mode]')).not.toBeNull();
    expect(screen.getByTestId('canvas-editor')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(document.querySelector('[data-dk-focus-mode]')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// A design must survive Design -> Arrange -> Design (Fix B).
//
// `docRef` snapshots the open tag's layers once, keyed by tag id, so the
// editor can remount on the SAME tag without replaying every keystroke.
// Toggling to Arrange unmounts the editor without changing the tag id, so
// without invalidating the snapshot on that unmount, the remount handed the
// editor - and, through its mount effect, the host's OWN `tags` state -
// whatever the snapshot held before the toggle, silently discarding
// anything added since. Save afterwards would then persist the loss.
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - design survives a mode toggle (Fix B)', () => {
  it('keeps a layer added in Design after toggling to Arrange and back', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);

    renderDesigner();

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));

    fireEvent.click(screen.getByRole('button', { name: 'Arrange' }));
    expect(screen.queryByTestId('canvas-editor')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Design' }));
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const drawn = canvasDocs[canvasDocs.length - 1].doc;
    expect(drawn.layers.some((l) => l.id.startsWith('added-'))).toBe(true);
  });

  it('keeps a design cleared to 0 layers, then switched to another line and back, then rebuilt to 3 layers, across a mode toggle', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-1', code: 'SRT-1' }),
      lineTagData({ line_id: 'line-2', code: 'SRT-2', name: 'Bath Tap' }),
    ]);

    renderDesigner(
      request({
        lines: [
          line({ id: 'line-1', code: 'SRT-1' }),
          line({ id: 'line-2', code: 'SRT-2', product_id: 'prod-2' }),
        ],
      }),
    );

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    // Clear line-1's tag to zero layers.
    fireEvent.click(screen.getByRole('button', { name: 'Clear layers' }));

    // Switch to line-2 (clones its own starter) and back to line-1 - the
    // canvas remounts on the tag id both times (existing behaviour, not part
    // of Fix B), so the clear must still be there when line-1 reopens.
    fireEvent.click(screen.getByText('SRT-2'));
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    fireEvent.click(screen.getByText('SRT-1'));
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    expect(canvasDocs[canvasDocs.length - 1].doc.layers).toHaveLength(0);

    // Add 3 layers back.
    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));

    // Toggle to Arrange and back - this is the step that lost the design
    // before Fix B.
    fireEvent.click(screen.getByRole('button', { name: 'Arrange' }));
    fireEvent.click(screen.getByRole('button', { name: 'Design' }));
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    expect(canvasDocs[canvasDocs.length - 1].doc.layers).toHaveLength(3);
  });
});

// ---------------------------------------------------------------------------
// The canvas's own placeholder states
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - explicit canvas states (AC-S3-2, AC-S3-3)', () => {
  it('says "Loading templates..." while the template fetch is in flight', async () => {
    const templatesGate = deferred<TagTemplate[]>();
    mockListTemplates.mockReturnValue(
      templatesGate.promise as unknown as ReturnType<typeof listPublishedTemplates>,
    );
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);

    renderDesigner();

    expect(await screen.findByText('Loading templates...')).toBeInTheDocument();
    expect(screen.queryByTestId('canvas-editor')).not.toBeInTheDocument();

    // Clean up: let the pending promise resolve so React has nothing left in
    // flight after the assertion.
    templatesGate.resolve([]);
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
  });

  it('says "Resolving prices..." once templates have loaded but prices have not', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    const pricesGate = deferred<LineTagData[]>();
    mockResolveRequestLines.mockReturnValue(
      pricesGate.promise as unknown as ReturnType<typeof resolveRequestLines>,
    );

    renderDesigner();

    expect(await screen.findByText('Resolving prices...')).toBeInTheDocument();
    expect(screen.queryByTestId('canvas-editor')).not.toBeInTheDocument();

    pricesGate.resolve([lineTagData()]);
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
  });

  it('shows an explicit error with Retry when the template fetch fails, and Retry recovers it', async () => {
    mockListTemplates.mockRejectedValueOnce(new Error('network down'));
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);

    renderDesigner();

    expect(await screen.findByText('Failed to load tag templates.')).toBeInTheDocument();
    const retryButton = screen.getByRole('button', { name: /retry/i });
    expect(retryButton).toBeInTheDocument();
    expect(screen.queryByTestId('canvas-editor')).not.toBeInTheDocument();

    mockListTemplates.mockResolvedValueOnce([]);
    fireEvent.click(retryButton);

    expect(mockListTemplates).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    expect(screen.queryByText('Failed to load tag templates.')).not.toBeInTheDocument();
  });

  it('shows an explicit error with Retry when price resolution fails, and Retry recovers it (review #5)', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    mockResolveRequestLines.mockRejectedValueOnce(new Error('network down'));

    renderDesigner();

    expect(await screen.findByText('Failed to resolve prices.')).toBeInTheDocument();
    const retryButton = screen.getByRole('button', { name: /retry/i });
    expect(retryButton).toBeInTheDocument();
    // Not "opens with blank data and no cause" - the canvas must not appear
    // at all until prices are either resolved or explicitly retried.
    expect(screen.queryByTestId('canvas-editor')).not.toBeInTheDocument();

    mockResolveRequestLines.mockResolvedValueOnce([lineTagData()]);
    fireEvent.click(retryButton);

    expect(mockResolveRequestLines).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    expect(screen.queryByText('Failed to resolve prices.')).not.toBeInTheDocument();
  });

  it('says there is nothing to design when the request has no lines', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([]);

    renderDesigner(request({ lines: [], line_count: 0 }));

    expect(
      await screen.findByText('This request has no lines, so there is nothing to design.'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('canvas-editor')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ?line= preselection (S10): the detail page's Lines tab opens the designer
// on a SPECIFIC line rather than whichever one this page would default to.
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - ?line= preselection', () => {
  const lineA = line({ id: 'line-a', product_id: 'prod-a', code: 'AAA-1' });
  const lineB = line({ id: 'line-b', product_id: 'prod-b', code: 'BBB-2' });

  it('defaults to the first line when there is no ?line= param', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2' }),
    ]);

    renderDesigner(request({ lines: [lineA, lineB] }));

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    const group = canvasDocs[canvasDocs.length - 1].doc.layers.find(
      (l) => l.props.kind === 'group',
    );
    expect(group?.props).toMatchObject({ binding: { product_id: 'prod-a' } });
  });

  it('preselects the line named by ?line=, not the first one', async () => {
    searchParams = new URLSearchParams('line=line-b');
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2' }),
    ]);

    renderDesigner(request({ lines: [lineA, lineB] }));

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    const group = canvasDocs[canvasDocs.length - 1].doc.layers.find(
      (l) => l.props.kind === 'group',
    );
    expect(group?.props).toMatchObject({ binding: { product_id: 'prod-b' } });
  });

  it('falls back to the first line when ?line= names a line not on this request', async () => {
    searchParams = new URLSearchParams('line=not-a-real-line');
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2' }),
    ]);

    renderDesigner(request({ lines: [lineA, lineB] }));

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    const group = canvasDocs[canvasDocs.length - 1].doc.layers.find(
      (l) => l.props.kind === 'group',
    );
    expect(group?.props).toMatchObject({ binding: { product_id: 'prod-a' } });
  });

  it('strips ?line= from the URL once applied, so a refresh does not snap back to it', async () => {
    searchParams = new URLSearchParams('line=line-b');
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2' }),
    ]);

    renderDesigner(request({ lines: [lineA, lineB] }));

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    expect(replace).toHaveBeenCalledWith(
      '/dealer-kit/price-tag-requests/req-1/design',
      { scroll: false },
    );
  });

  it('leaves the URL alone when there was no ?line= to strip', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2' }),
    ]);

    renderDesigner(request({ lines: [lineA, lineB] }));

    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    expect(replace).not.toHaveBeenCalled();
  });
});
