import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BuilderCanvas } from './BuilderCanvas';
import { CatalogueRenderer } from './CatalogueRenderer';
import type { Block, Section, SectionStyle } from '@/lib/dealer-kit/types';

/**
 * AC-F3, editor half: the person reviewing a seeded draft sees the artwork.
 *
 * S7.5 made the flyer's banner a section background on the public catalogue and
 * in the PDF, both of which go through `CatalogueRenderer`. The builder painted
 * nothing, so the one person who most needs to see the picture - the designer
 * correcting a heading the extractor is KNOWN to misread ("Transforming Your"
 * where the paper says "BATHTUB COLLECTION") - was asked to approve a brochure
 * against a blank canvas.
 *
 * The parity test below is the one that matters. Two tests asserting each
 * surface separately would both pass while the two surfaces disagreed, and a
 * builder that disagrees with what it publishes is the entire defect class this
 * feature exists to prevent. It bites by comparing the rendered `style`
 * attribute of both, so a second implementation of the surface - or the editor
 * simply not being handed the signed URLs - fails it.
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
    printMode: 'breakBefore',
  };
}

/**
 * The declarations that ARE the surface, read back off a rendered element.
 *
 * Read property by property rather than as `style.cssText`: jsdom re-serializes
 * the `background` shorthand and drops the longhands set after it, so a cssText
 * comparison reports `background: transparent;` for both a section with artwork
 * and one without - and a parity test written that way passes while the two
 * surfaces disagree, which is worse than not having it.
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

/** The builder canvas for one section, returning the surface it paints. */
function editorSurface(
  style: SectionStyle,
  assets?: Record<string, string>,
  blocks: Block[] = [HEADING],
): HTMLElement {
  const view = render(
    <BuilderCanvas
      blocks={blocks}
      placements={
        blocks.length
          ? { [BLOCK_ID]: { colStart: 1, colSpan: 12, rowStart: 1, rowSpan: 1 } }
          : {}
      }
      breakpoint="desktop"
      selectedBlockId={null}
      sectionStyle={style}
      assets={assets}
      onSelectBlock={() => {}}
      onPlacementsChange={() => {}}
      onGrowBlock={() => {}}
      onDeleteBlock={() => {}}
    />,
  );

  const element = view.container.querySelector('[data-testid="dk-builder-canvas"]');
  expect(element).not.toBeNull();
  return element as HTMLElement;
}

/** The same section as a reader receives it. */
function publishedSurface(
  style: SectionStyle,
  assets?: Record<string, string>,
): HTMLElement {
  const view = render(
    <CatalogueRenderer name="Flyer" sections={[section(style)]} assets={assets} />,
  );

  const element = view.container.querySelector('[data-dk-section-id="sec-1"]');
  expect(element).not.toBeNull();
  return element as HTMLElement;
}

describe('BuilderCanvas section backgrounds', () => {
  it('paints the bound artwork behind the section being edited', () => {
    const surface = editorSurface(BANNER, {
      'asset-1': 'https://cdn.test/banner.jpg?sig=abc',
    });

    expect(surface.style.backgroundImage).toContain('https://cdn.test/banner.jpg?sig=abc');
  });

  it('lays a band across the top rather than zooming it to fill', () => {
    // A 4:1 header band told to cover is magnified until only a smear shows,
    // which is not what was printed.
    const surface = editorSurface(BANNER, { 'asset-1': 'https://cdn.test/banner.jpg' });

    expect(surface.style.backgroundSize).toBe('100%');
    expect(surface.style.backgroundRepeat).toBe('no-repeat');
    expect(surface.style.backgroundPosition).toContain('top');
  });

  it('fills the section when the artwork was the whole printed page', () => {
    const surface = editorSurface(
      { ...BANNER, backgroundFit: 'cover' },
      { 'asset-1': 'https://cdn.test/cover.jpg' },
    );

    expect(surface.style.backgroundSize).toBe('cover');
  });

  it('renders no artwork when the asset could not be signed', () => {
    // The server signs strictly and omits what it could not sign, so an
    // unsignable file arrives ABSENT rather than as a URL the CDN answers 403
    // to. The canvas falls back to the plain background, which is a state the
    // design has - unlike a broken image.
    const surface = editorSurface(BANNER, {});

    expect(surface.style.backgroundImage).not.toContain('url(');
  });

  it('leaves a section with no bound artwork exactly as it was', () => {
    const surface = editorSurface({ background: 'transparent', paddingY: 'lg' });

    expect(surface.style.backgroundImage).not.toContain('url(');
  });

  it('still shows the artwork on a section that has no blocks yet', () => {
    // The empty section is not a blank slate: it already carries a background,
    // and a reader would see it. Hiding it here would mean the first block gets
    // placed against a surface the designer has not been shown.
    const surface = editorSurface(BANNER, { 'asset-1': 'https://cdn.test/banner.jpg' }, []);

    expect(surface.style.backgroundImage).toContain('https://cdn.test/banner.jpg');
  });

  it('paints the same surface the published catalogue does', () => {
    const assets = { 'asset-1': 'https://cdn.test/banner.jpg?sig=abc' };

    const editor = surfaceOf(editorSurface(BANNER, assets));
    const published = surfaceOf(publishedSurface(BANNER, assets));

    // Asserted to be a REAL surface first, so the comparison cannot pass by
    // both sides painting nothing - which is exactly what an editor that never
    // received the signed URLs would do.
    expect(editor.backgroundImage).toContain('url(');
    // Every declaration, not just the image: one that agreed on the URL and
    // forgot `no-repeat` would tile the banner down the page in the builder
    // while the catalogue laid it across the top once.
    expect(editor).toEqual(published);
  });

  it('agrees with the published catalogue about an unsignable asset too', () => {
    const editor = surfaceOf(editorSurface(BANNER, {}));
    const published = surfaceOf(publishedSurface(BANNER, {}));

    // No artwork on either, and the same fallback: the plain background the
    // section already had, not a broken picture and not a bare canvas.
    expect(editor.backgroundImage).not.toContain('url(');
    expect(editor).toEqual(published);
  });
});
