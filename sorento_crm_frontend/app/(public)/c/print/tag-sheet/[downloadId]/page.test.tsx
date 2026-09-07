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
import { act, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ensureFontsLoaded } from '@/lib/dealer-kit/fonts';

import TagSheetPrintPage from './page';

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
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

function payload(media: {
  assets?: Record<string, string>;
  images?: Record<string, string>;
  fonts?: { name: string; family: string; url: string }[];
  /** One real image layer bound to `media.assets['asset-1']` (S3 review) -
   *  absent renders no tags at all, same payload as before that round. */
  withImageLayer?: boolean;
}) {
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
      sheets: [
        {
          id: 'sheet-1',
          tags: media.withImageLayer
            ? [
                {
                  id: 't1',
                  template_id: 'tpl-1',
                  request_line_id: 'line-1',
                  x_mm: 5,
                  y_mm: 5,
                  width_mm: 95,
                  height_mm: 130,
                  layers: [
                    {
                      id: 'img1',
                      type: 'image',
                      x_mm: 0,
                      y_mm: 0,
                      width_mm: 40,
                      height_mm: 20,
                      rotation_deg: 0,
                      z_index: 1,
                      locked: false,
                      visible: true,
                      slot_binding: null,
                      text_override: null,
                      props: {
                        kind: 'image',
                        source: { type: 'asset', assetId: 'asset-1' },
                        fit: 'contain',
                        maskShape: 'none',
                      },
                    },
                  ],
                },
              ]
            : [],
        },
      ],
    },
    resolvedData: {},
    assets: media.assets ?? {},
    images: media.images ?? {},
    fonts: media.fonts ?? [],
    requestDocNumber: 'PT-202608-0001',
    version: 1,
  };
}

function stub(media: {
  assets?: Record<string, string>;
  images?: Record<string, string>;
  fonts?: { name: string; family: string; url: string }[];
  withImageLayer?: boolean;
}) {
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
  vi.unstubAllEnvs();
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

  it('counts exactly one <img> per image layer, never a second one appearing later (S3 review)', async () => {
    // `CroppedImage` used to swap in a SECOND `<img>` once the first one's
    // own load settled this page's `document.images` snapshot - taken once,
    // synchronously, on mount - so the second, actually-styled element was
    // never counted and `data-dk-print-ready` could flip true before it had
    // painted. One real image layer, bound to `asset-1`.
    stub({ assets: { 'asset-1': PHOTO }, withImageLayer: true });

    const { container } = await renderPage();
    const main = container.querySelector('main[data-dk-print-ready]') as HTMLElement;

    const domImages = () => Array.from(container.querySelectorAll('img'));
    expect(domImages()).toHaveLength(1);
    expect(main.dataset.dkPrintReady).toBe('false');

    await act(async () => {
      // The readiness effect's OWN preload for `asset-1` (a `PendingImage`,
      // separate from the DOM `<img>` TagSheetRenderer mounted for it).
      PendingImage.created.forEach((image) => image.fire('load'));
      // The real DOM `<img>` the layer itself rendered - `document.images`
      // tracks it directly, unrelated to the stubbed `Image` constructor.
      fireEvent.load(domImages()[0]);
    });

    expect(main.dataset.dkPrintReady).toBe('true');
    // Still exactly one - never a second element appearing once natural
    // size resolved.
    expect(domImages()).toHaveLength(1);
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

describe('the brand fonts the print page loads', () => {
  it('are fetched from the api base, since the payload carries a bare path', async () => {
    // The worker drives this page in headless Chromium, which has no notion
    // of "the frontend origin proxies /api/v1" unless the page is served
    // through that proxy - so the page prefixes the path itself (S1).
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://backend.test:8000');
    stub({
      fonts: [
        { name: 'Century Gothic', family: 'Century Gothic', url: '/api/v1/public/dealer-kit/fonts/f1' },
      ],
    });

    await renderPage();

    expect(ensureFontsLoaded).toHaveBeenCalledWith([
      {
        name: 'Century Gothic',
        family: 'Century Gothic',
        url: 'http://backend.test:8000/api/v1/public/dealer-kit/fonts/f1',
      },
    ]);
  });
});
