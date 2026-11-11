/**
 * SPEC-SHEET-DESIGNER-PARITY B5: the Export control offers PDF and PowerPoint. Choosing
 * PowerPoint queues the export with format `pptx`; PDF keeps format `pdf`. Written test-FIRST.
 *
 * Contract assumption: the existing service function takes the format as a 4th argument,
 * `queueSpecSheetPdf(projectId, documentId, sheetId, format)` with `'pdf' | 'pptx'`.
 * The control may be a menu (trigger button named "Export", items "PDF" / "PowerPoint") or two
 * buttons; the helper below accepts either.
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
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

// ---- a controllable IntersectionObserver -------------------------------------------------------

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

/** Tell every observer which page keys are in view; every other observed page is out of view. */
function report(visibleKeys: string[]) {
  act(() => {
    for (const observer of observers) {
      const entries = [...observer.targets]
        .filter((el) => el.getAttribute('data-page-key'))
        .map((el) => ({
          target: el,
          isIntersecting: visibleKeys.includes(
            el.getAttribute('data-page-key') as string,
          ),
          intersectionRatio: visibleKeys.includes(
            el.getAttribute('data-page-key') as string,
          )
            ? 1
            : 0,
        }));
      if (entries.length) observer.callback(entries);
    }
  });
}

// ---- mocks ---------------------------------------------------------------------------------------

const queueSpecSheetPdf = vi.fn();
const getSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
const updateSpecSheet = vi.fn();
const getSpecSheetPageImages = vi.fn();
vi.mock(
  '@/app/(protected)/project-sales/_shared/services/specSheetService',
  () => ({
    listSpecSheets: vi.fn(),
    createSpecSheet: vi.fn(),
    getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
    updateSpecSheet: (...a: unknown[]) => updateSpecSheet(...a),
    getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
    getSpecSheetPageDesign: vi.fn(),
    getSpecSheetPageImages: (...a: unknown[]) => getSpecSheetPageImages(...a),
    saveSpecSheetPageEdit: vi.fn(),
    queueSpecSheetPdf: (...a: unknown[]) => queueSpecSheetPdf(...a),
  }),
);

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () =>
    '/project-sales/p1/quotation-documents/d1/spec-sheet/sheet-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ projectId: 'p1', documentId: 'd1', sheetId: 'sheet-1' }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
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

// The renderer, counted: how many are mounted now, and the most that were ever mounted at once.
let live = 0;
let peak = 0;
function CountedRenderer({
  doc,
}: {
  doc: { sheets: { tags: { request_tag_id: string }[] }[] };
}) {
  const key = doc?.sheets?.[0]?.tags?.[0]?.request_tag_id ?? 'unknown';
  React.useEffect(() => {
    live += 1;
    peak = Math.max(peak, live);
    return () => {
      live -= 1;
    };
  }, []);
  return <div data-testid={`tag-sheet-renderer-${key}`} data-renderer="1" />;
}
vi.mock(
  '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer',
  () => ({
    default: (props: {
      doc: { sheets: { tags: { request_tag_id: string }[] }[] };
    }) => <CountedRenderer {...props} />,
  }),
);

// The live designer (F4), counted like a renderer: the first pages in the window draw it, the rest
// stay pictures, so the mounted total stays bounded either way.
vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor',
  () => ({
    TagCanvasEditor: (props: {
      docId: string;
      doc: { layers: unknown[] };
      onLayersChange: (layers: unknown[]) => void;
    }) => (
      <CountedRenderer
        doc={{
          sheets: [
            {
              tags: [
                { request_tag_id: props.docId.split(':').slice(1).join(':') },
              ],
            },
          ],
        }}
      />
    ),
  }),
);

// The Add accessory picker, counted: mounted now, and renders since the last reset. With 30+ pages a
// picker on every page re-rendered on every page change and cost ~500 ms long tasks (crew pass, 3 Nov).
let pickersLive = 0;
let pickerRenders = 0;
function CountedPicker() {
  pickerRenders += 1;
  React.useEffect(() => {
    pickersLive += 1;
    return () => {
      pickersLive -= 1;
    };
  }, []);
  return <div data-picker="1" />;
}
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: () => <CountedPicker />,
  default: () => <CountedPicker />,
}));

import { SpecSheetReader } from './SpecSheetReader';

// ---- fixtures ------------------------------------------------------------------------------------

const KEYS = ['cover', ...Array.from({ length: 29 }, (_, i) => `k${i + 1}`)];

function detail() {
  return {
    id: 'sheet-1',
    sheet_no: 1,
    label: 'SS1',
    source_label: 'PRJQ-2026-0027-R1',
    source_hint: 'issued 03 Nov 2026',
    is_draft: false,
    templates: {
      cover: { id: 'tc', name: 'Cover', version_no: 1 },
      page: { id: 'tp', name: 'Page', version_no: 1 },
      single: null,
    },
    newer_templates: false,
    page_size: { width_mm: 338.7, height_mm: 190.5 },
    pages: KEYS.map((key, i) => ({
      key,
      number: key === 'cover' ? null : i + 1,
      code: key === 'cover' ? '' : `CODE-${key}`,
      name: key === 'cover' ? 'Cover' : `Product ${key}`,
      brand: '',
      area: '',
      area_default: '',
      comment: '',
      marker: '',
      hidden: false,
      picked: [],
      accessories: [],
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
            layers: [],
          },
        ],
      })),
    },
    resolvedData: {},
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
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpecSheetReader projectId="p1" documentId="d1" sheetId="sheet-1" />
    </QueryClientProvider>,
  );
}

const sortedKeysOf = (callIndex: number) =>
  [...(getSpecSheetPreview.mock.calls[callIndex][3] as string[])].sort();

beforeEach(() => {
  queueSpecSheetPdf.mockReset().mockResolvedValue({ id: 'dl-1' });
  observers.length = 0;
  live = 0;
  peak = 0;
  getSpecSheet.mockReset().mockResolvedValue(detail());
  updateSpecSheet.mockReset().mockResolvedValue(detail());
  getSpecSheetPageImages
    .mockReset()
    .mockResolvedValue({ images: {}, assets: {} });
  getSpecSheetPreview
    .mockReset()
    .mockImplementation(
      async (_p: string, _d: string, _s: string, keys: string[]) =>
        previewFor(keys),
    );
});


async function choose(label: RegExp) {
  const direct = screen.queryByRole('button', { name: label });
  if (direct) {
    fireEvent.click(direct);
    return;
  }
  const trigger = screen.getAllByRole('button', { name: /^export/i })[0];
  // Radix opens its menu on pointerdown, which fireEvent.mouseDown/click never sends.
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(await screen.findByRole('menuitem', { name: label }));
}

describe('SpecSheetReader export formats (B5)', () => {
  it('offers PowerPoint beside PDF', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    expect(screen.getAllByRole('button', { name: /^export/i }).length).toBeGreaterThan(0);
    const trigger = screen.getAllByRole('button', { name: /^export/i })[0];
    if (!screen.queryByRole('button', { name: /powerpoint/i })) {
      fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    }
    expect(await screen.findByText(/powerpoint/i)).toBeInTheDocument();
  });

  it('choosing PowerPoint queues the export as pptx', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await choose(/powerpoint/i);
    await waitFor(() => expect(queueSpecSheetPdf).toHaveBeenCalledTimes(1));
    expect(queueSpecSheetPdf).toHaveBeenCalledWith('p1', 'd1', 'sheet-1', 'pptx');
  });

  it('choosing PDF queues the export as pdf', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    await choose(/^(export )?pdf$/i);
    await waitFor(() => expect(queueSpecSheetPdf).toHaveBeenCalledTimes(1));
    expect(queueSpecSheetPdf).toHaveBeenCalledWith('p1', 'd1', 'sheet-1', 'pdf');
  });
});
