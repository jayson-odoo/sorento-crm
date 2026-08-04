import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CatalogueRenderer } from './CatalogueRenderer';
import type { Section } from '@/lib/dealer-kit/types';

/**
 * AC-F3: the flyer's banner is the section BACKGROUND and its heading is a text
 * block over it.
 *
 * Both halves matter and they pull in opposite directions. Baking the heading
 * into the artwork would be less work and would look identical in a screenshot -
 * and would mean a heading nobody can correct, search for, or translate. The
 * extractor is known to misread headings (one page of the real flyer reads
 * "Transforming Your" where the paper says "BATHTUB COLLECTION"), so a heading
 * that lives only in a bitmap is a defect a reviewer cannot fix.
 *
 * This renderer is shared by the public catalogue and the print page, so a
 * background applied here is applied to the screen and to the PDF at once.
 */

function section(overrides: Partial<Section> = {}): Section {
  const blockId = 'blk-heading';
  return {
    id: 'sec-1',
    name: 'WATER CLOSET',
    style: { background: 'transparent', paddingY: 'lg' },
    blocks: [
      {
        id: blockId,
        type: 'heading',
        hideInPrint: false,
        props: { kind: 'heading', text: 'WATER CLOSET', scale: '2xl' },
      },
    ],
    layouts: {
      desktop: {
        blocks: { [blockId]: { colStart: 1, colSpan: 12, rowStart: 1, rowSpan: 1 } },
        isDerived: false,
      },
      tablet: {
        blocks: { [blockId]: { colStart: 1, colSpan: 8, rowStart: 1, rowSpan: 1 } },
        isDerived: true,
      },
      mobile: {
        blocks: { [blockId]: { colStart: 1, colSpan: 4, rowStart: 1, rowSpan: 1 } },
        isDerived: true,
      },
    },
    printMode: 'breakBefore',
    ...overrides,
  };
}

function sectionElement(): HTMLElement {
  const element = document.querySelector('[data-dk-section-id="sec-1"]');
  expect(element).not.toBeNull();
  return element as HTMLElement;
}

describe('CatalogueRenderer section backgrounds', () => {
  it('paints the bound asset behind the section', () => {
    render(
      <CatalogueRenderer
        name="Flyer"
        sections={[
          section({
            style: {
              background: 'transparent',
              paddingY: 'lg',
              backgroundAssetId: 'asset-1',
              backgroundFit: 'width',
            },
          }),
        ]}
        assets={{ 'asset-1': 'https://cdn.test/banner.jpg?sig=abc' }}
      />,
    );

    expect(sectionElement().style.backgroundImage).toContain(
      'https://cdn.test/banner.jpg?sig=abc',
    );
  });

  it('keeps the heading a real, selectable text node over the artwork', () => {
    render(
      <CatalogueRenderer
        name="Flyer"
        sections={[
          section({
            style: {
              background: 'transparent',
              paddingY: 'lg',
              backgroundAssetId: 'asset-1',
              backgroundFit: 'width',
            },
          }),
        ]}
        assets={{ 'asset-1': 'https://cdn.test/banner.jpg' }}
      />,
    );

    // Found by its text, which is what "searchable and translatable" means in
    // a DOM: a heading inside the bitmap would be invisible here.
    expect(screen.getByText('WATER CLOSET')).toBeInTheDocument();
  });

  it('lays a band across the top rather than zooming it to fill', () => {
    // A section is as tall as its content. A 4:1 header band told to cover is
    // magnified until only a smear of it shows, which is not what was printed.
    render(
      <CatalogueRenderer
        name="Flyer"
        sections={[
          section({
            style: {
              background: 'transparent',
              paddingY: 'lg',
              backgroundAssetId: 'asset-1',
              backgroundFit: 'width',
            },
          }),
        ]}
        assets={{ 'asset-1': 'https://cdn.test/banner.jpg' }}
      />,
    );

    const style = sectionElement().style;
    // The one-value form: full width, height from the aspect ratio.
    expect(style.backgroundSize).toBe('100%');
    expect(style.backgroundRepeat).toBe('no-repeat');
    expect(style.backgroundPosition).toContain('top');
  });

  it('fills the section when the artwork was the whole printed page', () => {
    render(
      <CatalogueRenderer
        name="Flyer"
        sections={[
          section({
            style: {
              background: 'transparent',
              paddingY: 'lg',
              backgroundAssetId: 'asset-1',
              backgroundFit: 'cover',
            },
          }),
        ]}
        assets={{ 'asset-1': 'https://cdn.test/cover.jpg' }}
      />,
    );

    expect(sectionElement().style.backgroundSize).toBe('cover');
  });

  it('renders no background when the asset could not be resolved', () => {
    // The server signs image URLs strictly, so an unsignable file arrives as an
    // ABSENT entry rather than a URL the CDN will answer 403 to. The section
    // falls back to its plain background instead of a broken picture.
    render(
      <CatalogueRenderer
        name="Flyer"
        sections={[
          section({
            style: {
              background: 'transparent',
              paddingY: 'lg',
              backgroundAssetId: 'asset-1',
              backgroundFit: 'width',
            },
          }),
        ]}
        assets={{}}
      />,
    );

    expect(sectionElement().style.backgroundImage).not.toContain('url(');
    expect(screen.getByText('WATER CLOSET')).toBeInTheDocument();
  });

  it('leaves a section with no bound artwork exactly as it was', () => {
    render(<CatalogueRenderer name="Flyer" sections={[section()]} />);

    expect(sectionElement().style.backgroundImage).not.toContain('url(');
  });
});

describe('section scroll-snap', () => {
  const SNAPPABLE = [section({ id: 'sec-1' }), section({ id: 'sec-2' })];

  it('does not snap by default, because the builder must not', () => {
    const { container } = render(<CatalogueRenderer name="Flyer" sections={SNAPPABLE} />);

    expect(container.querySelector('style')?.textContent).not.toContain('scroll-snap-type');
  });

  it('settles on a section boundary when the catalogue is published', () => {
    const { container } = render(
      <CatalogueRenderer name="Flyer" sections={SNAPPABLE} snapSections />,
    );

    const css = container.querySelector('style')?.textContent ?? '';
    expect(css).toContain('scroll-snap-type: y proximity');
    expect(css).toContain('.dk-section { scroll-snap-align: start; }');
    // Mandatory would trap a reader inside a section taller than the viewport:
    // they could never stop between its two ends.
    expect(css).not.toContain('mandatory');
  });

  it('turns snapping off for a reader who asked for reduced motion', () => {
    const { container } = render(
      <CatalogueRenderer name="Flyer" sections={SNAPPABLE} snapSections />,
    );

    const css = (container.querySelector('style')?.textContent ?? '').replace(/\s+/g, ' ');
    expect(css).toContain('@media (prefers-reduced-motion: reduce) { html { scroll-snap-type: none; } }');
  });

  it('marks every section as a snap target', () => {
    const { container } = render(
      <CatalogueRenderer name="Flyer" sections={SNAPPABLE} snapSections />,
    );

    expect(container.querySelectorAll('.dk-section')).toHaveLength(2);
  });
});
