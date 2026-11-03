/**
 * SPEC-SHEET-V2 red test 15: the PDF-style reader mounts only the pages near the viewport.
 *
 * Owner build order (3 Nov): "make sure don't cause the bottleneck in the system again". A 30-page
 * sheet must not mount 30 renderers, must not ask for 30 previews, and must not refetch in a loop.
 *
 * Written BEFORE the component. What the coder must provide (the contract of this file):
 *
 *   Component   `SpecSheetReader` (named export of ./SpecSheetReader), props
 *               `{ projectId, documentId, sheetId }` (the same ids are also in `useParams()`).
 *   Service     `@/app/(protected)/project-sales/_shared/services/specSheetService` exports exactly:
 *                 listSpecSheets(projectId, documentId)
 *                 createSpecSheet(projectId, documentId, body)
 *                 getSpecSheet(projectId, documentId, sheetId)
 *                 updateSpecSheet(projectId, documentId, sheetId, body)
 *                 getSpecSheetPreview(projectId, documentId, sheetId, keys: string[])
 *                 getSpecSheetPageDesign(projectId, documentId, sheetId, key)
 *                 saveSpecSheetPageEdit(projectId, documentId, sheetId, key, layers)
 *                 queueSpecSheetPdf(projectId, documentId, sheetId)
 *   DOM         every page placeholder in the stack carries data-testid="spec-page-<key>" and
 *               data-page-key="<key>" and is observed by an IntersectionObserver (one fixed-aspect
 *               box per page, sized from detail.page_size). The rail uses other test ids.
 *   Rendering   a page draws through `TagSheetRenderer` (directly or via ScaledSheet) only while its
 *               key is in the visible window; pages outside the window unmount their renderer.
 *   Fetching    ONE getSpecSheet call on open; ONE getSpecSheetPreview call per window change, with
 *               exactly the keys of the pages the observer reports visible.
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
(globalThis as { IntersectionObserver: unknown }).IntersectionObserver = FakeIntersectionObserver;

/** Tell every observer which page keys are in view; every other observed page is out of view. */
function report(visibleKeys: string[]) {
  act(() => {
    for (const observer of observers) {
      const entries = [...observer.targets]
        .filter((el) => el.getAttribute('data-page-key'))
        .map((el) => ({
          target: el,
          isIntersecting: visibleKeys.includes(el.getAttribute('data-page-key') as string),
          intersectionRatio: visibleKeys.includes(el.getAttribute('data-page-key') as string) ? 1 : 0,
        }));
      if (entries.length) observer.callback(entries);
    }
  });
}

// ---- mocks ---------------------------------------------------------------------------------------

const getSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
const updateSpecSheet = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/services/specSheetService', () => ({
  listSpecSheets: vi.fn(),
  createSpecSheet: vi.fn(),
  getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
  updateSpecSheet: (...a: unknown[]) => updateSpecSheet(...a),
  getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
  getSpecSheetPageDesign: vi.fn(),
  saveSpecSheetPageEdit: vi.fn(),
  queueSpecSheetPdf: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1/spec-sheet/sheet-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ projectId: 'p1', documentId: 'd1', sheetId: 'sheet-1' }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
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

// The renderer, counted: how many are mounted now, and the most that were ever mounted at once.
let live = 0;
let peak = 0;
function CountedRenderer({ doc }: { doc: { sheets: { tags: { request_tag_id: string }[] }[] } }) {
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
vi.mock('@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer', () => ({
  default: (props: { doc: { sheets: { tags: { request_tag_id: string }[] }[] } }) => (
    <CountedRenderer {...props} />
  ),
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SpecSheetReader projectId="p1" documentId="d1" sheetId="sheet-1" />
    </QueryClientProvider>,
  );
}

const sortedKeysOf = (callIndex: number) =>
  [...(getSpecSheetPreview.mock.calls[callIndex][3] as string[])].sort();

beforeEach(() => {
  observers.length = 0;
  live = 0;
  peak = 0;
  getSpecSheet.mockReset().mockResolvedValue(detail());
  updateSpecSheet.mockReset().mockResolvedValue(detail());
  getSpecSheetPreview
    .mockReset()
    .mockImplementation(async (_p: string, _d: string, _s: string, keys: string[]) => previewFor(keys));
});

describe('SpecSheetReader: a 30-page sheet mounts only the pages in view', () => {
  it('draws one placeholder per page, a renderer for none of them until pages are reported visible', async () => {
    renderReader();

    await screen.findByTestId('spec-page-k29');
    expect(document.querySelectorAll('[data-testid^="spec-page-"]')).toHaveLength(30);
    expect(getSpecSheet).toHaveBeenCalledTimes(1);
    // Nothing reported visible yet: no renderer is mounted for the other 29, whatever else happens.
    expect(document.querySelector('[data-testid="tag-sheet-renderer-k29"]')).toBeNull();
  });

  it('mounts at most 4 renderers and makes ONE preview request for the first window', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');

    report(['cover', 'k1', 'k2']);

    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(1));
    expect(getSpecSheetPreview.mock.calls[0].slice(0, 3)).toEqual(['p1', 'd1', 'sheet-1']);
    // The window snaps to the 6-page chunk holding the visible pages.
    expect(sortedKeysOf(0)).toEqual(['cover', 'k1', 'k2', 'k3', 'k4', 'k5'].sort());

    await waitFor(() => expect(document.querySelectorAll('[data-renderer="1"]').length).toBeGreaterThan(0));
    expect(document.querySelectorAll('[data-renderer="1"]').length).toBeLessThanOrEqual(4);
    expect(peak).toBeLessThanOrEqual(4);
    expect(document.querySelector('[data-testid="tag-sheet-renderer-k20"]')).toBeNull();
  });

  it('scrolling to pages 10-12 asks once more and unmounts pages 1-3', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['cover', 'k1', 'k2']);
    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByTestId('tag-sheet-renderer-k1')).not.toBeNull());

    report(['k9', 'k10', 'k11']);

    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(2));
    expect(sortedKeysOf(1)).toEqual(['k10', 'k11', 'k6', 'k7', 'k8', 'k9']);
    await waitFor(() => expect(screen.queryByTestId('tag-sheet-renderer-k10')).not.toBeNull());
    for (const gone of ['cover', 'k1', 'k2']) {
      expect(screen.queryByTestId(`tag-sheet-renderer-${gone}`)).toBeNull();
    }
    expect(document.querySelectorAll('[data-renderer="1"]').length).toBeLessThanOrEqual(4);
    expect(peak).toBeLessThanOrEqual(4);
  });

  it('moving between pages of one chunk, and back, makes no further request', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['cover', 'k1', 'k2']);
    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(1));

    report(['k1', 'k2', 'k3']);
    report(['cover', 'k1', 'k2']);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80));
    });

    expect(getSpecSheetPreview).toHaveBeenCalledTimes(1);
  });

  it('scrolling back to a chunk already fetched is a cache hit', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['cover', 'k1', 'k2']);
    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(1));
    report(['k9', 'k10', 'k11']);
    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(2));

    report(['cover', 'k1', 'k2']);
    await waitFor(() => expect(screen.queryByTestId('tag-sheet-renderer-k1')).not.toBeNull());
    expect(getSpecSheetPreview).toHaveBeenCalledTimes(2);
  });

  it('does not refetch in a loop once the window is settled', async () => {
    renderReader();
    await screen.findByTestId('spec-page-k29');
    report(['cover', 'k1', 'k2']);
    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(1));

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 150));
    });
    // The same window reported again is the same query.
    report(['cover', 'k1', 'k2']);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(getSpecSheetPreview).toHaveBeenCalledTimes(1);
    expect(getSpecSheet).toHaveBeenCalledTimes(1);
  });
});
