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
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PRODUCT_BLOCK_SIZE } from '@/lib/dealer-kit/product-block';
import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from 'sonner';
const mockToastSuccess = vi.mocked(toast.success);

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
// A MOUNT counter (S9 review B1) - distinct from `canvasDocs.length`, which
// grows on every RE-RENDER too. Only the mount-only effect below increments
// this, so a test can prove a resize (or anything else) re-rendered the
// stand-in with new props WITHOUT unmounting and remounting a fresh one -
// which is exactly what keying the editor on tag size used to do.
let canvasMountCount = 0;
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
      canvasMountCount += 1;
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

/** The designer's autosave prop, typed so a test can read back the document
 *  and the `keepalive` flag it was called with. */
type AutosaveFn = (doc: TagSheetDoc, options?: { keepalive?: boolean }) => Promise<void>;

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
  createTemplateFromTag: vi.fn(),
}));
vi.mock('../../../../services/priceTagRequestService', () => ({
  resolveRequestLines: vi.fn(),
  transitionPriceTagRequest: vi.fn(),
  exportTagSheet: vi.fn(),
}));
// Tag Size control's "Saved sizes" group (S4): a react-query hook this suite
// has no QueryClientProvider for, and nothing here tests the saved-sizes flow
// itself - `TagSizeControl.test.tsx` (or its own coverage) owns that. An
// empty list keeps every existing assertion about the "Custom" dropdown and
// the resize flow unchanged.
vi.mock('../../../../tag-sizes/hooks/useTagSizes', () => ({
  useTagSizesQuery: () => ({ data: [] }),
  useDeleteTagSize: () => ({ mutate: vi.fn() }),
  useCreateTagSize: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
}));

import { listPublishedTemplates } from '../../../../services/tagTemplateService';
import { resolveRequestLines } from '../../../../services/priceTagRequestService';
import { RequestTagDesigner } from './RequestTagDesigner';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
} from '../../../../services/priceTagRequestService';
import type { LineTagData, TagSheetDoc, TagTemplate } from '@/lib/dealer-kit/tag-template-types';

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
    <RequestTagDesigner
      request={req}
      initialDoc={null}
      onSave={vi.fn(async () => {})}
      onAutosave={vi.fn<AutosaveFn>(async () => {})}
    />,
  );
}

beforeEach(() => {
  canvasDocs.length = 0;
  canvasMountCount = 0;
  mockListTemplates.mockReset();
  mockResolveRequestLines.mockReset();
  searchParams = new URLSearchParams();
  push.mockReset();
  replace.mockReset();
  mockToastSuccess.mockReset();
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
// A line whose product could not be resolved (457_ptag_line_xco_repair): the
// prices resolve skips a line whose product 404s under the request's
// company - the rail must say so plainly, without a toast, instead of
// showing "Resolving..." forever.
// ---------------------------------------------------------------------------

describe("RequestTagDesigner - a line the request's company cannot resolve", () => {
  it('shows a "Product not found in this company" chip once prices have loaded, for the line resolveRequestLines skipped', async () => {
    mockListTemplates.mockResolvedValue([]);
    // Only line-1 comes back - line-2's product 404d under this request's
    // company and resolve_request_line_data silently skips it.
    mockResolveRequestLines.mockResolvedValue([lineTagData({ line_id: 'line-1' })]);

    renderDesigner(
      request({
        lines: [line({ id: 'line-1' }), line({ id: 'line-2', product_id: 'prod-2' })],
        line_count: 2,
      }),
    );

    expect(
      await screen.findByText('Product not found in this company'),
    ).toBeInTheDocument();
    // The resolved line never shows the chip.
    expect(screen.getByText('Kitchen Sink')).toBeInTheDocument();
  });

  it('the chip never appears while prices are still resolving (the rail is gated behind pricesStatus === loaded)', async () => {
    mockListTemplates.mockResolvedValue([]);
    const prices = deferred<LineTagData[]>();
    mockResolveRequestLines.mockReturnValue(
      prices.promise as unknown as ReturnType<typeof resolveRequestLines>,
    );

    renderDesigner(
      request({
        lines: [line({ id: 'line-1' }), line({ id: 'line-2', product_id: 'prod-2' })],
        line_count: 2,
      }),
    );

    expect(await screen.findByText('Resolving prices...')).toBeInTheDocument();
    expect(screen.queryByText('Product not found in this company')).not.toBeInTheDocument();

    await act(async () => {
      prices.resolve([lineTagData({ line_id: 'line-1' })]);
    });

    expect(
      await screen.findByText('Product not found in this company'),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Autosave (D22, S8, AC-S8-3)
//
// Autosave and manual Save are two different acts on two different routes
// (B1/B3): `onAutosave` writes the request's DRAFT and says nothing, `onSave`
// snapshots an immutable version and toasts. Every test here is about which
// of the two ran, how many times, and what the header said about it.
//
// The starter-tag clone a line gets on open is NOT one of them (S3), so
// nothing has to be drained before the behaviour under test - the first
// assertion in every case below is that opening the page saved nothing.
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - autosave (D22, AC-S8-3)', () => {
  /** Mount with templates and prices settled, and nothing saved yet. */
  async function mountQuiet(overrides: Partial<PriceTagRequestDetail> = {}) {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);
    const onSave = vi.fn(async () => {});
    const onAutosave = vi.fn<AutosaveFn>(async () => {});

    render(
      <RequestTagDesigner
        request={request(overrides)}
        initialDoc={null}
        onSave={onSave}
        onAutosave={onAutosave}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    return { onSave, onAutosave };
  }

  it('collapses rapid edits into a single autosave call, ~1s after the LAST one', async () => {
    const { onSave, onAutosave } = await mountQuiet();

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });
      // A second edit before the first's debounce would have fired resets
      // the clock rather than queuing a second save.
      fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(999);
      });
      expect(onAutosave).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1);
      });
      expect(onAutosave).toHaveBeenCalledTimes(1);
      // The DRAFT route, never the version route.
      expect(onSave).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('says nothing on a successful autosave - the indicator is the whole report (D22)', async () => {
    const { onAutosave } = await mountQuiet();

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(onAutosave).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/^Saved/)).toBeInTheDocument();
      // A toast roughly once a second while somebody designs is noise, not
      // feedback. `onAutosave` is silent by contract and nothing here adds one.
      expect(mockToastSuccess).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('a mode switch (Design -> Arrange) flushes the pending autosave immediately', async () => {
    const { onAutosave } = await mountQuiet();

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
      expect(onAutosave).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'Arrange' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(onAutosave).toHaveBeenCalledTimes(1);

      // The debounce the flush cut short must not ALSO fire later.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(onAutosave).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows Save failed with Retry, and Retry resends the same doc', async () => {
    const { onAutosave } = await mountQuiet();
    onAutosave.mockRejectedValueOnce(new Error('network down'));

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(onAutosave).toHaveBeenCalledTimes(1);
      // The failure reaches the indicator because `onAutosave` rethrows (B2) -
      // a swallowed one left the header reading "Saved" over lost work.
      expect(screen.getByText('Save failed')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(onAutosave).toHaveBeenCalledTimes(2);
      expect(onAutosave.mock.calls[1][0]).toEqual(onAutosave.mock.calls[0][0]);
      expect(screen.queryByText('Save failed')).not.toBeInTheDocument();
      expect(screen.getByText(/^Saved/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

// ---------------------------------------------------------------------------
// Opening and browsing persist NOTHING (S3)
//
// The starter/template clone a line gets when it has no tag yet is the page
// deciding what to draw, not the user deciding anything. Before this, merely
// opening a request with undesigned lines - or clicking down the rail to look
// at them - wrote a design for every line the eye landed on.
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - the starter clone is not a user change (S3)', () => {
  it('saves nothing on open, and nothing while browsing undesigned lines', async () => {
    const lineA = line({ id: 'line-a', product_id: 'prod-a', code: 'AAA-1' });
    const lineB = line({ id: 'line-b', product_id: 'prod-b', code: 'BBB-2', name: 'Basin' });
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2', name: 'Basin' }),
    ]);
    const onSave = vi.fn(async () => {});
    const onAutosave = vi.fn<AutosaveFn>(async () => {});

    render(
      <RequestTagDesigner
        request={request({ lines: [lineA, lineB], line_count: 2 })}
        initialDoc={null}
        onSave={onSave}
        onAutosave={onAutosave}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    // Line B has no tag either - switching to it clones one, which must be as
    // silent as opening was.
    fireEvent.click(screen.getByText('Basin'));
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    // Well past the debounce, on real timers, so a scheduled save would have
    // had every chance to fire.
    await new Promise((resolve) => setTimeout(resolve, 1300));

    expect(onAutosave).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Manual Save is one deliberate version, flushed clear of the autosave (S4)
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - manual Save (S4)', () => {
  it('flushes the pending autosave, then snapshots exactly once', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);
    const order: string[] = [];
    const onSave = vi.fn(async () => {
      order.push('version');
    });
    const onAutosave = vi.fn<AutosaveFn>(async () => {
      order.push('draft');
    });

    render(
      <RequestTagDesigner
        request={request()}
        initialDoc={null}
        onSave={onSave}
        onAutosave={onAutosave}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    // The pending draft went first, so a late draft write cannot land after
    // the snapshot and resurrect the draft the snapshot just cleared.
    expect(order).toEqual(['draft', 'version']);
    expect(onAutosave).toHaveBeenCalledTimes(1);

    // And the debounce the flush consumed does not fire a second time.
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(onAutosave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('leaving the page flushes the last edit, keepalive so it survives teardown', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);
    const onSave = vi.fn(async () => {});
    const onAutosave = vi.fn<AutosaveFn>(async () => {});

    const { unmount } = render(
      <RequestTagDesigner
        request={request()}
        initialDoc={null}
        onSave={onSave}
        onAutosave={onAutosave}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    // An edit whose ~1s debounce has NOT fired - a sidebar click or the
    // browser's Back here is exactly how the edit used to be lost. The route
    // change is this component unmounting, so that is what the test does.
    fireEvent.click(screen.getByRole('button', { name: 'Add layer' }));
    expect(onAutosave).not.toHaveBeenCalled();

    unmount();

    await waitFor(() => expect(onAutosave).toHaveBeenCalledTimes(1));
    expect(onAutosave.mock.calls[0][1]).toEqual({ keepalive: true });
  });

  it('with nothing pending, Save is a single request', async () => {
    mockListTemplates.mockResolvedValue([]);
    mockResolveRequestLines.mockResolvedValue([lineTagData()]);
    const onSave = vi.fn(async () => {});
    const onAutosave = vi.fn<AutosaveFn>(async () => {});

    render(
      <RequestTagDesigner
        request={request()}
        initialDoc={null}
        onSave={onSave}
        onAutosave={onAutosave}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onAutosave).not.toHaveBeenCalled();
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

// ---------------------------------------------------------------------------
// Tag size control (D24, S9, AC-S9-3)
// ---------------------------------------------------------------------------

describe('RequestTagDesigner - tag size control (D24, AC-S9-3)', () => {
  const lineA = line({ id: 'line-a', product_id: 'prod-a', code: 'AAA-1' });
  const lineB = line({ id: 'line-b', product_id: 'prod-b', code: 'BBB-2' });

  it('editing W/H resizes the selected line\'s tag and every one of its copies', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
    ]);
    const onSave = vi.fn<(doc: TagSheetDoc) => Promise<void>>(async () => {});

    render(
      <RequestTagDesigner
        request={request({ lines: [lineA] })}
        initialDoc={null}
        onSave={onSave}
        onAutosave={vi.fn<AutosaveFn>(async () => {})}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const wInput = screen.getByLabelText('Tag width (mm)');
    const hInput = screen.getByLabelText('Tag height (mm)');
    fireEvent.change(wInput, { target: { value: '95' } });
    fireEvent.blur(wInput);
    fireEvent.change(hInput, { target: { value: '44.5' } });
    fireEvent.blur(hInput);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());

    const doc = onSave.mock.calls[onSave.mock.calls.length - 1][0];
    const tag = doc.sheets[0].tags.find((t) => t.request_line_id === 'line-a');
    expect(tag).toMatchObject({ width_mm: 95, height_mm: 44.5 });
  });

  it('"Apply to all lines" resizes every line\'s tag, not only the selected one', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2' }),
    ]);
    const onSave = vi.fn<(doc: TagSheetDoc) => Promise<void>>(async () => {});

    render(
      <RequestTagDesigner
        request={request({ lines: [lineA, lineB] })}
        initialDoc={null}
        onSave={onSave}
        onAutosave={vi.fn<AutosaveFn>(async () => {})}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    // Line B needs a tag of its own before "apply to all" has two lines to
    // reach - selecting it clones one the same way selecting line A already did.
    fireEvent.click(screen.getByText('BBB-2'));
    await waitFor(() =>
      expect(canvasDocs[canvasDocs.length - 1].doc.width_mm).toBe(60),
    );

    const wInput = screen.getByLabelText('Tag width (mm)');
    const hInput = screen.getByLabelText('Tag height (mm)');
    fireEvent.change(wInput, { target: { value: '95' } });
    fireEvent.blur(wInput);
    fireEvent.change(hInput, { target: { value: '44.5' } });
    fireEvent.blur(hInput);
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all lines' }));

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());

    const doc = onSave.mock.calls[onSave.mock.calls.length - 1][0];
    const allTags = doc.sheets.flatMap((s) => s.tags);
    expect(allTags.length).toBeGreaterThan(0);
    for (const tag of allTags) {
      expect(tag).toMatchObject({ width_mm: 95, height_mm: 44.5 });
    }
  });

  // ---------------------------------------------------------------------
  // S9 review B1: typing must commit on blur, never per keystroke - the
  // control used to call onResize on every change, which changed a doc key
  // the editor was mounted on and remounted it (and this very input) mid-
  // keystroke, dropping characters ("95" -> "9").
  // ---------------------------------------------------------------------

  it('typing into H commits on blur, never remounts the editor, and never loses focus (S9 review B1)', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
    ]);
    const onSave = vi.fn<(doc: TagSheetDoc) => Promise<void>>(async () => {});

    render(
      <RequestTagDesigner
        request={request({ lines: [lineA] })}
        initialDoc={null}
        onSave={onSave}
        onAutosave={vi.fn<AutosaveFn>(async () => {})}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const mountsBeforeTyping = canvasMountCount;
    const hInput = screen.getByLabelText('Tag height (mm)');

    await userEvent.clear(hInput);
    await userEvent.type(hInput, '44.5');

    // The SAME DOM node, still focused, still mid-edit - a remount partway
    // through typing (keying the editor on width/height, B1's actual bug)
    // would have swapped this element out from under the keystrokes.
    expect(screen.getByLabelText('Tag height (mm)')).toBe(hInput);
    expect(document.activeElement).toBe(hInput);
    expect(canvasMountCount).toBe(mountsBeforeTyping);
    expect(hInput).toHaveValue(44.5);

    fireEvent.blur(hInput);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());

    const doc = onSave.mock.calls[onSave.mock.calls.length - 1][0];
    const tag = doc.sheets[0].tags.find((t) => t.request_line_id === 'line-a');
    expect(tag?.height_mm).toBe(44.5);
    // Committing the resize (a live prop update, not a remount) still must
    // not have unmounted/remounted the editor.
    expect(canvasMountCount).toBe(mountsBeforeTyping);
  });

  // ---------------------------------------------------------------------
  // S9 review B2: "Apply to all lines" must also reach a line that has not
  // been opened yet - resizeAllTags alone only touches already-cloned tags.
  // ---------------------------------------------------------------------

  it('applying a size to all lines also sets the default for a line opened LATER (S9 review B2)', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    const lineC = line({ id: 'line-c', product_id: 'prod-c', code: 'CCC-3' });
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
      lineTagData({ line_id: 'line-b', code: 'BBB-2' }),
      lineTagData({ line_id: 'line-c', code: 'CCC-3' }),
    ]);
    const onSave = vi.fn<(doc: TagSheetDoc) => Promise<void>>(async () => {});

    render(
      <RequestTagDesigner
        request={request({ lines: [lineA, lineB, lineC] })}
        initialDoc={null}
        onSave={onSave}
        onAutosave={vi.fn<AutosaveFn>(async () => {})}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
    // Only line A has opened so far - B and C are untouched.

    const wInput = screen.getByLabelText('Tag width (mm)');
    const hInput = screen.getByLabelText('Tag height (mm)');
    fireEvent.change(wInput, { target: { value: '95' } });
    fireEvent.blur(wInput);
    fireEvent.change(hInput, { target: { value: '44.5' } });
    fireEvent.blur(hInput);
    fireEvent.click(screen.getByRole('button', { name: 'Apply to all lines' }));

    // Open line C for the FIRST time - it must clone at the request's
    // default size (95x44.5), not its template's own print_size (60x40).
    fireEvent.click(screen.getByText('CCC-3'));
    await waitFor(() => {
      const drawn = canvasDocs[canvasDocs.length - 1].doc;
      expect(drawn.width_mm).toBe(95);
      expect(drawn.height_mm).toBe(44.5);
    });
  });

  // ---------------------------------------------------------------------
  // S9 review S3: a size has to fit the CURRENT imposition sheet - refused
  // inline (no toast), not silently redrawn to something else.
  // ---------------------------------------------------------------------

  it('refuses a size that does not fit the sheet, with an inline reason and no toast (400mm refused)', async () => {
    mockListTemplates.mockResolvedValue([realTemplate()]);
    mockResolveRequestLines.mockResolvedValue([
      lineTagData({ line_id: 'line-a', code: 'AAA-1' }),
    ]);
    const onSave = vi.fn<(doc: TagSheetDoc) => Promise<void>>(async () => {});

    render(
      <RequestTagDesigner
        request={request({ lines: [lineA] })}
        initialDoc={null}
        onSave={onSave}
        onAutosave={vi.fn<AutosaveFn>(async () => {})}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());

    const wInput = screen.getByLabelText('Tag width (mm)');
    fireEvent.change(wInput, { target: { value: '400' } });
    fireEvent.blur(wInput);

    expect(await screen.findByText(/largest that fits this sheet/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const doc = onSave.mock.calls[onSave.mock.calls.length - 1][0];
    const tag = doc.sheets[0].tags.find((t) => t.request_line_id === 'line-a');
    // Refused - the tag keeps its ORIGINAL width (the template's print_size).
    expect(tag?.width_mm).toBe(60);
  });
});
