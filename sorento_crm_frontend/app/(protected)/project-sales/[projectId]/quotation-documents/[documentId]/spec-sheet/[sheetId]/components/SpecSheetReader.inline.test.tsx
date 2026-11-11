/**
 * SPEC-SHEET-V2 F4: the reader IS the editor. Every page near the viewport is a LIVE designer
 * canvas (at most 3), the rest stay still pictures; the inspector follows the selection; every
 * change autosaves a second later, per page; undo/redo is per page; "Every page" applies a layer
 * change to the whole sheet; the thumbnail rail draws real mini pages from the chunks the stack
 * already loads; and a phone edits too.
 *
 * The designer is stood in for by a fake that exposes what the host drives: selection in and out,
 * layers in and out, and the controller handle the inspector and toolbar act through.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = vi.fn();
HTMLElement.prototype.scrollTo = vi.fn() as never;

// ---- a controllable IntersectionObserver (stack pages carry data-page-key, rail thumbs data-rail-key)

type Observer = {
  callback: (entries: unknown[]) => void;
  targets: Set<Element>;
};
const observers: Observer[] = [];
class FakeIntersectionObserver {
  private readonly record: Observer;
  constructor(callback: (entries: unknown[]) => void) {
    this.record = { callback, targets: new Set() };
    observers.push(this.record);
  }
  observe(el: Element) {
    this.record.targets.add(el);
  }
  unobserve(el: Element) {
    this.record.targets.delete(el);
  }
  disconnect() {
    this.record.targets.clear();
  }
  takeRecords() {
    return [];
  }
}
(globalThis as { IntersectionObserver: unknown }).IntersectionObserver =
  FakeIntersectionObserver;

function reportAttr(attr: string, visibleKeys: string[]) {
  act(() => {
    for (const observer of observers) {
      const entries = [...observer.targets]
        .filter((el) => el.getAttribute(attr))
        .map((el) => ({
          target: el,
          isIntersecting: visibleKeys.includes(el.getAttribute(attr) as string),
        }));
      if (entries.length) observer.callback(entries);
    }
  });
}
const report = (keys: string[]) => reportAttr('data-page-key', keys);
const reportRail = (keys: string[]) => reportAttr('data-rail-key', keys);

// ---- mocks -------------------------------------------------------------------------------------

const getSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
const saveSpecSheetPageEdit = vi.fn();
const applySpecSheetLayerToAll = vi.fn();
const updateSpecSheet = vi.fn();
const listSpecSheets = vi.fn();
vi.mock(
  '@/app/(protected)/project-sales/_shared/services/specSheetService',
  () => ({
    listSpecSheets: (...a: unknown[]) => listSpecSheets(...a),
    createSpecSheet: vi.fn(),
    getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
    updateSpecSheet: (...a: unknown[]) => updateSpecSheet(...a),
    getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
    getSpecSheetPageDesign: vi.fn(),
    getSpecSheetPageImages: vi.fn(async () => ({ images: {}, assets: {} })),
    saveSpecSheetPageEdit: (...a: unknown[]) => saveSpecSheetPageEdit(...a),
    applySpecSheetLayerToAll: (...a: unknown[]) =>
      applySpecSheetLayerToAll(...a),
    queueSpecSheetPdf: vi.fn(),
  }),
);

let pageParam: string | null = null;
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () =>
    '/project-sales/p1/quotation-documents/d1/spec-sheet/sheet-1',
  useSearchParams: () =>
    new URLSearchParams(pageParam ? { page: pageParam } : {}),
  useParams: () => ({ projectId: 'p1', documentId: 'd1', sheetId: 'sheet-1' }),
}));
vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    custom: vi.fn(),
    dismiss: vi.fn(),
  },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({
    pending: null,
    last_outcome: null,
  })),
}));
vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => undefined),
  ensureSeedFontsLoaded: vi.fn(async () => undefined),
}));
let mobile = false;
vi.mock('@/hooks/use-mobile', () => ({ useIsMobile: () => mobile }));

// The still-picture renderer (rail thumbnails, pages outside the live set).
vi.mock(
  '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer',
  () => ({
    default: ({
      doc,
    }: {
      doc: { sheets: { tags: { request_tag_id: string }[] }[] };
    }) => (
      <div
        data-testid={`tag-sheet-renderer-${doc?.sheets?.[0]?.tags?.[0]?.request_tag_id}`}
        data-renderer="1"
      />
    ),
  }),
);

// The inspector and the library hook, stood in for.
vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings',
  () => ({
    useKitLibrary: () => ({
      assetUrls: {},
      thumbUrls: {},
      fonts: [],
      specKeys: [],
      fontOptions: [],
      reload: vi.fn(),
      remember: vi.fn(),
      rename: vi.fn(),
      forget: vi.fn(),
    }),
  }),
);
vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/InspectorPanel',
  () => ({
    InspectorPanel: ({
      layer,
      onUpdate,
    }: {
      layer: { id: string } | null;
      onUpdate: (id: string, changes: Record<string, unknown>) => void;
    }) => (
      <div data-testid="inspector" data-layer={layer?.id ?? ''}>
        <button
          type="button"
          onClick={() => layer && onUpdate(layer.id, { x_mm: 77 })}
        >
          move logo
        </button>
        <button
          type="button"
          onClick={() => layer && onUpdate(layer.id, { y_mm: 40 })}
        >
          lower logo
        </button>
      </div>
    ),
  }),
);

type FakeProps = {
  doc: { layers: Record<string, unknown>[] };
  docId: string;
  onLayersChange: (layers: Record<string, unknown>[]) => void;
  embedded: {
    selectedLayerId: string | null;
    onSelect: (id: string | null) => void;
    layers?: Record<string, unknown>[];
    readOnly?: boolean;
    active?: boolean;
    onEditField?: (layerId: string) => void;
    controllerRef: { current: unknown };
  };
};
const liveSeen = new Set<string>();
const mounts = new Map<string, number>();
let lastDocLayers: Record<string, unknown>[] = [];
let livePeak = 0;
let liveNow = 0;
vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor',
  () => ({
    TagCanvasEditor: function FakeEditor(props: FakeProps) {
      const key = props.docId.split(':').slice(1).join(':');
      lastDocLayers = props.doc.layers as unknown as Record<string, unknown>[];
      // The canvas owns its layers, adopts the host's when they differ, and reports every change.
      const [layers, setLayers] = React.useState(props.doc.layers);
      const latest = React.useRef(layers);
      latest.current = layers;
      const hostLayers = props.embedded.layers;
      React.useEffect(() => {
        if (hostLayers && hostLayers !== latest.current) setLayers(hostLayers);
      }, [hostLayers]);
      React.useEffect(() => {
        mounts.set(key, (mounts.get(key) ?? 0) + 1);
        liveSeen.add(key);
        liveNow += 1;
        livePeak = Math.max(livePeak, liveNow);
        return () => {
          liveNow -= 1;
        };
      }, [key]);
      React.useEffect(() => {
        props.onLayersChange(layers);
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [layers]);
      const change = (next: Record<string, unknown>[]) => setLayers(next);
      props.embedded.controllerRef.current = {
        updateLayer: (id: string, changes: Record<string, unknown>) =>
          change(
            latest.current.map((l) => (l.id === id ? { ...l, ...changes } : l)),
          ),
        updateLayerProps: (id: string, changes: Record<string, unknown>) =>
          change(
            latest.current.map((l) =>
              l.id === id
                ? { ...l, props: { ...(l.props as object), ...changes } }
                : l,
            ),
          ),
      };
      return (
        <div
          data-testid={`live-canvas-${key}`}
          data-readonly={props.embedded.readOnly ? 'yes' : 'no'}
          data-active={props.embedded.active ? 'yes' : 'no'}
          data-layers={layers.map((l) => l.id).join(',')}
          data-logo-x={JSON.stringify(layers.find((l) => l.id === 'logo')?.x_mm ?? null)}
        >
          <button type="button" onClick={() => props.embedded.onSelect('logo')}>
            {`select ${key}`}
          </button>
          <button
            type="button"
            onClick={() =>
              change(
                latest.current.map((l) =>
                  l.id === 'logo' ? { ...l, x_mm: (l.x_mm as number) + 1 } : l,
                ),
              )
            }
          >
            {`nudge ${key}`}
          </button>
          <button
            type="button"
            onClick={() => props.embedded.onEditField?.('area')}
          >
            {`double-click area ${key}`}
          </button>
          <button
            type="button"
            onClick={() => props.embedded.onEditField?.('desc')}
          >
            {`double-click description ${key}`}
          </button>
          <button
            type="button"
            onClick={() => props.embedded.onEditField?.('desc0')}
          >
            {`double-click accessory description ${key}`}
          </button>
        </div>
      );
    },
  }),
);

import { SpecSheetReader } from './SpecSheetReader';

// ---- fixtures ------------------------------------------------------------------------------------

const KEYS = ['cover', ...Array.from({ length: 29 }, (_, i) => `k${i + 1}`)];
const LOGO = {
  id: 'logo',
  type: 'text',
  x_mm: 5,
  y_mm: 2,
  width_mm: 30,
  height_mm: 8,
  rotation_deg: 0,
  z_index: 1,
  visible: true,
  props: {
    kind: 'text',
    text: 'SORENTO',
    fontFamily: 'DM Sans',
    fontSize: 12,
    color: '#000000',
    align: 'left',
  },
};

const AREA = {
  ...LOGO,
  id: 'area',
  y_mm: 40,
  z_index: 2,
  props: { ...LOGO.props, text: 'AREA : {{line.area}}' },
};

// B1: a text layer printing the spec sheet description, for the main item and for accessory 1.
const DESC = {
  ...LOGO,
  id: 'desc',
  y_mm: 60,
  z_index: 3,
  props: { ...LOGO.props, text: '{{product.spec_sheet_description}}' },
};
const DESC0 = {
  ...DESC,
  id: 'desc0',
  y_mm: 80,
  props: { ...DESC.props, subjectPart: 0 },
};

function detail() {
  return {
    id: 'sheet-1',
    sheet_no: 1,
    label: 'SS1',
    source_label: 'PRJQ-2026-0027-R1',
    source_hint: '',
    is_draft: false,
    templates: {
      cover: { id: 'tc', name: 'Cover', version_no: 1 },
      page: { id: 'tp', name: 'Page', version_no: 1 },
      single: null,
    },
    templates_missing: [],
    newer_templates: false,
    page_size: { width_mm: 338.7, height_mm: 190.5 },
    pages: KEYS.map((key, i) => ({
      key,
      number: key === 'cover' ? 1 : i + 1,
      code: key === 'cover' ? '' : `CODE-${key}`,
      name: key === 'cover' ? 'Cover' : `Product ${key}`,
      brand: '',
      area: '',
      area_default: '',
      comment: '',
      marker: '',
      hidden: false,
      picked: [],
      accessories:
        key === 'k2'
          ? [
              {
                key: null,
                source: 'set',
                product_id: 'acc-1',
                code: 'AV-1',
                name: 'Angle valve',
                brand: '',
                spec_sheet_description: 'Valve default',
              },
            ]
          : [],
      description: key === 'k3' ? 'Typed before' : '',
      accessory_descriptions: {},
      spec_sheet_description_default: `Default of ${key}`,
      edited: false,
      template: key === 'cover' ? 'cover' : 'page',
    })),
    prev_id: null,
    next_id: null,
    can_edit: true,
  };
}

function previewFor(keys: string[]) {
  return {
    doc: {
      kind: 'tag_sheet',
      imposition: {
        preset: 'custom',
        page_width_mm: 338.7,
        page_height_mm: 190.5,
        bleed_mm: 0,
        gap_mm: 0,
      },
      sheets: keys.map((key) => ({
        id: `sheet-${key}`,
        tags: [
          {
            id: `tag-${key}`,
            template_id: 't',
            request_tag_id: key,
            x_mm: 0,
            y_mm: 0,
            width_mm: 338.7,
            height_mm: 190.5,
            layers: [LOGO, AREA, DESC, DESC0],
          },
        ],
      })),
    },
    resolvedData: Object.fromEntries(
      keys.map((k) => [k, { code: k, images: [], parts: [] }]),
    ),
    assets: {},
    images: {},
    fonts: [],
    version: 1,
    hidden: [],
    page_size: { width_mm: 338.7, height_mm: 190.5 },
  };
}

function renderReader() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpecSheetReader projectId="p1" documentId="d1" sheetId="sheet-1" />
    </QueryClientProvider>,
  );
}

const live = () => document.querySelectorAll('[data-testid^="live-canvas-"]');

beforeEach(() => {
  observers.length = 0;
  liveSeen.clear();
  livePeak = 0;
  liveNow = 0;
  mobile = false;
  pageParam = null;
  getSpecSheet.mockReset().mockResolvedValue(detail());
  updateSpecSheet.mockReset().mockResolvedValue(detail());
  saveSpecSheetPageEdit.mockReset().mockResolvedValue(detail());
  applySpecSheetLayerToAll.mockReset().mockResolvedValue(detail());
  getSpecSheetPreview
    .mockReset()
    .mockImplementation(
      async (_p: string, _d: string, _s: string, keys: string[]) =>
        previewFor(keys),
    );
});

afterEach(() => {
  vi.useRealTimers();
});

describe('live canvases', () => {
  it('mounts at most 3 live canvases for a 30-page sheet; the other visible pages stay still pictures', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(live()).toHaveLength(0);

    report(['cover', 'k1', 'k2', 'k3', 'k4']);

    await waitFor(() => expect(live().length).toBeGreaterThan(0));
    expect(live()).toHaveLength(3);
    expect(livePeak).toBeLessThanOrEqual(3);
    await waitFor(() =>
      expect(screen.queryByTestId('tag-sheet-renderer-k4')).not.toBeNull(),
    );
    expect(screen.queryByTestId('tag-sheet-renderer-k3')).not.toBeNull();
    expect(screen.queryByTestId('live-canvas-k4')).toBeNull();
  });

  it('opens the page named in ?page= (the old Edit page link)', async () => {
    pageParam = 'k7';
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await waitFor(() =>
      expect(HTMLElement.prototype.scrollTo).toHaveBeenCalled(),
    );
  });
});

describe('selection and the inspector', () => {
  it('shows the inspector for the layer selected on page 5, and nothing before', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k4', 'k5', 'k6']);
    await screen.findByTestId('live-canvas-k5');
    expect(screen.queryByTestId('inspector')).toBeNull();

    fireEvent.click(
      within(screen.getByTestId('live-canvas-k5')).getByText('select k5'),
    );

    const inspector = await screen.findByTestId('inspector');
    expect(inspector).toHaveAttribute('data-layer', 'logo');
    expect(screen.getByTestId('reader-inspector')).toHaveAttribute(
      'data-page-key',
      'k5',
    );
  });
});

describe('which page a paste or shortcut acts on (crew pass on #2331)', () => {
  const activeOf = (key: string) =>
    screen.getByTestId(`live-canvas-${key}`).getAttribute('data-active');

  it('the page the user last pressed on, not the one scrolled into view or holding an old selection', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k4', 'k5', 'k6']);
    await screen.findByTestId('live-canvas-k6');

    fireEvent.click(within(screen.getByTestId('live-canvas-k5')).getByText('select k5'));
    await screen.findByTestId('inspector');
    expect(activeOf('k5')).toBe('yes');

    // An empty spot on another page: that page is now the target, and k5's selection goes.
    fireEvent.pointerDown(screen.getByTestId('spec-page-k6'));
    await waitFor(() => expect(activeOf('k6')).toBe('yes'));
    expect(activeOf('k5')).toBe('no');
    expect(activeOf('k4')).toBe('no');
    expect(screen.queryByTestId('inspector')).toBeNull();
  });

  it('a pressed page that shows a still picture becomes a live canvas and the target', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k4', 'k5', 'k6', 'k7', 'k8']);
    await screen.findByTestId('live-canvas-k6');
    expect(screen.queryByTestId('live-canvas-k8')).toBeNull();

    fireEvent.pointerDown(screen.getByTestId('spec-page-k8'));
    await screen.findByTestId('live-canvas-k8');
    expect(activeOf('k8')).toBe('yes');
  });

  it('Undo follows the pressed page, not the page edited last somewhere else', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k4', 'k5', 'k6']);
    await screen.findByTestId('live-canvas-k6');
    fireEvent.click(within(screen.getByTestId('live-canvas-k5')).getByText('nudge k5'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Undo' })).not.toBeDisabled(),
    );

    fireEvent.pointerDown(screen.getByTestId('spec-page-k6'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled(),
    );
  });

  it('a page that leaves the live canvases and comes back keeps its latest layers, and the next save carries both edits (crew pass: data loss)', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'], shouldAdvanceTime: true });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2', 'k3', 'k4']);
    await screen.findByTestId('live-canvas-k3');
    const logoX = () =>
      (JSON.parse(screen.getByTestId('live-canvas-k3').getAttribute('data-logo-x') ?? 'null') as number);

    // Move a box on page 3.
    fireEvent.click(within(screen.getByTestId('live-canvas-k3')).getByText('nudge k3'));
    await waitFor(() => expect(logoX()).toBe(6));

    // Page 4 takes a live slot: page 3 goes back to a picture.
    fireEvent.pointerDown(screen.getByTestId('spec-page-k4'));
    await waitFor(() => expect(screen.queryByTestId('live-canvas-k3')).toBeNull());

    // Back to page 3: it shows the moved box, not the old one.
    fireEvent.pointerDown(screen.getByTestId('spec-page-k3'));
    await screen.findByTestId('live-canvas-k3');
    expect(logoX()).toBe(6);

    // Another edit there, then the save: both moves are in it.
    fireEvent.click(within(screen.getByTestId('live-canvas-k3')).getByText('nudge k3'));
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    await waitFor(() => expect(saveSpecSheetPageEdit).toHaveBeenCalled());
    const last = saveSpecSheetPageEdit.mock.calls.at(-1)!;
    expect(last[3]).toBe('k3');
    expect((last[4] as { id: string; x_mm: number }[]).find((l) => l.id === 'logo')?.x_mm).toBe(7);
  });

  it('a right-click makes its page the target too', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k4', 'k5', 'k6']);
    await screen.findByTestId('live-canvas-k4');

    fireEvent.pointerDown(screen.getByTestId('spec-page-k4'), { button: 2 });
    await waitFor(() => expect(activeOf('k4')).toBe('yes'));
    expect(activeOf('k5')).toBe('no');
  });
});

describe('autosave and undo', () => {
  async function ready() {
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout'],
      shouldAdvanceTime: true,
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    await screen.findByTestId('live-canvas-k1');
  }

  it('one change triggers exactly one PUT, one second after it', async () => {
    await ready();
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );

    await act(async () => {
      vi.advanceTimersByTime(900);
    });
    expect(saveSpecSheetPageEdit).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    await waitFor(() => expect(saveSpecSheetPageEdit).toHaveBeenCalledTimes(1));
    const [p, d, s, key, layers] = saveSpecSheetPageEdit.mock.calls[0];
    expect([p, d, s, key]).toEqual(['p1', 'd1', 'sheet-1', 'k1']);
    expect((layers as { x_mm: number }[])[0].x_mm).toBe(6);
    expect(await screen.findByText('Saved')).toBeInTheDocument();
  });

  it('two quick changes make one PUT with the latest layers', async () => {
    await ready();
    const nudge = within(screen.getByTestId('live-canvas-k1')).getByText(
      'nudge k1',
    );
    fireEvent.click(nudge);
    await act(async () => {
      vi.advanceTimersByTime(500);
    });
    fireEvent.click(nudge);
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => expect(saveSpecSheetPageEdit).toHaveBeenCalledTimes(1));
    expect(
      (saveSpecSheetPageEdit.mock.calls[0][4] as { x_mm: number }[])[0].x_mm,
    ).toBe(7);
  });

  it('Undo restores the page and saves it', async () => {
    await ready();
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    await waitFor(() => expect(saveSpecSheetPageEdit).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => expect(saveSpecSheetPageEdit).toHaveBeenCalledTimes(2));
    expect(
      (saveSpecSheetPageEdit.mock.calls[1][4] as { x_mm: number }[])[0].x_mm,
    ).toBe(5);
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }));
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    await waitFor(() => expect(saveSpecSheetPageEdit).toHaveBeenCalledTimes(3));
    expect(
      (saveSpecSheetPageEdit.mock.calls[2][4] as { x_mm: number }[])[0].x_mm,
    ).toBe(6);
  });

  it('shows an error mark when the save fails', async () => {
    saveSpecSheetPageEdit.mockRejectedValue(new Error('too large'));
    await ready();
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(await screen.findByText('Not saved')).toBeInTheDocument();
  });
});

describe('apply to every page', () => {
  it('sends the layer id and the changes to the new endpoint when "Every page" is chosen', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');

    fireEvent.click(
      screen.getByRole('radio', { name: 'Every page' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'move logo' }));

    await waitFor(() =>
      expect(applySpecSheetLayerToAll).toHaveBeenCalledTimes(1),
    );
    expect(applySpecSheetLayerToAll).toHaveBeenCalledWith(
      'p1',
      'd1',
      'sheet-1',
      'logo',
      { x_mm: 77 },
      'k1',
    );
  });

  it('by default ("This page") nothing goes to the every-page endpoint', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');

    fireEvent.click(screen.getByRole('button', { name: 'move logo' }));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });

    expect(applySpecSheetLayerToAll).not.toHaveBeenCalled();
  });
});

describe('apply to every page: one send per pause, other pages held while it runs', () => {
  async function selectedEveryPage() {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    await screen.findByTestId('live-canvas-k1');
    await screen.findByTestId('live-canvas-k2');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');
    fireEvent.click(
      screen.getByRole('radio', { name: 'Every page' }),
    );
  }

  it('changes made in quick succession go out as ONE apply with all of them', async () => {
    await selectedEveryPage();
    fireEvent.click(screen.getByRole('button', { name: 'move logo' }));
    fireEvent.click(screen.getByRole('button', { name: 'lower logo' }));

    await waitFor(() =>
      expect(applySpecSheetLayerToAll).toHaveBeenCalledTimes(1),
    );
    expect(applySpecSheetLayerToAll.mock.calls[0][4]).toEqual({
      x_mm: 77,
      y_mm: 40,
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 700));
    });
    expect(applySpecSheetLayerToAll).toHaveBeenCalledTimes(1);
  });

  it('every other page is read-only until the apply answers, so no edit there is saved over it', async () => {
    let answer: (v: unknown) => void = () => undefined;
    applySpecSheetLayerToAll.mockImplementationOnce(
      () => new Promise((resolve) => (answer = resolve)),
    );
    await selectedEveryPage();
    fireEvent.click(screen.getByRole('button', { name: 'move logo' }));
    await waitFor(() =>
      expect(applySpecSheetLayerToAll).toHaveBeenCalledTimes(1),
    );

    expect(screen.getByTestId('live-canvas-k2')).toHaveAttribute(
      'data-readonly',
      'yes',
    );
    expect(screen.getByTestId('live-canvas-k1')).toHaveAttribute(
      'data-readonly',
      'no',
    );

    await act(async () => {
      answer(detail());
    });
    await waitFor(() =>
      expect(screen.getByTestId('live-canvas-k2')).toHaveAttribute(
        'data-readonly',
        'no',
      ),
    );
  });
});

describe('apply to every page restarts only the pages the server changed', () => {
  it('the page it started from keeps its canvas (no remount, selection kept); the others restart', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    await screen.findByTestId('live-canvas-k1');
    await screen.findByTestId('live-canvas-k2');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');
    const k1Before = mounts.get('k1') ?? 0;
    const k2Before = mounts.get('k2') ?? 0;
    fireEvent.click(
      screen.getByRole('radio', { name: 'Every page' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'lower logo' }));
    await waitFor(() =>
      expect(applySpecSheetLayerToAll).toHaveBeenCalledTimes(1),
    );
    await waitFor(() => expect(mounts.get('k2')).toBe(k2Before + 1));
    expect(mounts.get('k1')).toBe(k1Before);
    expect(screen.getByTestId('inspector')).toHaveAttribute('data-layer', 'logo');
  });
});

describe('a change made ON the canvas in Every-page mode', () => {
  it('a drag of the selected layer goes to every page, like an Inspector change', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');
    fireEvent.click(
      screen.getByRole('radio', { name: 'Every page' }),
    );
    // The fake canvas "drags" the selected logo 1 mm right.
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );
    await waitFor(() =>
      expect(applySpecSheetLayerToAll).toHaveBeenCalledTimes(1),
    );
    expect(applySpecSheetLayerToAll).toHaveBeenCalledWith(
      'p1',
      'd1',
      'sheet-1',
      'logo',
      { x_mm: 6 },
      'k1',
    );
  });

  it('in This-page mode a drag stays on its page', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 800));
    });
    expect(applySpecSheetLayerToAll).not.toHaveBeenCalled();
  });
});

describe('AREA, COMMENT and marker on a live page', () => {
  it('their button lets clicks through to the canvas but stays reachable by keyboard; a double-click opens the field box', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    const page = screen.getByTestId('spec-page-live-k1').parentElement!;
    // Tab + Enter still reach the field; the pointer passes through to select / drag the layer.
    const button = within(page).getByRole('button', { name: 'Edit Area' });
    expect(button.className).toContain('pointer-events-none');

    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText(
        'double-click area k1',
      ),
    );
    const box = await screen.findByRole('textbox', { name: 'Area' });
    fireEvent.change(box, { target: { value: 'lobby' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalled());
  });
});

describe('the spec sheet description override on a live page (B1)', () => {
  async function openLive(key: string) {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report([key]);
    await screen.findByTestId(`live-canvas-${key}`);
    return screen.getByTestId(`live-canvas-${key}`);
  }
  const lastRows = () =>
    (updateSpecSheet.mock.calls.at(-1)![3] as { rows: Record<string, unknown>[] })
      .rows;

  it('a double-click opens a multi-line box with the product text; Enter adds a line, Ctrl+Enter saves the override', async () => {
    const canvas = await openLive('k1');
    fireEvent.click(within(canvas).getByText('double-click description k1'));
    const box = (await screen.findByRole('textbox', {
      name: 'Spec sheet description',
    })) as HTMLTextAreaElement;
    expect(box.tagName).toBe('TEXTAREA');
    expect(box.value).toBe('Default of k1');

    fireEvent.change(box, { target: { value: 'Line one\nLine two' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(updateSpecSheet).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: 'Enter', ctrlKey: true });
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalled());
    expect(lastRows().find((r) => r.key === 'k1')).toMatchObject({
      description: 'Line one\nLine two',
    });
  });

  it('Escape cancels without saving', async () => {
    const canvas = await openLive('k1');
    fireEvent.click(within(canvas).getByText('double-click description k1'));
    const box = await screen.findByRole('textbox', { name: 'Spec sheet description' });
    fireEvent.change(box, { target: { value: 'Never saved' } });
    fireEvent.keyDown(box, { key: 'Escape' });
    expect(screen.queryByRole('textbox', { name: 'Spec sheet description' })).toBeNull();
    expect(updateSpecSheet).not.toHaveBeenCalled();
  });

  it('shows the stored override, and "Reset to product text" clears it', async () => {
    const canvas = await openLive('k3');
    fireEvent.click(within(canvas).getByText('double-click description k3'));
    const box = (await screen.findByRole('textbox', {
      name: 'Spec sheet description',
    })) as HTMLTextAreaElement;
    expect(box.value).toBe('Typed before');
    fireEvent.mouseDown(screen.getByRole('button', { name: 'Reset to product text' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reset to product text' }));
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalled());
    expect(lastRows().find((r) => r.key === 'k3')).toMatchObject({ description: '' });
  });

  it('a layer pointed at an accessory edits that accessory by product id', async () => {
    const canvas = await openLive('k2');
    fireEvent.click(
      within(canvas).getByText('double-click accessory description k2'),
    );
    const box = (await screen.findByRole('textbox', {
      name: 'Spec sheet description',
    })) as HTMLTextAreaElement;
    expect(box.value).toBe('Valve default');
    fireEvent.change(box, { target: { value: 'Valve typed' } });
    fireEvent.keyDown(box, { key: 'Enter', metaKey: true });
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalled());
    const row = lastRows().find((r) => r.key === 'k2')!;
    expect(row).toMatchObject({ accessory_descriptions: { 'acc-1': 'Valve typed' } });
    expect(row.description).toBe('');
  });
});

describe('the save state in the toolbar', () => {
  it('has a fixed width and never wraps, so "Saving..." vs "Saved" cannot reflow the toolbar', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    const state = await screen.findByTestId('spec-sheet-save-state');
    expect(state.className).toContain('whitespace-nowrap');
    expect(state.className).toContain('shrink-0');
    expect(state.className).toMatch(/\bw-\[|\bw-\d/);
  });
});

describe('thumbnail rail', () => {
  it('draws real mini pages and asks for chunks, never for single thumbnails', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['cover', 'k1']);
    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(1));

    // The rail scrolls on its own: thumbnails 6-8 are in ITS view (chunk 1), 0-5 are loaded.
    reportRail(['cover', 'k1', 'k2', 'k6', 'k7', 'k8']);

    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(
        within(screen.getByTestId('spec-rail-k7')).queryByTestId(
          'tag-sheet-renderer-k7',
        ),
      ).not.toBeNull(),
    );
    expect(
      within(screen.getByTestId('spec-rail-k2')).queryByTestId(
        'tag-sheet-renderer-k2',
      ),
    ).not.toBeNull();
    // A thumbnail outside the rail's view is a placeholder, not a renderer and not a request.
    expect(
      within(screen.getByTestId('spec-rail-k20')).queryByTestId(
        'tag-sheet-renderer-k20',
      ),
    ).toBeNull();
    const chunkKeys = getSpecSheetPreview.mock.calls.map(
      (call) => (call[3] as string[]).length,
    );
    expect(chunkKeys.every((n) => n <= 6)).toBe(true);
    expect(getSpecSheetPreview).toHaveBeenCalledTimes(2);
  });

  it('shows an edited dot and greys a left-out page', async () => {
    getSpecSheet.mockResolvedValue({
      ...detail(),
      pages: detail().pages.map((p) =>
        p.key === 'k3'
          ? { ...p, edited: true }
          : p.key === 'k4'
            ? { ...p, hidden: true, number: null }
            : p,
      ),
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(
      within(screen.getByTestId('spec-rail-k3')).getByLabelText('Edited'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('spec-rail-k4').className).toMatch(/opacity-50/);
  });
});

describe('phone', () => {
  it('selecting leaves the canvas free; Properties opens a compact sheet on demand', async () => {
    mobile = true;
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    const canvas = await screen.findByTestId('live-canvas-k1');
    expect(canvas).toHaveAttribute('data-readonly', 'no');
    expect(screen.queryByRole('button', { name: 'Properties' })).toBeNull();

    fireEvent.click(within(canvas).getByText('select k1'));

    // The sheet stays shut, so it cannot cover the layer just picked.
    const button = await screen.findByRole('button', { name: 'Properties' });
    expect(screen.queryByRole('dialog')).toBeNull();

    vi.mocked(HTMLElement.prototype.scrollTo).mockClear();
    fireEvent.click(button);
    const dialog = await screen.findByRole('dialog');
    // The stack scrolls the selected layer to its top, above the sheet.
    expect(HTMLElement.prototype.scrollTo).toHaveBeenCalled();
    // The shared drawer's own bottom cap (80vh) must not survive: it is the one that applies.
    expect(dialog.className).toContain(
      'data-[vaul-drawer-direction=bottom]:max-h-[45dvh]',
    );
    expect(dialog.className).not.toContain(
      'data-[vaul-drawer-direction=bottom]:max-h-[80vh]',
    );
    expect(within(dialog).getByTestId('inspector')).toHaveAttribute(
      'data-layer',
      'logo',
    );
    expect(screen.getByTestId('live-canvas-k1')).toHaveAttribute(
      'data-readonly',
      'no',
    );
  });
});

describe('every page, pending saves, save status and the unload guard', () => {
  async function two() {
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout'],
      shouldAdvanceTime: true,
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    await screen.findByTestId('live-canvas-k1');
    await screen.findByTestId('live-canvas-k2');
  }

  it("sends another page's pending edit BEFORE applying to every page, and keeps it", async () => {
    await two();
    // Page B (k2) has an edit waiting for its second; then page A (k1) applies to every page.
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k2')).getByText('nudge k2'),
    );
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');
    fireEvent.click(
      screen.getByRole('radio', { name: 'Every page' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'move logo' }));

    await waitFor(() =>
      expect(applySpecSheetLayerToAll).toHaveBeenCalledTimes(1),
    );
    const firstSave = saveSpecSheetPageEdit.mock.calls.findIndex(
      (c) => c[3] === 'k2',
    );
    expect(firstSave).toBeGreaterThanOrEqual(0);
    expect(
      (saveSpecSheetPageEdit.mock.calls[firstSave][4] as { x_mm: number }[])[0]
        .x_mm,
    ).toBe(6);
    expect(
      saveSpecSheetPageEdit.mock.invocationCallOrder[firstSave],
    ).toBeLessThan(applySpecSheetLayerToAll.mock.invocationCallOrder[0]);
    // B's own copy survives the apply (it was sent, and is still what the page holds).
    expect(screen.getByTestId('live-canvas-k2')).toBeInTheDocument();
  });

  it('keeps "Not saved" while any page failed, retries it on the next flush, then says Saved', async () => {
    let k2Ok = false;
    saveSpecSheetPageEdit.mockImplementation(
      async (_p: string, _d: string, _s: string, key: string) => {
        if (key === 'k2' && !k2Ok) throw new Error('too large');
        return detail();
      },
    );
    await two();
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k2')).getByText('nudge k2'),
    );
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(await screen.findByText('Not saved')).toBeInTheDocument();

    // Page C saves; B is still failed, so the mark stays.
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    await waitFor(() =>
      expect(
        saveSpecSheetPageEdit.mock.calls.filter((c) => c[3] === 'k1'),
      ).toHaveLength(1),
    );
    expect(screen.getByText('Not saved')).toBeInTheDocument();
    expect(screen.queryByText('Saved')).toBeNull();

    // B can save now; the next flush retries it.
    k2Ok = true;
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(await screen.findByText('Saved')).toBeInTheDocument();
    expect(screen.queryByText('Not saved')).toBeNull();
  });

  it('guards the tab with beforeunload while a save is pending, and lets go when idle', async () => {
    const add = vi.spyOn(window, 'addEventListener') as unknown as {
      mock: { calls: unknown[][] };
      mockRestore: () => void;
    };
    const remove = vi.spyOn(window, 'removeEventListener') as unknown as {
      mock: { calls: unknown[][] };
      mockRestore: () => void;
    };
    await two();
    expect(add.mock.calls.some((c) => c[0] === 'beforeunload')).toBe(false);

    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('nudge k1'),
    );
    await waitFor(() =>
      expect(add.mock.calls.some((c) => c[0] === 'beforeunload')).toBe(true),
    );
    const handler = add.mock.calls.find(
      (c) => c[0] === 'beforeunload',
    )?.[1] as (e: Event) => void;
    const event = new Event('beforeunload', { cancelable: true });
    handler(event);
    expect(event.defaultPrevented).toBe(true);

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    await screen.findByText('Saved');
    await waitFor(() =>
      expect(remove.mock.calls.some((c) => c[0] === 'beforeunload')).toBe(true),
    );
    add.mockRestore();
    remove.mockRestore();
  });
});

describe('layers as the PDF reads them', () => {
  it('hands the designer layers with visible, rotation and z-index filled in (a missing visible is shown)', async () => {
    const bare = { ...LOGO } as Record<string, unknown>;
    delete bare.visible;
    delete bare.rotation_deg;
    delete bare.z_index;
    getSpecSheetPreview.mockImplementation(async (_p: string, _d: string, _s: string, keys: string[]) => {
      const preview = previewFor(keys);
      preview.doc.sheets.forEach((sheet) => {
        sheet.tags[0].layers = [bare] as never;
      });
      return preview;
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');

    expect(lastDocLayers).toHaveLength(1);
    expect(lastDocLayers[0]).toMatchObject({ id: 'logo', visible: true, locked: false, rotation_deg: 0, z_index: 0 });
  });
});

describe('a page that does not move under the pointer', () => {
  it('keeps a one-line page header whether or not the page actions show', async () => {
    renderReader();
    const page = await screen.findByTestId('spec-page-k29');
    const wrap = page.closest('[data-page-wrap]') as HTMLElement;
    const header = () => wrap.querySelector('[data-testid^="spec-sheet-bar-"]')!.parentElement as HTMLElement;
    // Hovering shows the page actions; if they could wrap the header, the page would slide
    // down under the pointer between the move and the press and the click would miss.
    expect(header().className).not.toContain('flex-wrap');
    expect(header().className).toContain('h-8');
    fireEvent.mouseEnter(wrap);
    const actions = await screen.findByTestId('spec-sheet-leave-out-k29');
    expect(header().className).not.toContain('flex-wrap');
    expect(header().className).toContain('h-8');
    expect(actions.parentElement!.className).toContain('absolute');
    fireEvent.mouseLeave(wrap);
  });

  it('the toolbar holds the SAME format bar in every selection state (only hidden), so its height never changes', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    // Nothing selected: the real bar, invisible and out of the accessibility tree.
    const hidden = document.querySelector(
      '[role="group"][aria-label="Text formatting"]',
    ) as HTMLElement;
    expect(hidden).not.toBeNull();
    expect(hidden.className).toContain('invisible');
    const shape = (el: HTMLElement) =>
      Array.from(el.querySelectorAll('*')).map((n) => n.tagName).join(',');
    const before = shape(hidden);

    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    const shown = await screen.findByRole('group', { name: 'Text formatting' });
    expect(shown.className).not.toContain('invisible');
    expect(shape(shown)).toBe(before);
  });
});

describe('SPEC-SHEET-EDITOR-UX: full screen, folding panels, Apply to, templates', () => {
  it('Full screen lifts the editor into the shared focus overlay; Escape brings it back', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(document.querySelector('[data-dk-focus-mode]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Full screen spec sheet' }));

    const overlay = document.querySelector('[data-dk-focus-mode]') as HTMLElement;
    expect(overlay).not.toBeNull();
    // The page stack, the rail and the toolbar are all inside the overlay.
    expect(within(overlay).getByTestId('spec-sheet-stack')).toBeInTheDocument();
    expect(within(overlay).getByTestId('spec-sheet-rail')).toBeInTheDocument();
    expect(
      within(overlay).getByRole('button', { name: 'Exit full screen spec sheet' }),
    ).toHaveAttribute('aria-pressed', 'true');

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() =>
      expect(document.querySelector('[data-dk-focus-mode]')).toBeNull(),
    );
  });

  it('a live page keeps its canvas when full screen toggles (no remount)', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    const before = await screen.findByTestId('live-canvas-k1');
    fireEvent.click(screen.getByRole('button', { name: 'Full screen spec sheet' }));
    expect(screen.getByTestId('live-canvas-k1')).toBe(before);
  });

  it('the page rail folds away and comes back', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.getByTestId('spec-sheet-rail')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Hide Pages' }));
    expect(screen.queryByTestId('spec-sheet-rail')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Show Pages' }));
    expect(screen.getByTestId('spec-sheet-rail')).toBeInTheDocument();
  });

  it('the Inspector folds away and comes back, keeping the selection', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');

    fireEvent.click(screen.getByRole('button', { name: 'Hide Inspector' }));
    expect(screen.queryByTestId('inspector')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Show Inspector' }));
    expect(screen.getByTestId('inspector')).toHaveAttribute('data-layer', 'logo');
  });

  it('Apply to is a two-option segmented control, This page by default, no long caption', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('select k1'),
    );
    await screen.findByTestId('inspector');

    const group = screen.getByRole('group', { name: 'Apply to' });
    const options = within(group).getAllByRole('radio');
    expect(options.map((o) => o.textContent)).toEqual(['This page', 'Every page']);
    expect(within(group).getByRole('radio', { name: 'This page' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.queryByText(/each becomes an edited page/)).toBeNull();

    fireEvent.click(within(group).getByRole('radio', { name: 'Every page' }));
    expect(within(group).getByRole('radio', { name: 'Every page' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    // Clicking the chosen option again does not leave the control with nothing picked.
    fireEvent.click(within(group).getByRole('radio', { name: 'Every page' }));
    expect(within(group).getByRole('radio', { name: 'Every page' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('Templates opens the template picker for this sheet and saves the picks', async () => {
    listSpecSheets.mockResolvedValue({
      items: [],
      sources: [],
      templates: {
        cover: [{ id: 'tc', name: 'Cover', width_mm: 338.7, height_mm: 190.5 }],
        page: [
          { id: 'tp', name: 'Page', width_mm: 338.7, height_mm: 190.5 },
          { id: 'tp2', name: 'Project Page Default Template', width_mm: 338.7, height_mm: 190.5 },
        ],
      },
      defaults: {
        source: null,
        cover_template_id: null,
        page_template_id: null,
        single_page_template_id: null,
      },
      create_disabled_reason: null,
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');

    fireEvent.keyDown(screen.getByRole('button', { name: 'Spec sheet actions' }), {
      key: 'Enter',
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Templates' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Pick templates' })).toBeInTheDocument();
    await waitFor(() => expect(listSpecSheets).toHaveBeenCalled());

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalledTimes(1));
    expect(updateSpecSheet).toHaveBeenCalledWith('p1', 'd1', 'sheet-1', {
      cover_template_id: 'tc',
      page_template_id: 'tp',
      single_page_template_id: null,
    });
  });

  it('Escape that cancels an Area edit does not also leave full screen', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    fireEvent.click(screen.getByRole('button', { name: 'Full screen spec sheet' }));
    fireEvent.click(
      within(screen.getByTestId('live-canvas-k1')).getByText('double-click area k1'),
    );
    const box = await screen.findByRole('textbox', { name: 'Area' });
    fireEvent.keyDown(box, { key: 'Escape' });
    await waitFor(() =>
      expect(screen.queryByRole('textbox', { name: 'Area' })).toBeNull(),
    );
    expect(document.querySelector('[data-dk-focus-mode]')).not.toBeNull();
  });

  it('after a template switch an unedited LIVE page redraws from the new template, no reload', async () => {
    listSpecSheets.mockResolvedValue({
      items: [],
      sources: [],
      templates: {
        cover: [{ id: 'tc', name: 'Cover', width_mm: 338.7, height_mm: 190.5 }],
        page: [{ id: 'tp', name: 'Page', width_mm: 338.7, height_mm: 190.5 }],
      },
      defaults: {
        source: null,
        cover_template_id: null,
        page_template_id: null,
        single_page_template_id: null,
      },
      create_disabled_reason: null,
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1']);
    const before = await screen.findByTestId('live-canvas-k1');
    expect(before).toHaveAttribute('data-layers', 'logo,area,desc,desc0');

    // The server now draws every unedited page from the other template.
    const switched = {
      ...detail(),
      templates: {
        ...detail().templates,
        page: { id: 'tp2', name: 'Item with accessories', version_no: 3 },
      },
    };
    updateSpecSheet.mockResolvedValue(switched);
    getSpecSheet.mockResolvedValue(switched);
    getSpecSheetPreview.mockImplementation(
      async (_p: string, _d: string, _s: string, keys: string[]) => {
        const out = previewFor(keys);
        for (const sheet of out.doc.sheets)
          sheet.tags[0].layers = [{ ...LOGO, id: 'title' }] as never;
        return out;
      },
    );

    fireEvent.keyDown(screen.getByRole('button', { name: 'Spec sheet actions' }), {
      key: 'Enter',
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Templates' }));
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(listSpecSheets).toHaveBeenCalled());
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalledTimes(1));

    await waitFor(() =>
      expect(screen.getByTestId('live-canvas-k1')).toHaveAttribute('data-layers', 'title'),
    );
  });

  it('a template switch saves no page edit (no pages/*/edit request), and switching back restores the original layers', async () => {
    listSpecSheets.mockResolvedValue({
      items: [],
      sources: [],
      templates: {
        cover: [{ id: 'tc', name: 'Cover', width_mm: 338.7, height_mm: 190.5 }],
        page: [
          { id: 'tp', name: 'Page', width_mm: 338.7, height_mm: 190.5 },
          { id: 'tp2', name: 'Single item', width_mm: 338.7, height_mm: 190.5 },
        ],
      },
      defaults: {
        source: null,
        cover_template_id: null,
        page_template_id: null,
        single_page_template_id: null,
      },
      create_disabled_reason: null,
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    // The cover and an item page are live, as on a 2-page sheet.
    report(['cover', 'k1']);
    expect(await screen.findByTestId('live-canvas-k1')).toHaveAttribute(
      'data-layers',
      'logo,area,desc,desc0',
    );
    await screen.findByTestId('live-canvas-cover');

    let page = 'tp';
    const current = () => ({
      ...detail(),
      templates: {
        ...detail().templates,
        page:
          page === 'tp'
            ? { id: 'tp', name: 'Page', version_no: 1 }
            : { id: 'tp2', name: 'Single item', version_no: 3 },
      },
    });
    updateSpecSheet.mockImplementation(async (...args: unknown[]) => {
      page = (args[3] as { page_template_id: string }).page_template_id;
      return current();
    });
    getSpecSheet.mockImplementation(async () => current());
    getSpecSheetPreview.mockImplementation(
      async (_p: string, _d: string, _s: string, keys: string[]) => {
        const out = previewFor(keys);
        if (page === 'tp2')
          for (const sheet of out.doc.sheets)
            sheet.tags[0].layers = [{ ...LOGO, id: 'title' }] as never;
        return out;
      },
    );

    const switchTo = async (name: string) => {
      fireEvent.keyDown(screen.getByRole('button', { name: 'Spec sheet actions' }), {
        key: 'Enter',
      });
      fireEvent.click(await screen.findByRole('menuitem', { name: 'Templates' }));
      const dialog = await screen.findByRole('dialog');
      await waitFor(() => expect(listSpecSheets).toHaveBeenCalled());
      const select = within(dialog).getAllByRole('combobox')[1];
      fireEvent.click(select);
      fireEvent.click(await screen.findByRole('option', { name: new RegExp(`^${name}`) }));
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
      await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    };

    await switchTo('Single item');
    await waitFor(() =>
      expect(screen.getByTestId('live-canvas-k1')).toHaveAttribute('data-layers', 'title'),
    );
    // Past the autosave delay: nothing was written for any page.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1300));
    });
    expect(saveSpecSheetPageEdit).not.toHaveBeenCalled();
    expect(screen.getByTestId('spec-sheet-save-state').textContent).toBe('');

    await switchTo('Page');
    await waitFor(() =>
      expect(screen.getByTestId('live-canvas-k1')).toHaveAttribute('data-layers', 'logo,area,desc,desc0'),
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1300));
    });
    expect(saveSpecSheetPageEdit).not.toHaveBeenCalled();
  }, 15000);

  it('a page whose chunk was cached BEFORE a template switch draws the new template when it comes back into view', async () => {
    listSpecSheets.mockResolvedValue({
      items: [],
      sources: [],
      templates: {
        cover: [{ id: 'tc', name: 'Cover', width_mm: 338.7, height_mm: 190.5 }],
        page: [{ id: 'tp', name: 'Page', width_mm: 338.7, height_mm: 190.5 }],
      },
      defaults: {
        source: null,
        cover_template_id: null,
        page_template_id: null,
        single_page_template_id: null,
      },
      create_disabled_reason: null,
    });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    // k13 is read (its chunk is cached with the old template), then the reader moves away.
    report(['k13']);
    expect(await screen.findByTestId('live-canvas-k13')).toHaveAttribute(
      'data-layers',
      'logo,area,desc,desc0',
    );
    report(['k1']);
    await screen.findByTestId('live-canvas-k1');
    await waitFor(() => expect(screen.queryByTestId('live-canvas-k13')).toBeNull());

    const switched = {
      ...detail(),
      templates: {
        ...detail().templates,
        page: { id: 'tp2', name: 'Item with accessories', version_no: 3 },
      },
    };
    updateSpecSheet.mockResolvedValue(switched);
    getSpecSheet.mockResolvedValue(switched);
    // The new template's previews answer slowly, so a stale cached chunk would draw first.
    getSpecSheetPreview.mockImplementation(
      async (_p: string, _d: string, _s: string, keys: string[]) => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        const out = previewFor(keys);
        for (const sheet of out.doc.sheets)
          sheet.tags[0].layers = [{ ...LOGO, id: 'title' }] as never;
        return out;
      },
    );
    fireEvent.keyDown(screen.getByRole('button', { name: 'Spec sheet actions' }), {
      key: 'Enter',
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Templates' }));
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(listSpecSheets).toHaveBeenCalled());
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId('live-canvas-k1')).toHaveAttribute('data-layers', 'title'),
    );

    // Back to k13: never seeded from the old template's cached chunk.
    report(['k13']);
    await waitFor(() =>
      expect(screen.getByTestId('live-canvas-k13')).toHaveAttribute('data-layers', 'title'),
    );
    const seen: string[] = [];
    const watch = setInterval(() => {
      const el = screen.queryByTestId('live-canvas-k13');
      if (el) seen.push(el.getAttribute('data-layers') ?? '');
    }, 5);
    await new Promise((resolve) => setTimeout(resolve, 150));
    clearInterval(watch);
    expect(seen.every((v) => v === 'title')).toBe(true);
  });

  it('a phone has no toolbar format bar (the Properties sheet formats text), so the toolbar has no blank rows', async () => {
    mobile = true;
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(
      document.querySelector('[role="group"][aria-label="Text formatting"]'),
    ).toBeNull();
  });

  it('the "Press Esc" hint is hidden on a touch screen', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    fireEvent.click(screen.getByRole('button', { name: 'Full screen spec sheet' }));
    const hint = screen.getByText('Press Esc to exit full screen');
    expect(hint.className).toContain('pointer-coarse:hidden');
  });

  it('a viewer who cannot edit gets no Templates action', async () => {
    getSpecSheet.mockResolvedValue({ ...detail(), can_edit: false });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.queryByRole('menuitem', { name: 'Templates' })).toBeNull();
    expect(screen.queryByText('Templates')).toBeNull();
  });

});
