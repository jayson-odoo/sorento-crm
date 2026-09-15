/**
 * The shared design card (r9 S1/D2, AC-S1-3 + AC-S1-6).
 *
 * ONE viewer for the salesperson's portal page and marketing's detail page, so
 * a proof, a preview and a print cannot disagree. What this file asserts is the
 * CARD's contract, which is deliberately small: fit to width, a pager only when
 * there is more than one sheet, one Open button, and a Download that says why
 * it is disabled instead of doing nothing.
 *
 * The media maps matter more than they look. Before r9 the card drew the same
 * document the PDF draws but WITHOUT `assets` / `images` / `fonts`, so every
 * image layer painted `#f5f5f5` and every photo slot painted `#f0f0f0` plus a
 * product code. "An `<img>` with the signed src reaches the DOM" is the whole
 * defect, expressed as an assertion.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import DesignViewer from './DesignViewer';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

// jsdom has no ResizeObserver, and the card measures its container to fit.
class StubResizeObserver {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    this.callback(
      [{ contentRect: { width: 640, height: 480 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as Record<string, unknown>).ResizeObserver =
  StubResizeObserver;

vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dealer-kit/fonts')>();
  return {
    ...actual,
    ensureFontsLoaded: vi.fn(async () => {}),
    ensureSeedFontsLoaded: vi.fn(async () => {}),
  };
});

const ASSET_URL = 'https://cdn.example.test/signed/artwork.png';
const PHOTO_URL = 'https://cdn.example.test/signed/photo.jpg';

function tag(requestTagId: string, id: string) {
  return {
    id,
    request_tag_id: requestTagId,
    x_mm: 10,
    y_mm: 10,
    width_mm: 80,
    height_mm: 50,
    layers: [
      {
        id: `${id}-art`,
        type: 'image',
        x_mm: 0,
        y_mm: 0,
        width_mm: 80,
        height_mm: 50,
        props: { kind: 'image', source: { type: 'asset', assetId: 'asset-1' } },
      },
      {
        id: `${id}-photo`,
        type: 'product_slot',
        x_mm: 40,
        y_mm: 0,
        width_mm: 40,
        height_mm: 50,
        // A product photo slot: the picture follows the TAG's primary photo,
        // resolved through `images`, not through the asset library.
        props: { kind: 'product_slot', fieldKey: 'product_image' },
      },
    ],
  };
}

function payload(sheetCount = 1): TagSheetDesignPayload {
  return {
    page_id: 'page-1',
    version: 3,
    source: 'version',
    doc: {
      kind: 'tag_sheet',
      imposition: { page_width_mm: 210, page_height_mm: 297 },
      sheets: Array.from({ length: sheetCount }, (_, index) => ({
        id: `sheet-${index + 1}`,
        tags: [tag('line-1', `tag-${index + 1}`)],
      })),
    } as unknown as TagSheetDesignPayload['doc'],
    resolvedData: {
      // Keyed by REQUEST TAG since the combos slice; the everyday request has
      // one tag per line and its id is the line's here.
      'line-1': {
        tag_id: 'line-1',
        tag_label: '1a',
        open_groups: [],
        parts: [],
        line_id: 'line-1',
        code: 'ZZT-SINK-1',
        name: 'ZZT Kitchen Sink',
        dimensions: '',
        spec_lines: '',
        specs: [],
        set_members: '',
        images: [{ attachment_id: 'att-1', url: PHOTO_URL, is_primary: true }],
        list_price: 1599,
        sell_price: null,
        show_promo_price: false,
        included_accessories: '',
        quantity: 1,
        barcode: null,
      },
    } as unknown as TagSheetDesignPayload['resolvedData'],
    assets: { 'asset-1': ASSET_URL },
    images: { 'att-1': PHOTO_URL },
    fonts: [
      { name: 'ZZT Brand', family: 'ZZT Brand', url: '/api/v1/public/dealer-kit/fonts/f1' },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DesignViewer card (AC-S1-3)', () => {
  it('draws the document artwork from the media maps rather than a grey box', () => {
    const { container } = render(
      <DesignViewer docNumber="PT-202609-0001" payload={payload()} />,
    );

    const sources = Array.from(container.querySelectorAll('img')).map((node) =>
      node.getAttribute('src'),
    );
    expect(sources).toContain(ASSET_URL);
  });

  it('draws the bound product photo from the image map', () => {
    const { container } = render(
      <DesignViewer docNumber="PT-202609-0001" payload={payload()} />,
    );

    const sources = Array.from(container.querySelectorAll('img')).map((node) =>
      node.getAttribute('src'),
    );
    expect(sources).toContain(PHOTO_URL);
  });

  it('has exactly one Open button and no zoom control in the card', () => {
    render(<DesignViewer docNumber="PT-202609-0001" payload={payload()} />);

    expect(screen.getAllByRole('button', { name: /Open/ })).toHaveLength(1);
    expect(screen.queryByLabelText('Zoom in')).toBeNull();
    expect(screen.queryByLabelText('Zoom out')).toBeNull();
    expect(screen.queryByLabelText('Zoom level')).toBeNull();
  });

  it('shows no sheet pager for a single sheet document', () => {
    render(<DesignViewer docNumber="PT-202609-0001" payload={payload(1)} />);

    expect(screen.queryByLabelText('Next sheet')).toBeNull();
    expect(screen.queryByText(/Sheet 1 \/ 1/)).toBeNull();
  });

  it('pages sheets once there is more than one', () => {
    render(<DesignViewer docNumber="PT-202609-0001" payload={payload(3)} />);

    expect(screen.getByText('Sheet 1 / 3')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous sheet')).toBeDisabled();

    fireEvent.click(screen.getByLabelText('Next sheet'));

    expect(screen.getByText('Sheet 2 / 3')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous sheet')).not.toBeDisabled();
  });

  it('says what is missing instead of drawing an empty frame', () => {
    render(
      <DesignViewer
        docNumber="PT-202609-0001"
        payload={null}
        emptyMessage="No design yet"
        emptyHint="Claim the request to start designing."
      />,
    );

    expect(screen.getByText('No design yet')).toBeInTheDocument();
    expect(
      screen.getByText('Claim the request to start designing.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open/ })).toBeNull();
  });

  it('does not throw when a doc has a sheet but no imposition (review-round leftover)', () => {
    // `_EMPTY_SHEET_DOC` on the backend used to carry no `imposition` at
    // all, and every reader of a tag_sheet doc read
    // `doc.imposition.page_width_mm` unconditionally. A doc with sheets
    // (so the card does NOT take the "no design yet" early return) but no
    // imposition must not crash the card - it has to draw something,
    // even if that something is blank, rather than throw.
    const withSheetsNoImposition = payload(1);
    const doc = { ...withSheetsNoImposition.doc } as Record<string, unknown>;
    delete doc.imposition;
    const broken = {
      ...withSheetsNoImposition,
      doc,
    } as unknown as typeof withSheetsNoImposition;

    expect(() =>
      render(<DesignViewer docNumber="PT-202609-0001" payload={broken} />),
    ).not.toThrow();
  });
});

describe('Download PDF (AC-S1-6)', () => {
  it('is disabled and says the PDF is being generated while no export completed', () => {
    render(
      <DesignViewer
        docNumber="PT-202609-0001"
        payload={payload()}
        download={{ available: false, onDownload: vi.fn() }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Open/ }));

    const button = screen.getByRole('button', { name: /PDF is being generated/ });
    expect(button).toBeDisabled();
  });

  it('downloads the newest export once one exists', () => {
    const onDownload = vi.fn();
    render(
      <DesignViewer
        docNumber="PT-202609-0001"
        payload={payload()}
        download={{ available: true, onDownload }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Open/ }));

    const button = screen.getByRole('button', { name: 'Download PDF' });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);

    expect(onDownload).toHaveBeenCalledTimes(1);
  });
});

describe('the lightbox opens on the sheet the card was showing', () => {
  it('carries the doc number as its title and the current sheet index', () => {
    render(<DesignViewer docNumber="PT-202609-0001" payload={payload(3)} />);
    fireEvent.click(screen.getByLabelText('Next sheet'));

    fireEvent.click(screen.getByRole('button', { name: /Open/ }));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('PT-202609-0001')).toBeInTheDocument();
    expect(within(dialog).getByText('2 / 3')).toBeInTheDocument();
  });
});
