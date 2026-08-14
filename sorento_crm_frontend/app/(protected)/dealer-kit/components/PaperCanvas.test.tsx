import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CatalogueRenderer } from './CatalogueRenderer';
import { PaperCanvas } from './PaperCanvas';
import {
  DEFAULT_PRINT_PROFILE,
  type Block,
  type Section,
  type SectionStyle,
} from '@/lib/dealer-kit/types';

/**
 * Paper mode is an editor canvas too, and the PDF it previews HAS backgrounds.
 *
 * So the same gap applied here: a designer switching to Paper to check the page
 * breaks saw a white sheet where the export puts the flyer's banner. That is a
 * preview that disagrees with its own output, which is the failure this slice
 * exists to close, and it is closed by the same shared surface rather than by a
 * second one written for paper.
 */

const BLOCK_ID = 'blk-heading';

const HEADING: Block = {
  id: BLOCK_ID,
  type: 'heading',
  hideInPrint: false,
  props: { kind: 'heading', text: 'WATER CLOSET', scale: '2xl' },
};

const BANNER: SectionStyle = {
  background: 'transparent',
  paddingY: 'lg',
  backgroundAssetId: 'asset-1',
  backgroundFit: 'width',
};

function section(style: SectionStyle): Section {
  return {
    id: 'sec-1',
    name: 'WATER CLOSET',
    style,
    blocks: [HEADING],
    layouts: {
      desktop: {
        blocks: { [BLOCK_ID]: { colStart: 1, colSpan: 12, rowStart: 1, rowSpan: 1 } },
        isDerived: false,
      },
      tablet: {
        blocks: { [BLOCK_ID]: { colStart: 1, colSpan: 8, rowStart: 1, rowSpan: 1 } },
        isDerived: true,
      },
      mobile: {
        blocks: { [BLOCK_ID]: { colStart: 1, colSpan: 4, rowStart: 1, rowSpan: 1 } },
        isDerived: true,
      },
    },
    printMode: 'include',
  };
}

/**
 * The declarations that ARE the surface. Read as longhands, never as
 * `style.cssText`: jsdom re-serializes the `background` shorthand and drops
 * whatever was set after it, so a cssText comparison reports the same string
 * for a section with artwork and one without.
 */
function surfaceOf(element: HTMLElement) {
  const { style } = element;
  return {
    background: style.background,
    backgroundImage: style.backgroundImage,
    backgroundSize: style.backgroundSize,
    backgroundRepeat: style.backgroundRepeat,
    backgroundPosition: style.backgroundPosition,
  };
}

function paperSurface(
  style: SectionStyle,
  assets?: Record<string, string>,
): HTMLElement {
  const view = render(
    <PaperCanvas
      sections={[section(style)]}
      profile={DEFAULT_PRINT_PROFILE}
      assets={assets}
    />,
  );

  const element = view.container.querySelector('[data-dk-paper-section-id="sec-1"]');
  expect(element).not.toBeNull();
  return element as HTMLElement;
}

describe('PaperCanvas section backgrounds', () => {
  it('paints the artwork the PDF will carry', () => {
    const surface = paperSurface(BANNER, {
      'asset-1': 'https://cdn.test/banner.jpg?sig=abc',
    });

    expect(surface.style.backgroundImage).toContain('https://cdn.test/banner.jpg?sig=abc');
  });

  it('paints the same surface the published catalogue does', () => {
    const assets = { 'asset-1': 'https://cdn.test/banner.jpg?sig=abc' };
    const paper = surfaceOf(paperSurface(BANNER, assets));

    const view = render(
      <CatalogueRenderer name="Flyer" sections={[section(BANNER)]} assets={assets} />,
    );
    const published = surfaceOf(
      view.container.querySelector('[data-dk-section-id="sec-1"]') as HTMLElement,
    );

    // A real surface first: both sides painting nothing would otherwise be
    // "parity" too, and that is the bug rather than the fix.
    expect(paper.backgroundImage).toContain('url(');
    expect(paper).toEqual(published);
  });

  it('renders no artwork when the asset could not be signed', () => {
    const surface = paperSurface(BANNER, {});

    expect(surface.style.backgroundImage).not.toContain('url(');
  });
});
