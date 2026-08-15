import { existsSync } from 'node:fs';
import path from 'node:path';
import { Suspense } from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CataloguePrintPage from './page';
import { DEFAULT_PRINT_PROFILE, type ResolvedTile } from '@/lib/dealer-kit/types';

/**
 * The page headless Chromium prints.
 *
 * The user's requirement is one sentence: the PDF and the brochure on screen
 * must look the same. They share `CatalogueRenderer`, so the only way they can
 * diverge is if one of them hands it different inputs - which is exactly what
 * these cover.
 */

const TILE: ResolvedTile = {
  productId: 'p1',
  productCode: 'SK-3040',
  productName: 'Undermount Kitchen Sink',
  price: 'RM 1,290.00',
  offerPrice: 'RM 599.00',
  invoicePrice: null,
  imageUrl: null,
  dimensions: '760 x 440 mm',
  badges: [],
};

function payload(tileFields: string[], printProfile = DEFAULT_PRINT_PROFILE) {
  return {
    pageName: 'ZZT flyer',
    version: 1,
    audience: 'end_user',
    doc: {
      sections: [
        {
          id: 's1',
          name: 'Products',
          style: {},
          printMode: 'include',
          layouts: {
            desktop: { blocks: {}, isDerived: true },
            tablet: { blocks: {}, isDerived: true },
            mobile: { blocks: {}, isDerived: true },
          },
          blocks: [
            {
              id: 'b1',
              type: 'collection',
              props: {
                kind: 'collection',
                collectionId: 'c1',
                tileTemplateId: 't1',
                columns: { desktop: 4, tablet: 2, mobile: 1 },
              },
            },
          ],
        },
      ],
      printProfile,
    },
    collections: { c1: [TILE] },
    tileTemplates: { t1: tileFields },
  };
}

/**
 * The route reads its params through `use()`, so the render has to be flushed
 * inside `act` - otherwise React never gets past the Suspense fallback and
 * every assertion below reads an empty page.
 */
async function renderPrintPage() {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <Suspense fallback={<p>Loading</p>}>
        <CataloguePrintPage
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

describe('the printed catalogue', () => {
  it('prints the offer with the list price struck through, exactly as the screen does', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload(['name', 'price']) }),
    );

    const { container } = await renderPrintPage();

    expect(await screen.findByText('RM 599.00')).toBeInTheDocument();
    const list = container.querySelector('[data-dk-list-price]') as HTMLElement;
    expect(list).toHaveTextContent('RM 1,290.00');
    expect(list.className).toContain('line-through');
  });

  it('prints the tile design the brochure uses, not a default of its own', async () => {
    // The payload carries the design's field list. Ignoring it would print a
    // different tile from the one on screen - the same product code appearing
    // on paper and not online is how "the PDF looks different" starts.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload(['name', 'offerPrice']) }),
    );

    const { container } = await renderPrintPage();

    expect(await screen.findByText('Undermount Kitchen Sink')).toBeInTheDocument();
    // The design binds the offer alone, so no list price prints beside it.
    expect(container.querySelector('[data-dk-offer-price]')).toHaveTextContent('RM 599.00');
    expect(container.querySelector('[data-dk-list-price]')).toBeNull();
    expect(screen.queryByText('SK-3040')).not.toBeInTheDocument();
  });
});

/**
 * The geometry invariant, stated once: the document occupies the paper exactly.
 *
 * The defect these pin: the right-hand tile was clipped off every export. Two
 * separate causes, both measurable on a rendered A4 PDF - the document was
 * offset 65pt from the left edge by chrome it should never have been inside,
 * and the paper size was declared in two places that only agreed by accident.
 */
describe('the printed page geometry', () => {
  async function printedMain() {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload(['name', 'price']) }),
    );
    const { container } = await renderPrintPage();
    return container.querySelector('main[data-dk-print-ready]') as HTMLElement;
  }

  it('occupies the whole paper, with the margins inside it', async () => {
    const main = await printedMain();

    // `100%` of the page box IS the paper Chromium was told to print on. A
    // width restated in millimetres here is a second opinion about the paper,
    // and the one that loses is whichever one is wrong.
    expect(main.style.width).toBe('100%');
    // Content-box would put the margins OUTSIDE that width, making the
    // document wider than the page by exactly left + right, which is then
    // clipped. Declared locally rather than relied upon from a global reset.
    expect(main.style.boxSizing).toBe('border-box');
    expect(main.style.paddingLeft).toBe(`${DEFAULT_PRINT_PROFILE.margins.left}mm`);
    expect(main.style.paddingRight).toBe(`${DEFAULT_PRINT_PROFILE.margins.right}mm`);
  });

  it('leaves the shell-cancelling rule to the group that owns it', async () => {
    // Every route in `(public)` needs <body> out of the shell's flex row, not
    // just this one - the public catalogue was rendering 274px wide without it.
    // Two copies of one rule is the same defect as two declarations of the
    // paper size, so the layout states it and this page does not repeat it.
    const main = await printedMain();
    const css = (main.querySelector('style') as HTMLStyleElement).innerHTML;

    expect(css).not.toMatch(/display:\s*block\s*!important/);
  });

  it('leaves the paper size to Chromium and states it nowhere itself', async () => {
    const main = await printedMain();
    const css = (main.querySelector('style') as HTMLStyleElement).innerHTML;

    // Chromium ignores `@page size` unless asked for prefer_css_page_size, so
    // this declaration never decided anything - it just looked like it did,
    // and it carried its own landscape swap that would have double-rotated the
    // paper the day someone switched that flag on.
    expect(css).not.toMatch(/@page[^}]*size/);
    // The margins live on <main>; a second set from Chromium would shrink every
    // page by a margin nobody chose.
    expect(css).toMatch(/@page\s*{[^}]*margin:\s*0/);
  });

  it('is not nested under a layout that frames it in chrome', () => {
    // The App Router composes layouts, it never lets a child replace a parent.
    // While these routes sat under `(auth)`, every catalogue - and every PDF -
    // was rendered inside the sign-in Card, which is what pushed the document
    // off the right edge of the paper. The passthrough layout at `c/` looked
    // like it prevented this and could not. Leaving the group is the only fix,
    // so the guard is that the group was left.
    // vitest runs from the frontend root, where vitest.config.ts lives.
    const app = path.join(process.cwd(), 'app');
    expect(existsSync(path.join(app, '(public)/c/print/[downloadId]/page.tsx'))).toBe(true);
    expect(existsSync(path.join(app, '(auth)/c'))).toBe(false);
  });
});

/**
 * One sheet, one layout.
 *
 * The paper is 794px wide on A4 portrait, so the renderer's media queries were
 * firing and handing back TABLET placements, while tile density fell back to
 * its desktop default because the print page named no breakpoint at all. The
 * export therefore stacked blocks the tablet way and filled them at the desktop
 * tile count, which is a page that exists at no width.
 */
describe('the breakpoint the paper is', () => {
  async function printedWith(printProfile: typeof DEFAULT_PRINT_PROFILE) {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => payload(['name', 'price'], printProfile) }),
    );
    const { container } = await renderPrintPage();
    return container;
  }

  function layoutCss(container: HTMLElement): string {
    return (container.querySelector('[data-dk-catalogue] style') as HTMLStyleElement).innerHTML;
  }

  function tilesAcross(container: HTMLElement): string {
    return (container.querySelector('[data-dk-tile-grid]') as HTMLElement).style
      .gridTemplateColumns;
  }

  it('lays an A4 sheet out as the tablet it is, density and placement together', async () => {
    const container = await printedWith(DEFAULT_PRINT_PROFILE);

    // The document declares 4 across on desktop and 2 on tablet.
    expect(tilesAcross(container)).toBe('repeat(2, minmax(0, 1fr))');
    // ...and the placements come from the same breakpoint's variables.
    expect(layoutCss(container)).toContain('var(--dk-t-col)');
    expect(layoutCss(container)).not.toContain('var(--dk-d-col)');
  });

  it('lays an A3 landscape sheet out as the desktop it is', async () => {
    // 420mm is 1587px. The same code that answers "tablet" for A4 has to answer
    // "desktop" here, or it is a constant wearing a function's clothes.
    const container = await printedWith({
      ...DEFAULT_PRINT_PROFILE,
      pageSize: 'A3',
      orientation: 'landscape',
    });

    expect(tilesAcross(container)).toBe('repeat(4, minmax(0, 1fr))');
    expect(layoutCss(container)).toContain('var(--dk-d-col)');
    expect(layoutCss(container)).not.toContain('var(--dk-t-col)');
  });

  it('leaves no media query on the page to disagree with that choice', async () => {
    const container = await printedWith(DEFAULT_PRINT_PROFILE);

    // A query is a second opinion about a width that cannot change. Paper does
    // not resize, and the half of the layout that is data (tile density) could
    // never have been behind a query anyway - which is exactly how the two came
    // apart.
    expect(layoutCss(container)).not.toContain('@media');
  });
});

describe('where a fold is allowed to land', () => {
  it('keeps the break out of the middle of a product', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => payload(['name', 'price']) }),
    );
    const { container } = await renderPrintPage();
    const css = (container.querySelector('main[data-dk-print-ready] style') as HTMLStyleElement)
      .innerHTML;

    // A section taller than one page cannot be kept whole, so Chromium breaks
    // it wherever the fold falls - measured at 47.6pt of a 57pt tile on the
    // first sheet, with that product's price alone on the second. The section
    // rule states what the paginator models; the tile rule states the guarantee
    // that survives when the model cannot hold.
    expect(css).toMatch(/\[data-dk-section-id\]\s*{[^}]*break-inside:\s*avoid/);
    expect(css).toMatch(/\[data-dk-tile\]\s*{[^}]*break-inside:\s*avoid/);
  });
});

/**
 * The flyer's own artwork, on paper.
 *
 * A seeded section carries its banner as a section BACKGROUND, which is a CSS
 * `background-image` and therefore not an `<img>`. That distinction is the whole
 * risk: the readiness flag was counting `document.images`, which does not
 * include backgrounds, so the largest picture on the page was the one thing
 * nothing waited for - and a background that arrives after the worker has
 * printed is a blank band in a PDF nobody re-checks.
 */
describe('the printed section artwork', () => {
  const BANNER = 'https://cdn.test/banner.jpg';

  function bannerPayload(assets: Record<string, string> = { a1: BANNER }) {
    const base = payload(['name', 'price']);
    return {
      ...base,
      doc: {
        ...base.doc,
        sections: [
          {
            ...base.doc.sections[0],
            style: {
              background: 'transparent',
              backgroundAssetId: 'a1',
              backgroundFit: 'width',
            },
          },
        ],
      },
      assets,
    };
  }

  /** An `Image` that never loads on its own, so a test can decide when it does. */
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

  function stubImageAndFetch(assets?: Record<string, string>) {
    PendingImage.created = [];
    vi.stubGlobal('Image', PendingImage);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => bannerPayload(assets) }),
    );
  }

  it('paints the banner the payload signed behind its section', async () => {
    stubImageAndFetch();

    const { container } = await renderPrintPage();
    const section = container.querySelector('[data-dk-section-id="s1"]') as HTMLElement;

    expect(section.style.backgroundImage).toContain(BANNER);
    expect(section.style.backgroundSize).toBe('100%');
  });

  it('does not declare itself ready until the background has loaded', async () => {
    stubImageAndFetch();

    const { container } = await renderPrintPage();
    const main = container.querySelector('main[data-dk-print-ready]') as HTMLElement;

    expect(PendingImage.created).toHaveLength(1);
    expect(PendingImage.created[0].src).toBe(BANNER);
    expect(main.dataset.dkPrintReady).toBe('false');

    await act(async () => PendingImage.created[0].fire('load'));

    expect(main.dataset.dkPrintReady).toBe('true');
  });

  it('is ready anyway when the document binds no artwork', async () => {
    // An asset the server could not sign is ABSENT from the map rather than a
    // URL the CDN answers 403 to. Nothing to wait for, and the section falls
    // back to its plain background.
    stubImageAndFetch({});

    const { container } = await renderPrintPage();
    const main = container.querySelector('main[data-dk-print-ready]') as HTMLElement;

    expect(PendingImage.created).toHaveLength(0);
    expect(main.dataset.dkPrintReady).toBe('true');
  });
});
