/**
 * SPEC-SHEET-PARITY-B2 v3 fix round on the spec sheet reader. Written test-FIRST.
 *
 * - B1 (AC-C6.2): Manage fonts (toolbar format row and Inspector) only with
 *   `dealer_kit.library.manage`, the server's gate on font upload / rename / delete. Both open the
 *   ONE Brand fonts dialog.
 * - F2: the save state sits outside the toolbar's scrolling tools, pinned at the right, so a wide
 *   contextual group never pushes it off screen; the tools still scroll inside the row.
 * - F4: right after Remove page the side bar names a page that is there ("Page N of M"), never "-".
 *
 * Harness as in `SpecSheetReader.v3.test.tsx` (canvas stand-in, Inspector stand-in that offers
 * Manage fonts when handed `onUploadFont`, as the real one does).
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
  InspectorPanel: ({ layer, onUploadFont }: { layer: { id: string } | null; onUploadFont?: () => void }) => (
    <div data-testid="inspector" data-layer={layer?.id ?? ''}>
      {onUploadFont && (
        <button type="button" onClick={onUploadFont}>
          Manage fonts
        </button>
      )}
    </div>
  ),
}));
const granted = vi.hoisted(() => ({ slugs: new Set<string>(['dealer_kit.library.manage']) }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.slugs.has(slug),
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

// ---- B1 ------------------------------------------------------------------------------------------

describe('B1 Manage fonts needs dealer_kit.library.manage (AC-C6.2)', () => {
  it('with it: the format row and the Inspector both offer Manage fonts, opening the one dialog', async () => {
    granted.slugs = new Set(['dealer_kit.library.manage']);
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await selectOn('k1', 'logo');
    const format = await within(row()).findByRole('group', { name: 'Text formatting' });
    expect(within(format).getByRole('button', { name: 'Manage fonts' })).toBeInTheDocument();
    fireEvent.click(within(screen.getAllByTestId('inspector')[0]).getByRole('button', { name: 'Manage fonts' }));
    expect(await screen.findAllByRole('dialog', { name: 'Brand fonts' })).toHaveLength(1);
  });

  it('without it: no Manage fonts in the format row nor in the Inspector', async () => {
    granted.slugs = new Set();
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await selectOn('k1', 'logo');
    await within(row()).findByRole('group', { name: 'Text formatting' });
    expect(screen.queryByRole('button', { name: 'Manage fonts' })).toBeNull();
  });
});

// ---- F2 ------------------------------------------------------------------------------------------

describe('F2 the save state stays in view', () => {
  it('sits outside the scrolling tools, at the right of the row; the tools scroll inside the row', async () => {
    granted.slugs = new Set(['dealer_kit.library.manage']);
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await selectOn('k1', 'tbl');
    const tools = within(row()).getByTestId('canvas-toolbar-tools');
    expect(tools.className.split(/\s+/)).toContain('overflow-x-auto');
    expect(tools.contains(within(row()).getByRole('button', { name: 'Add Text' }))).toBe(true);
    expect(tools.contains(within(row()).getByRole('button', { name: /^header row$/i }))).toBe(true);
    const save = screen.getByTestId('spec-sheet-save-state');
    expect(row().contains(save)).toBe(true);
    expect(tools.contains(save)).toBe(false);
  });
});

// ---- F4 ------------------------------------------------------------------------------------------

describe('F4 the page counter right after Remove page', () => {
  it('names the page that took its place, never "-"', async () => {
    granted.slugs = new Set(['dealer_kit.library.manage']);
    updateSpecSheet.mockResolvedValue(detail(['k3']));
    renderReader();
    await screen.findByTestId('spec-page-k29');
    fireEvent.click(within(screen.getByTestId('spec-rail-k3')).getByRole('button', { name: /CODE-k3/ }));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(screen.getByTestId('spec-rail-page-of').textContent).toBe('Page 4 of 30');
    openMenu(within(screen.getByTestId('spec-rail-k3')).getByRole('button', { name: /page options/i }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove page' }));
    await waitFor(() => expect(screen.queryByTestId('spec-rail-k3')).toBeNull());
    expect(screen.getByTestId('spec-rail-page-of').textContent).toBe('Page 4 of 29');
  });
});
