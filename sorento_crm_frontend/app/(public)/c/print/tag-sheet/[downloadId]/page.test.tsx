/**
 * The tag sheet page tells the worker when it is FINISHED, not when it has data.
 *
 * `data-dk-print-ready` flipped the moment the payload arrived, so Chromium was
 * free to call `page.pdf()` while the product photos and the badge artwork were
 * still in flight: the tags printed with blank boxes where the pictures belong,
 * and nothing on the sheet said anything had been missed.
 *
 * The catalogue print page beside it already counts its images before reporting
 * ready. Its test's `PendingImage` stub is the pattern this borrows.
 */
import { Suspense } from 'react';
import { act, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TagSheetPrintPage from './page';

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => {}),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
}));

const PHOTO = 'https://cdn.test.invalid/photo.jpg?sig=1';
const BADGE = 'https://cdn.test.invalid/badge.png?sig=1';

/** An `Image` that never loads on its own, so a test decides when it does. */
class PendingImage {
  static created: PendingImage[] = [];
  complete = false;
  src = '';
  private handlers: Record<string, Array<() => void>> = {};

  constructor() {
    PendingImage.created.push(this);
  }

  addEventListener(type: string, handler: () => void) {
    (this.handlers[type] ??= []).push(handler);
  }

  fire(type: string) {
    (this.handlers[type] ?? []).forEach((handler) => handler());
  }
}

function payload(media: { assets?: Record<string, string>; images?: Record<string, string> }) {
  return {
    doc: {
      kind: 'tag_sheet',
      imposition: {
        preset: 'a4_3up',
        sheet_width_mm: 210,
        sheet_height_mm: 297,
        bleed_mm: 0,
        gutter_mm: 0,
      },
      sheets: [{ id: 'sheet-1', tags: [] }],
    },
    resolvedData: {},
    assets: media.assets ?? {},
    images: media.images ?? {},
    fonts: [],
    requestDocNumber: 'PT-202608-0001',
    version: 1,
  };
}

function stub(media: { assets?: Record<string, string>; images?: Record<string, string> }) {
  PendingImage.created = [];
  vi.stubGlobal('Image', PendingImage);
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => payload(media) }),
  );
}

async function renderPage() {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <Suspense fallback={<p>Loading</p>}>
        <TagSheetPrintPage
          params={Promise.resolve({ downloadId: 'dl-1' })}
          searchParams={Promise.resolve({ token: 'tok' })}
        />
      </Suspense>,
    );
  });
  return result;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the tag sheet print page reports ready', () => {
  it('not while the pictures on the tags are still loading', async () => {
    stub({ images: { 'att-1': PHOTO }, assets: { 'asset-1': BADGE } });

    const { container } = await renderPage();
    const main = container.querySelector('main[data-dk-print-ready]') as HTMLElement;

    expect(PendingImage.created.map((image) => image.src).sort()).toEqual(
      [BADGE, PHOTO].sort(),
    );
    expect(main.dataset.dkPrintReady).toBe('false');

    await act(async () => {
      PendingImage.created.forEach((image) => image.fire('load'));
    });

    expect(main.dataset.dkPrintReady).toBe('true');
  });

  it('as soon as it has the payload when the sheet carries no pictures', async () => {
    stub({});

    const { container } = await renderPage();
    const main = container.querySelector('main[data-dk-print-ready]') as HTMLElement;

    expect(PendingImage.created).toHaveLength(0);
    expect(main.dataset.dkPrintReady).toBe('true');
  });

  it('even when a picture is broken, rather than never', async () => {
    // A photo the CDN refuses must not hold the render open until the worker
    // gives up: the sheet is still correct apart from that one box.
    stub({ images: { 'att-1': PHOTO } });

    const { container } = await renderPage();
    const main = container.querySelector('main[data-dk-print-ready]') as HTMLElement;
    expect(main.dataset.dkPrintReady).toBe('false');

    await act(async () => PendingImage.created[0].fire('error'));

    expect(main.dataset.dkPrintReady).toBe('true');
  });
});
