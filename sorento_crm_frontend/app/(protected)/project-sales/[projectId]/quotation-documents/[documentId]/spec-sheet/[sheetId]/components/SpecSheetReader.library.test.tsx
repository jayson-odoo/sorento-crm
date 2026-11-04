/**
 * The designer's library (artwork, brand fonts, spec keys) loads ONCE per session, however many
 * live canvases mount and unmount while the reader scrolls. `useKitLibrary` is NOT mocked here:
 * the three service calls are, and each must be called exactly once.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
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
Element.prototype.scrollIntoView = vi.fn();

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
        }));
      if (entries.length) observer.callback(entries);
    }
  });
}

const getSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
vi.mock(
  '@/app/(protected)/project-sales/_shared/services/specSheetService',
  () => ({
    listSpecSheets: vi.fn(),
    createSpecSheet: vi.fn(),
    getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
    updateSpecSheet: vi.fn(),
    getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
    getSpecSheetPageDesign: vi.fn(),
    getSpecSheetPageImages: vi.fn(async () => ({ images: {}, assets: {} })),
    saveSpecSheetPageEdit: vi.fn(),
    applySpecSheetLayerToAll: vi.fn(),
    queueSpecSheetPdf: vi.fn(),
  }),
);
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/x',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
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
vi.mock(
  '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer',
  () => ({
    default: () => <div data-renderer="1" />,
  }),
);

// The three library reads: counted. The hook that makes them is the real one.
const listAssets = vi.fn();
const listFontAssets = vi.fn();
const listSpecKeys = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/services/assetService', () => ({
  listAssets: (...a: unknown[]) => listAssets(...a),
  listFontAssets: (...a: unknown[]) => listFontAssets(...a),
}));
vi.mock(
  '@/app/(protected)/dealer-kit/services/tagDataService',
  async (importOriginal) => ({
    ...(await importOriginal<Record<string, unknown>>()),
    listSpecKeys: (...a: unknown[]) => listSpecKeys(...a),
  }),
);

// A designer that, like the real one, uses the library hook on every mount.
vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor',
  async () => {
    const { useKitLibrary } =
      await import('@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings');
    return {
      TagCanvasEditor: function LibraryUsingCanvas(props: { docId: string }) {
        useKitLibrary();
        return (
          <div
            data-testid={`live-canvas-${props.docId.split(':').slice(1).join(':')}`}
          />
        );
      },
    };
  },
);

import { SpecSheetReader } from './SpecSheetReader';

const KEYS = ['cover', ...Array.from({ length: 29 }, (_, i) => `k${i + 1}`)];
function detail() {
  return {
    id: 'sheet-1',
    sheet_no: 1,
    label: 'SS1',
    source_label: 'R1',
    source_hint: '',
    is_draft: false,
    templates: {
      cover: { id: 'tc', name: 'C', version_no: 1 },
      page: { id: 'tp', name: 'P', version_no: 1 },
      single: null,
    },
    templates_missing: [],
    newer_templates: false,
    page_size: { width_mm: 338.7, height_mm: 190.5 },
    pages: KEYS.map((key, i) => ({
      key,
      number: i + 1,
      code: `CODE-${key}`,
      name: key,
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
        id: `s-${key}`,
        tags: [
          {
            id: `t-${key}`,
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

beforeEach(() => {
  observers.length = 0;
  getSpecSheet.mockReset().mockResolvedValue(detail());
  getSpecSheetPreview
    .mockReset()
    .mockImplementation(
      async (_p: string, _d: string, _s: string, keys: string[]) =>
        previewFor(keys),
    );
  listAssets.mockReset().mockResolvedValue([]);
  listFontAssets.mockReset().mockResolvedValue([]);
  listSpecKeys.mockReset().mockResolvedValue([]);
});

describe('the designer library across live canvases', () => {
  it('is read once for the session while canvases mount and unmount as the reader scrolls', async () => {
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
      },
    });
    render(
      <QueryClientProvider client={client}>
        <SpecSheetReader projectId="p1" documentId="d1" sheetId="sheet-1" />
      </QueryClientProvider>,
    );
    await screen.findByTestId('spec-page-k29');

    for (const window of [
      ['cover', 'k1', 'k2'],
      ['k8', 'k9', 'k10'],
      ['k20', 'k21', 'k22'],
      ['cover', 'k1', 'k2'],
    ]) {
      report(window);
      await waitFor(() =>
        expect(screen.queryByTestId(`live-canvas-${window[0]}`)).not.toBeNull(),
      );
    }

    expect(listAssets).toHaveBeenCalledTimes(1);
    expect(listFontAssets).toHaveBeenCalledTimes(1);
    expect(listSpecKeys).toHaveBeenCalledTimes(1);
  });
});
