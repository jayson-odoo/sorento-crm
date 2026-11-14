/**
 * SPEC-SHEET-PARITY-B2 v3 editor (UAC `spec-sheet-editor-v3-14nov-acceptance-criteria.md`), on the
 * spec sheet reader. Written test-FIRST.
 *
 * C1 one toolbar row: the separate page bar is gone (no Previous / Next page, no "N of M"); zoom
 * out, zoom %, zoom in, Fit width, Full screen and the save state sit in the ONE toolbar row
 * (`spec-sheet-toolbar-row`, the shared CanvasToolbar); Delete / Duplicate / Group / Ungroup live in
 * its "More actions" menu, not as visible buttons; a selected text layer brings its format controls
 * (with ALL CAPS) into the same row, a selected table brings the table actions instead.
 *
 * C2 Pages side bar: "Page N of M" under the thumbnails (`spec-rail-page-of`); every non-cover
 * thumbnail has a "Page options" menu and a right-click menu with "Remove page" (the existing
 * `hidden` flag, the same PATCH the old Leave out button made); removed pages leave the thumbnails
 * and the page stack and are listed under "Removed pages (N)" (`spec-rail-removed`) with "Put
 * back"; the Leave out button above each page is gone.
 *
 * The designer canvas is stood in for by a fake that exposes selection per layer and the
 * controller handle the toolbar and inspector act through (as in SpecSheetReader.inline.test).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

type Observer = { callback: (entries: unknown[]) => void; targets: Set<Element> };
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
(globalThis as { IntersectionObserver: unknown }).IntersectionObserver = FakeIntersectionObserver;

function report(visibleKeys: string[]) {
  act(() => {
    for (const observer of observers) {
      const entries = [...observer.targets]
        .filter((el) => el.getAttribute('data-page-key'))
        .map((el) => ({
          target: el,
          isIntersecting: visibleKeys.includes(el.getAttribute('data-page-key') as string),
        }));
      if (entries.length) observer.callback(entries);
    }
  });
}

// ---- mocks -------------------------------------------------------------------------------------

const getSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
const saveSpecSheetPageEdit = vi.fn();
const updateSpecSheet = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/services/specSheetService', () => ({
  listSpecSheets: vi.fn(async () => []),
  createSpecSheet: vi.fn(),
  getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
  updateSpecSheet: (...a: unknown[]) => updateSpecSheet(...a),
  getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
  getSpecSheetPageDesign: vi.fn(),
  getSpecSheetPageImages: vi.fn(async () => ({ images: {}, assets: {} })),
  saveSpecSheetPageEdit: (...a: unknown[]) => saveSpecSheetPageEdit(...a),
  applySpecSheetLayerToAll: vi.fn(),
  addSpecSheetLayerToAll: vi.fn(),
  queueSpecSheetPdf: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1/spec-sheet/sheet-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ projectId: 'p1', documentId: 'd1', sheetId: 'sheet-1' }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));
vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => undefined),
  ensureSeedFontsLoaded: vi.fn(async () => undefined),
}));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: { onCommitted?: () => void }) => ({
    pending: null,
    isPending: false,
    isBlocked: false,
    start: () => input.onCommitted?.(),
    cancel: () => undefined,
    countdown: null,
  }),
}));
let mobile = false;
vi.mock('@/hooks/use-mobile', () => ({ useIsMobile: () => mobile }));

vi.mock('@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer', () => ({
  default: ({ doc }: { doc: { sheets: { tags: { request_tag_id: string }[] }[] } }) => (
    <div data-testid={`tag-sheet-renderer-${doc?.sheets?.[0]?.tags?.[0]?.request_tag_id}`} />
  ),
}));
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings', () => ({
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
}));
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/InspectorPanel', () => ({
  InspectorPanel: ({ layer }: { layer: { id: string } | null }) => (
    <div data-testid="inspector" data-layer={layer?.id ?? ''} />
  ),
}));

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
    controllerRef: { current: unknown };
  };
};
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor', () => ({
  TagCanvasEditor: function FakeEditor(props: FakeProps) {
    const key = props.docId.split(':').slice(1).join(':');
    const [layers, setLayers] = React.useState(props.doc.layers);
    const latest = React.useRef(layers);
    latest.current = layers;
    const hostLayers = props.embedded.layers;
    React.useEffect(() => {
      if (hostLayers && hostLayers !== latest.current) setLayers(hostLayers);
    }, [hostLayers]);
    React.useEffect(() => {
      props.onLayersChange(layers);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [layers]);
    const selected = props.embedded.selectedLayerId;
    props.embedded.controllerRef.current = {
      updateLayer: (id: string, changes: Record<string, unknown>) =>
        setLayers(latest.current.map((l) => (l.id === id ? { ...l, ...changes } : l))),
      updateLayerProps: (id: string, changes: Record<string, unknown>) =>
        setLayers(
          latest.current.map((l) => (l.id === id ? { ...l, props: { ...(l.props as object), ...changes } } : l)),
        ),
      deleteSelected: () => setLayers(latest.current.filter((l) => l.id !== selected)),
      duplicateSelected: () => undefined,
      groupSelected: () => undefined,
      ungroupSelected: () => undefined,
      addLayer: () => undefined,
    };
    return (
      <div
        data-testid={`live-canvas-${key}`}
        data-active={props.embedded.active ? 'yes' : 'no'}
        data-layers={layers.map((l) => l.id).join(',')}
        data-json={JSON.stringify(layers)}
      >
        {layers.map((l) => (
          <button key={String(l.id)} type="button" onClick={() => props.embedded.onSelect(String(l.id))}>
            {`select ${String(l.id)} ${key}`}
          </button>
        ))}
      </div>
    );
  },
}));

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
  props: { kind: 'text', text: 'Sorento', fontFamily: 'DM Sans', fontSize: 12, fontWeight: 400, color: '#000000', align: 'left' },
};
const SIDE = { color: '#000000', width_mm: 0.2 };
const TABLE = {
  id: 'tbl',
  type: 'table',
  x_mm: 200,
  y_mm: 20,
  width_mm: 60,
  height_mm: 12,
  rotation_deg: 0,
  z_index: 2,
  visible: true,
  props: {
    kind: 'table',
    columns: [{ width_mm: 30 }, { width_mm: 30 }],
    rows: [{ height_mm: 6 }, { height_mm: 6 }],
    cells: [
      [{ text: 'REF', border: { top: SIDE } }, { text: '{{doc.ref}}' }],
      [{ text: 'Code' }, { text: '{{product.code}}' }],
    ],
    fontFamily: 'DM Sans',
    fontSize: 10,
    color: '#000000',
    align: 'left',
    verticalAlign: 'middle',
  },
};

type Page = Record<string, unknown> & { key: string; hidden: boolean };

function detail(hidden: string[] = []) {
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
    pages: KEYS.map((key, i): Page => ({
      key,
      number: hidden.includes(key) ? null : key === 'cover' ? 1 : i + 1,
      code: key === 'cover' ? '' : `CODE-${key}`,
      name: key === 'cover' ? 'Cover' : `Product ${key}`,
      brand: '',
      area: '',
      area_default: '',
      comment: '',
      marker: '',
      hidden: hidden.includes(key),
      picked: [],
      accessories: [],
      description: '',
      accessory_descriptions: {},
      spec_sheet_description_default: '',
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
      imposition: { preset: 'custom', page_width_mm: 338.7, page_height_mm: 190.5, bleed_mm: 0, gap_mm: 0 },
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
            layers: [LOGO, TABLE],
          },
        ],
      })),
    },
    resolvedData: Object.fromEntries(keys.map((k) => [k, { code: k, images: [], parts: [] }])),
    assets: {},
    images: {},
    fonts: [],
    version: 1,
    hidden: [],
    page_size: { width_mm: 338.7, height_mm: 190.5 },
  };
}

function renderReader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpecSheetReader projectId="p1" documentId="d1" sheetId="sheet-1" />
    </QueryClientProvider>,
  );
}

const row = () => screen.getByTestId('spec-sheet-toolbar-row');

/** Radix menus open on pointerdown (button 0), not on click. */
function openMenu(trigger: HTMLElement) {
  fireEvent.pointerDown(trigger, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
}

function moreButton(): HTMLElement {
  return within(row()).getAllByRole('button', { name: /^More( actions)?$/ })[0];
}

async function selectOn(key: string, layerId: string) {
  report([key]);
  const canvas = await screen.findByTestId(`live-canvas-${key}`);
  fireEvent.pointerDown(screen.getByTestId(`spec-page-${key}`));
  fireEvent.click(within(canvas).getByText(`select ${layerId} ${key}`));
  await screen.findByTestId('inspector');
  return canvas;
}

/** The rows sent with the LAST sheet PATCH, by page key. */
function lastPatchedRows(): Record<string, { hidden: boolean }> {
  const body = updateSpecSheet.mock.calls.at(-1)![3] as { rows: { key: string; hidden: boolean }[] };
  return Object.fromEntries(body.rows.map((r) => [r.key, r]));
}

beforeEach(() => {
  observers.length = 0;
  mobile = false;
  getSpecSheet.mockReset().mockResolvedValue(detail());
  updateSpecSheet.mockReset().mockResolvedValue(detail());
  saveSpecSheetPageEdit.mockReset().mockResolvedValue(detail());
  getSpecSheetPreview
    .mockReset()
    .mockImplementation(async (_p: string, _d: string, _s: string, keys: string[]) => previewFor(keys));
});

afterEach(() => {
  vi.useRealTimers();
});

// ---- C1 ------------------------------------------------------------------------------------------

describe('C1 one toolbar row', () => {
  it('AC-C1.1/C1.2: no page bar: no Previous / Next page buttons and no "N of M" counter', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.queryByRole('button', { name: 'Previous page' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Next page' })).toBeNull();
    expect(screen.queryByTestId('spec-sheet-page-of')).toBeNull();
    expect(within(row()).queryByText(/^\s*\d+\s+of\s+\d+\s*$/)).toBeNull();
  });

  it('AC-C1.1: zoom out, zoom %, zoom in, Fit width, Full screen and the save state are in the one row', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    const toolbar = row();
    expect(within(toolbar).getByRole('button', { name: /^zoom out$/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: /^zoom in$/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: /^fit (width|to view)$/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: /full screen/i })).toBeInTheDocument();
    expect(within(toolbar).getByText(/^\d+%$/)).toBeInTheDocument();
    expect(toolbar.contains(screen.getByTestId('spec-sheet-save-state'))).toBe(true);
  });

  it('AC-C1.1: a viewer who cannot edit still zooms, fits and goes full screen, with no add tools', async () => {
    getSpecSheet.mockResolvedValue({ ...detail(), can_edit: false });
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.getByRole('button', { name: /^zoom out$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^zoom in$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^fit (width|to view)$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /full screen/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add Text' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Previous page' })).toBeNull();
  });

  it('AC-C1.3: Delete, Duplicate, Group, Ungroup are not visible buttons; they are in the More menu', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    for (const name of ['Delete', 'Duplicate', 'Group', 'Ungroup']) {
      expect(screen.queryByRole('button', { name }), name).toBeNull();
    }
    openMenu(moreButton());
    const menu = await screen.findByRole('menu');
    for (const name of ['Delete', 'Duplicate', 'Group', 'Ungroup']) {
      expect(within(menu).getByRole('menuitem', { name: new RegExp(`^${name}`) }), name).toBeInTheDocument();
    }
  });

  it('AC-C1.3: More > Delete removes the selected layer on its page', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    const canvas = await selectOn('k1', 'logo');
    openMenu(moreButton());
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Delete/ }));
    await waitFor(() => expect(canvas.getAttribute('data-layers')).toBe('tbl'));
  });

  it('AC-C1.4: nothing selected: no text format controls and no table actions', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.queryByRole('group', { name: 'Text formatting' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Header row$/ })).toBeNull();
  });

  it('AC-C1.4: a selected text layer brings font, size, bold, italic, align and ALL CAPS into the same row', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await selectOn('k1', 'logo');
    const format = await within(row()).findByRole('group', { name: 'Text formatting' });
    for (const name of [/^Bold$/, /^Italic$/, /^Align left$/, /all caps/i]) {
      expect(within(format).getByRole('button', { name }), String(name)).toBeInTheDocument();
    }
    expect(within(row()).queryByRole('button', { name: /^Header row$/ })).toBeNull();
  });

  it('AC-C5.2: ALL CAPS on a text layer sets props.uppercase and leaves the text as typed', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    const canvas = await selectOn('k1', 'logo');
    const format = await within(row()).findByRole('group', { name: 'Text formatting' });
    fireEvent.click(within(format).getByRole('button', { name: /all caps/i }));
    await waitFor(() => {
      const logo = (JSON.parse(canvas.getAttribute('data-json')!) as typeof LOGO[]).find((l) => l.id === 'logo')!;
      expect((logo.props as Record<string, unknown>).uppercase).toBe(true);
      expect(logo.props.text).toBe('Sorento');
    });
  });

  it('AC-C1.4: a selected table brings + Row, + Column, Merge, Header row, Insert field into the row instead', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await selectOn('k1', 'tbl');
    const toolbar = row();
    for (const name of [/(\+ ?|add )row/i, /(\+ ?|add )column/i, /^merge/i, /^header row$/i, /^insert field$/i]) {
      expect(within(toolbar).getAllByRole('button', { name }).length, String(name)).toBeGreaterThan(0);
    }
    expect(screen.queryByRole('group', { name: 'Text formatting' })).toBeNull();
  });

  it('AC-C4.1: Header row in the row turns the table header row on', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    const canvas = await selectOn('k1', 'tbl');
    fireEvent.click(within(row()).getByRole('button', { name: /^header row$/i }));
    await waitFor(() => {
      const table = (JSON.parse(canvas.getAttribute('data-json')!) as typeof TABLE[]).find((l) => l.id === 'tbl')!;
      expect((table.props as Record<string, unknown>).headerRow).toBe(true);
    });
  });
});

// ---- C2 ------------------------------------------------------------------------------------------

describe('C2 Pages side bar: navigation, Remove page, Removed pages', () => {
  it('AC-C2.1: reads "Page N of M" under the thumbnails and follows the clicked page', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    fireEvent.click(within(screen.getByTestId('spec-rail-k3')).getByRole('button', { name: /CODE-k3/ }));
    fireEvent.scroll(screen.getByTestId('spec-sheet-stack'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    const counter = screen.getByTestId('spec-rail-page-of');
    expect(screen.getByTestId('spec-sheet-rail').contains(counter) || counter.closest('[data-testid="spec-sheet-pages-panel"]')).toBeTruthy();
    expect(counter.textContent).toMatch(/^Page 4 of 30$/);
  });

  it('AC-C2.2: a thumbnail "Page options" menu offers Remove page, which saves hidden: true for that page', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    openMenu(within(screen.getByTestId('spec-rail-k3')).getByRole('button', { name: /page options/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove page' }));
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalled());
    const rows = lastPatchedRows();
    expect(rows.k3.hidden).toBe(true);
    expect(rows.k2.hidden).toBe(false);
  });

  it('AC-C2.2: right-click on a thumbnail offers Remove page too', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    fireEvent.contextMenu(within(screen.getByTestId('spec-rail-k5')).getByRole('button', { name: /CODE-k5/ }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove page' }));
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalled());
    expect(lastPatchedRows().k5.hidden).toBe(true);
  });

  it('AC-C2.2: the cover has no Remove page', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    const cover = screen.getByTestId('spec-rail-cover');
    expect(within(cover).queryByRole('button', { name: /page options/i })).toBeNull();
    fireEvent.contextMenu(within(cover).getByRole('button', { name: /Cover/ }));
    expect(screen.queryByRole('menuitem', { name: 'Remove page' })).toBeNull();
  });

  it('AC-C2.2/C2.3: a removed page leaves the thumbnails and the stack and is listed under "Removed pages (N)"', async () => {
    getSpecSheet.mockResolvedValue(detail(['k4']));
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.queryByTestId('spec-rail-k4')).toBeNull();
    expect(screen.queryByTestId('spec-page-k4')).toBeNull();
    const removed = screen.getByTestId('spec-rail-removed');
    expect(removed).toHaveTextContent('Removed pages (1)');
    expect(removed).toHaveTextContent('CODE-k4');
    expect(screen.getByTestId('spec-rail-page-of').textContent).toMatch(/of 29$/);
  });

  it('AC-C2.3: Put back clears the flag', async () => {
    getSpecSheet.mockResolvedValue(detail(['k4']));
    renderReader();
    await screen.findByTestId('spec-page-k29');
    fireEvent.click(within(screen.getByTestId('spec-rail-removed')).getByRole('button', { name: /Put back/ }));
    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalled());
    expect(lastPatchedRows().k4.hidden).toBe(false);
  });

  it('AC-C2.3: no removed pages, no Removed pages section', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.queryByTestId('spec-rail-removed')).toBeNull();
  });

  it('AC-C2.4: the Leave out / Put back button above each page is gone', async () => {
    renderReader();
    const page = await screen.findByTestId('spec-page-k5');
    const wrap = page.closest('[data-page-wrap]') as HTMLElement;
    fireEvent.mouseEnter(wrap);
    expect(within(wrap).queryByRole('button', { name: /Leave out|Put back/ })).toBeNull();
    expect(screen.queryByTestId('spec-sheet-leave-out-k5')).toBeNull();
  });

  it('AC-C2.5: on a phone the page strip offers Remove page and the Removed pages list', async () => {
    mobile = true;
    getSpecSheet.mockResolvedValue(detail(['k4']));
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.getByTestId('spec-rail-removed')).toHaveTextContent('Removed pages (1)');
    openMenu(within(screen.getByTestId('spec-rail-k3')).getByRole('button', { name: /page options/i }));
    expect(await screen.findByRole('menuitem', { name: 'Remove page' })).toBeInTheDocument();
  });
});

// ---- C7 (reader) -----------------------------------------------------------------------------------

describe('C7 keyboard Delete: the page holding the selection takes the keys', () => {
  it('selecting a layer on a page marks that page active (its shortcuts are live)', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['k1', 'k2']);
    await screen.findByTestId('live-canvas-k2');
    fireEvent.pointerDown(screen.getByTestId('spec-page-k2'));
    fireEvent.click(within(screen.getByTestId('live-canvas-k2')).getByText('select logo k2'));
    await waitFor(() => expect(screen.getByTestId('live-canvas-k2').getAttribute('data-active')).toBe('yes'));
    expect(screen.getByTestId('live-canvas-k1').getAttribute('data-active')).toBe('no');
  });
});
