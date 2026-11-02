/**
 * PS-SPEC-SHEET (crew browser pass, step 14): the page strip with the REAL shared Sortable.
 *
 * The strip did not reorder in a browser, by mouse or keyboard: the pages were wrapped in a div
 * inside `Sortable`, whose drag overlay clones the dragged item from its DIRECT children, so the
 * overlay was empty, zero-sized, and dnd-kit (which measures collisions with the overlay) never
 * found a page under it. jsdom cannot run dnd-kit's collision detection (no layout), so this pins
 * the structure the fix depends on; the drag itself was checked in Chromium (evidence README,
 * `evidence-ps-spec-sheet/dnd/`).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
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

const getSpecSheet = vi.fn();
const saveSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
vi.mock('../../../../_shared/services/specSheetService', () => ({
  getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
  saveSpecSheet: (...a: unknown[]) => saveSpecSheet(...a),
  getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
  queueSpecSheetPdf: vi.fn(),
}));
vi.mock('@/components/dealer-kit/ScaledSheet', () => ({
  default: () => <div />,
  sheetPixelSize: () => ({ width: 1280, height: 720 }),
  PX_PER_MM: 96 / 25.4,
}));
vi.mock('./QuotationDocumentContext', () => ({
  useQuotationDocumentScreen: () => ({
    projectId: 'p1',
    documentId: 'd1',
    canEdit: true,
  }),
}));

import { QuotationSpecSheetTab } from './QuotationSpecSheetTab';

const page = (key: string, code: string) => ({
  key,
  line_id: `l-${key}`,
  product_id: key,
  code,
  name: code,
  brand: '',
  image_attachment_id: null,
  drawing_attachment_id: null,
  accessories: [],
  picked: [],
  area: '',
  area_default: '',
  comment: '',
  marker: '',
  hidden: false,
});

const VIEW = {
  settings: {
    cover_template_id: 'c',
    page_template_id: 'p',
    single_page_template_id: null,
    issue_id: null,
    rows: [],
  },
  issue_id: 'issue-1',
  issues: [{ id: 'issue-1', issue_no: 1, label: 'Q-R1', issued_at: null }],
  pages: [
    page('wc', 'SRTWC0001'),
    page('basin', 'SRTWB0002'),
    page('trap', 'SRTBT0006'),
  ],
  templates: {
    cover: [{ id: 'c', name: 'Cover', width_mm: 338.7, height_mm: 190.5 }],
    page: [{ id: 'p', name: 'Page', width_mm: 338.7, height_mm: 190.5 }],
  },
};

beforeEach(() => {
  getSpecSheet.mockReset().mockResolvedValue(VIEW);
  saveSpecSheet.mockReset().mockResolvedValue(VIEW);
  getSpecSheetPreview.mockReset().mockResolvedValue({
    doc: {
      kind: 'tag_sheet',
      imposition: {
        preset: 'custom',
        page_width_mm: 338.7,
        page_height_mm: 190.5,
        bleed_mm: 0,
        gap_mm: 0,
      },
      sheets: ['cover', 'wc', 'basin', 'trap'].map((key) => ({
        id: key,
        tags: [
          {
            id: key,
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
    page_size: { width_mm: 338.7, height_mm: 190.5 },
  });
});

describe('page strip with the real shared Sortable', () => {
  it('every page is a direct child of the Sortable root, so a drag has an overlay to measure', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <QuotationSpecSheetTab />
      </QueryClientProvider>,
    );

    const strip = await screen.findByTestId('spec-sheet-strip');
    const root = strip.querySelector('[data-slot="sortable"]') as HTMLElement;
    expect(root).not.toBeNull();
    const items = Array.from(
      strip.querySelectorAll('[data-slot="sortable-item"]'),
    );
    expect(items.map((el) => el.getAttribute('data-value'))).toEqual([
      'wc',
      'basin',
      'trap',
    ]);
    for (const item of items) expect(item.parentElement).toBe(root);
    // Each handle is focusable, so the keyboard sensor can start a drag.
    for (const code of ['SRTWC0001', 'SRTWB0002', 'SRTBT0006']) {
      expect(
        within(strip).getByLabelText(`Drag ${code} to reorder`),
      ).toHaveAttribute('tabindex', '0');
    }
  });

  it('a finger drag on a handle drags the page instead of scrolling the strip (touch-action: none)', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <QuotationSpecSheetTab />
      </QueryClientProvider>,
    );

    const strip = await screen.findByTestId('spec-sheet-strip');
    for (const code of ['SRTWC0001', 'SRTWB0002', 'SRTBT0006']) {
      // On a phone the browser owns a touch gesture unless touch-action says otherwise: without
      // it the strip scrolls and the pointer drag is cancelled (crew 375 px finger test).
      expect(within(strip).getByLabelText(`Drag ${code} to reorder`)).toHaveClass('touch-none');
    }
  });
});
