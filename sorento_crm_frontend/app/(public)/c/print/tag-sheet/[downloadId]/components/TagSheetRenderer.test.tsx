/**
 * What the PDF actually says (AC-L.1, AC-L.6).
 *
 * The print page is DOM/CSS, so a jsdom render IS the thing Chromium prints.
 * The badge assertions here are the other half of `price-badge.test.ts`: that
 * file pins the composition, this one proves the DOM renderer uses it, so the
 * proof on screen and the PDF cannot state a price differently.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultPriceBadgeProps } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const LINE_ID = 'line-1';

function resolved(overrides: Partial<ResolvedLineData> = {}): ResolvedLineData {
  return {
    line_id: LINE_ID,
    code: 'SK-1234',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: 'Stainless steel',
    set_members: '',
    list_price: 1599,
    sell_price: 599,
    show_promo_price: true,
    included_accessories: '',
    quantity: 1,
    ...overrides,
  };
}

function layer(partial: Partial<TagLayer> & Pick<TagLayer, 'props' | 'type'>): TagLayer {
  return {
    id: 'l1',
    x_mm: 0,
    y_mm: 0,
    width_mm: 45,
    height_mm: 17,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    ...partial,
  } as TagLayer;
}

function docWith(layers: TagLayer[]): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: {
      preset: 'a4_3up',
      page_width_mm: 210,
      page_height_mm: 297,
      bleed_mm: 0,
      gap_mm: 2,
    },
    sheets: [
      {
        id: 's1',
        tags: [
          {
            id: 't1',
            template_id: 'tpl-1',
            request_line_id: LINE_ID,
            x_mm: 5,
            y_mm: 5,
            width_mm: 95,
            height_mm: 130,
            layers,
          },
        ],
      },
    ],
  };
}

describe('price_badge on the print page', () => {
  it('prints the list price alone in the list_only variant', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({ type: 'price_badge', props: defaultPriceBadgeProps('list_only') }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(screen.getByText('RM 1,599')).toBeInTheDocument();
    expect(screen.queryByText('NETT')).not.toBeInTheDocument();
  });

  it('prints the struck list price above SP RM 599 NETT in the promo variant', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({ type: 'price_badge', props: defaultPriceBadgeProps('promo') }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const struck = screen.getByText('LP: RM 1,599');
    expect(struck).toBeInTheDocument();
    expect(struck).toHaveStyle({ textDecoration: 'line-through' });
    expect(screen.getByText('SP')).toBeInTheDocument();
    expect(screen.getByText('RM 599')).toBeInTheDocument();
    expect(screen.getByText('NETT')).toBeInTheDocument();
  });

  it('keeps the pre-r4b promo sizes when the layer names no typography (r4c, AC-S6-5)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({ type: 'price_badge', props: defaultPriceBadgeProps('promo') }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    // figureSize falls back to 16pt when the layer names no fontSize; the
    // struck list price and the SP/NETT labels keep their proportion to it
    // (0.5625 and 0.5), unchanged since before typography existed.
    expect(screen.getByText('RM 599')).toHaveStyle({ fontSize: '16pt' });
    expect(screen.getByText('LP: RM 1,599')).toHaveStyle({ fontSize: '9pt' });
    expect(screen.getByText('SP')).toHaveStyle({ fontSize: '8pt' });
    expect(screen.getByText('NETT')).toHaveStyle({ fontSize: '8pt' });
  });

  it('falls back to the list price when the line turns the promo price off', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({ type: 'price_badge', props: defaultPriceBadgeProps('promo') }),
        ])}
        resolvedData={{ [LINE_ID]: resolved({ show_promo_price: false }) }}
      />,
    );

    expect(screen.getByText('RM 1,599')).toBeInTheDocument();
    expect(screen.queryByText('LP: RM 1,599')).not.toBeInTheDocument();
  });
});

describe('the price badge box on the print page (r4b, AC-S6-1/2/5)', () => {
  it('prints no box for a list-only badge saved before the flag (AC-S6-5)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({ type: 'price_badge', props: defaultPriceBadgeProps('list_only') }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(container.querySelector('svg')).toBeNull();
    expect(screen.getByText('RM 1,599')).toBeInTheDocument();
  });

  it('prints the callout as an SVG path once the layer asks for a box (AC-S6-1)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            type: 'price_badge',
            width_mm: 40,
            height_mm: 20,
            props: {
              ...defaultPriceBadgeProps('list_only'),
              showBox: true,
              fill: '#ffffff',
              textColor: '#111111',
              cornerRadius: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('viewBox')).toBe('0 0 40 20');
    const path = svg?.querySelector('path');
    expect(path?.getAttribute('d')).toBe('M 0 0 L 40 0 L 40 20 L 0 20 Z');
    expect(path?.getAttribute('fill')).toBe('#ffffff');
    expect(screen.getByText('RM 1,599')).toHaveStyle({ color: '#111111' });
  });

  it('follows the layer own corners, so the callout slants in the PDF too (AC-S6-2)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            type: 'price_badge',
            width_mm: 40,
            height_mm: 20,
            props: {
              ...defaultPriceBadgeProps('list_only'),
              showBox: true,
              cornerRadius: 0,
              points: [
                { x: 0.25, y: 0 },
                { x: 1, y: 0 },
                { x: 1, y: 1 },
                { x: 0, y: 1 },
              ],
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(container.querySelector('svg path')?.getAttribute('d')).toBe(
      'M 10 0 L 40 0 L 40 20 L 0 20 Z',
    );
  });

  it('leaves the promotional block on its rounded rectangle (AC-S6-3)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({ type: 'price_badge', props: defaultPriceBadgeProps('promo') }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(container.querySelector('svg')).toBeNull();
    expect(screen.getByText('SP')).toBeInTheDocument();
  });
});

describe('the price badge figure typography on the print page (r4b, AC-S6-4/5)', () => {
  it('sets the figure in the layer own face, size and style', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            type: 'price_badge',
            props: {
              ...defaultPriceBadgeProps('list_only'),
              fontFamily: 'Bebas Neue',
              fontSize: 22,
              fontWeight: 900,
              italic: true,
              strikethrough: true,
              align: 'left',
              letterSpacing: 0.5,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const figure = screen.getByText('RM 1,599');
    expect(figure).toHaveStyle({
      fontSize: '22pt',
      fontWeight: '900',
      fontStyle: 'italic',
      textDecoration: 'line-through',
      textAlign: 'left',
      letterSpacing: '0.5px',
    });
    // The face is set on the frame, so every part of the badge shares it.
    expect(figure.parentElement).toHaveStyle({ fontFamily: 'Bebas Neue' });
  });

  it('keeps 13pt / 700 / DM Sans for a badge that names none (AC-S6-5)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({ type: 'price_badge', props: defaultPriceBadgeProps('list_only') }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const figure = screen.getByText('RM 1,599');
    expect(figure).toHaveStyle({ fontSize: '13pt', fontWeight: '700', textAlign: 'center' });
    expect(figure.parentElement).toHaveStyle({ fontFamily: 'DM Sans, sans-serif' });
  });

  it('scales the promotional block struck price, SP and NETT with the figure', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            type: 'price_badge',
            props: { ...defaultPriceBadgeProps('promo'), fontSize: 32 },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(screen.getByText('RM 599')).toHaveStyle({ fontSize: '32pt' });
    expect(screen.getByText('LP: RM 1,599')).toHaveStyle({ fontSize: '18pt' });
    expect(screen.getByText('NETT')).toHaveStyle({ fontSize: '16pt' });
  });
});

describe('bound text and pictures on the print page', () => {
  it('resolves a slot-bound text layer against the line', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-code',
            type: 'text',
            slot_binding: 'code',
            props: {
              kind: 'text',
              text: 'placeholder',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(screen.getByText('SK-1234')).toBeInTheDocument();
    expect(screen.queryByText('placeholder')).not.toBeInTheDocument();
  });

  it('prints the typed text when the layer was unlinked', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-code',
            type: 'text',
            slot_binding: 'code',
            text_override: 'SHOWROOM',
            props: {
              kind: 'text',
              text: 'placeholder',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(screen.getByText('SHOWROOM')).toBeInTheDocument();
  });

  it('renders italic, underline and strikethrough on the printed text (AC-S2-7)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-styled',
            type: 'text',
            props: {
              kind: 'text',
              text: 'Sale',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
              italic: true,
              underline: true,
              strikethrough: true,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const el = screen.getByText('Sale');
    expect(el).toHaveStyle({ fontStyle: 'italic' });
    expect(el).toHaveStyle({ textDecoration: 'underline line-through' });
  });

  it('renders normal style and no decoration when the flags are absent (old doc, AC-S2-9)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-plain',
            type: 'text',
            props: {
              kind: 'text',
              text: 'Plain',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const el = screen.getByText('Plain');
    expect(el).toHaveStyle({ fontStyle: 'normal' });
    expect(el).toHaveStyle({ textDecoration: 'none' });
  });

  it('rotates a layer about its own top-left corner, not the CSS box centre (r4c)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-rotated',
            type: 'text',
            rotation_deg: 30,
            props: {
              kind: 'text',
              text: 'Rotated',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const el = screen.getByText('Rotated');
    expect(el).toHaveStyle({ transform: 'rotate(30deg)' });
    expect(el.style.transformOrigin).toBe('0 0');
  });

  it('leaves an unrotated layer with no transform-origin', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-flat',
            type: 'text',
            rotation_deg: 0,
            props: {
              kind: 'text',
              text: 'Flat',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    const el = screen.getByText('Flat');
    expect(el.style.transform).toBe('');
    expect(el.style.transformOrigin).toBe('');
  });

  it('draws an asset image from the payload map', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'img',
            type: 'image',
            props: {
              kind: 'image',
              source: { type: 'asset', assetId: 'a1' },
              fit: 'contain',
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
        assets={{ a1: 'https://cdn.test/a1.png' }}
      />,
    );

    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      'https://cdn.test/a1.png',
    );
  });

  it('draws a product photo from the payload map', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'img',
            type: 'image',
            props: {
              kind: 'image',
              source: { type: 'product_attachment', attachmentId: 'att-1' },
              fit: 'cover',
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
        images={{ 'att-1': 'https://cdn.test/photo.jpg' }}
      />,
    );

    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      'https://cdn.test/photo.jpg',
    );
  });

  it('draws the primary photo for a slot-bound image layer the template left unset', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'img',
            type: 'image',
            slot_binding: 'product_image',
            props: { kind: 'image', source: null, fit: 'contain' },
          }),
        ])}
        resolvedData={{
          [LINE_ID]: resolved({
            images: [
              { attachment_id: 'att-1', url: 'https://cdn.test/other.jpg', is_primary: false },
              { attachment_id: 'att-2', url: 'https://cdn.test/primary.jpg', is_primary: true },
            ],
          }),
        }}
        images={{
          'att-1': 'https://cdn.test/other.jpg',
          'att-2': 'https://cdn.test/primary.jpg',
        }}
      />,
    );

    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      'https://cdn.test/primary.jpg',
    );
  });

  it('draws the primary photo for a product_slot layer that holds the photo', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'slot',
            type: 'product_slot',
            props: { kind: 'product_slot', fieldKey: 'product_image' },
          }),
        ])}
        resolvedData={{
          [LINE_ID]: resolved({
            images: [
              { attachment_id: 'att-2', url: 'https://cdn.test/primary.jpg', is_primary: true },
            ],
          }),
        }}
        images={{ 'att-2': 'https://cdn.test/primary.jpg' }}
      />,
    );

    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      'https://cdn.test/primary.jpg',
    );
  });

  it('still draws an image layer saved before the source discriminator existed', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'img',
            type: 'image',
            // A document written by the first version of the editor.
            props: { kind: 'image', source: null, assetId: 'a1', fit: 'contain' },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
        assets={{ a1: 'https://cdn.test/legacy.png' }}
      />,
    );

    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      'https://cdn.test/legacy.png',
    );
  });
});

// ---------------------------------------------------------------------------
// Barcode layer on the print page (AC-S7-3, AC-S7-4, AC-S7-6)
// ---------------------------------------------------------------------------

describe('barcode on the print page', () => {
  // Checksum-valid, same value the browser-verification run seeds onto a
  // real ZZT- test product.
  const VALID_EAN13 = '4006381333931';

  function barcodeLayer(showCode = true): TagLayer {
    return layer({
      id: 'bc1',
      type: 'barcode',
      slot_binding: 'barcode',
      width_mm: 40,
      height_mm: 22,
      props: { kind: 'barcode', show_code: showCode },
    });
  }

  it('draws the label plate: product-code strip and guard-split human-readable digits', () => {
    render(
      <TagSheetRenderer
        doc={docWith([barcodeLayer()])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: VALID_EAN13 }) }}
        assets={{}}
        images={{}}
      />,
    );

    expect(screen.getByText('SK-1234')).toBeInTheDocument();
    // Guard-split: digit, group of 6, group of 6 - the same shape
    // `humanReadableBarcode` pins in lib/dealer-kit/barcode.test.ts, so the
    // print DOM cannot drift from the editor's own preview.
    expect(screen.getByText('4 006381 333931')).toBeInTheDocument();
  });

  it('draws the bars themselves as a real data: URL image (jsdom canvas via the `canvas` package)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([barcodeLayer()])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: VALID_EAN13 }) }}
        assets={{}}
        images={{}}
      />,
    );

    // Only one <img> on this plate: the bars. `jsbarcode` throws in stock
    // jsdom (no <canvas> 2d context); the `canvas` devDependency is what
    // makes this assertion possible instead of a permanently-untested path.
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toMatch(/^data:image\/png;base64,/);
  });

  it('omits the product-code strip when show_code is off', () => {
    render(
      <TagSheetRenderer
        doc={docWith([barcodeLayer(false)])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: VALID_EAN13 }) }}
        assets={{}}
        images={{}}
      />,
    );

    expect(screen.queryByText('SK-1234')).not.toBeInTheDocument();
    expect(screen.getByText('4 006381 333931')).toBeInTheDocument();
  });

  it('prints a Code128 value plain, with no guard split', () => {
    render(
      <TagSheetRenderer
        doc={docWith([barcodeLayer()])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: 'SKU-NOT-EAN' }) }}
        assets={{}}
        images={{}}
      />,
    );

    expect(screen.getByText('SKU-NOT-EAN')).toBeInTheDocument();
  });

  it('draws nothing at all when the line carries no barcode (AC-S7-3)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([barcodeLayer()])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: null }) }}
        assets={{}}
        images={{}}
      />,
    );

    // Not the editor's dashed placeholder - nothing, because a physical tag
    // has no business printing "no data yet" language.
    expect(container.querySelector('[style*="border-radius"]')).toBeNull();
    expect(container.textContent).not.toContain('SK-1234');
  });

  it('draws nothing for an empty-string barcode either', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([barcodeLayer()])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: '' }) }}
        assets={{}}
        images={{}}
      />,
    );

    expect(container.querySelector('[style*="border-radius"]')).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Barcode value override (D23, S9, AC-S9-2) - the print page prints the
  // designer's typed override, not the bound line's barcode, using the SAME
  // `resolveBarcodeValue` the Konva editor calls (product-block.ts).
  // ---------------------------------------------------------------------------

  it('prints the override instead of the bound barcode (AC-S9-2)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([{ ...barcodeLayer(), text_override: '111222333' }])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: VALID_EAN13 }) }}
        assets={{}}
        images={{}}
      />,
    );

    // Code128 (non-EAN), so no guard split - plain override text.
    expect(screen.getByText('111222333')).toBeInTheDocument();
    expect(screen.queryByText('4 006381 333931')).not.toBeInTheDocument();
  });

  it('prints the override even when the line carries no barcode of its own', () => {
    render(
      <TagSheetRenderer
        doc={docWith([{ ...barcodeLayer(), text_override: VALID_EAN13 }])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: null }) }}
        assets={{}}
        images={{}}
      />,
    );

    expect(screen.getByText('4 006381 333931')).toBeInTheDocument();
  });

  it('an empty override draws nothing, never falling back to a real product barcode (S5)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([{ ...barcodeLayer(), text_override: '' }])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: VALID_EAN13 }) }}
        assets={{}}
        images={{}}
      />,
    );

    expect(container.querySelector('[style*="border-radius"]')).toBeNull();
    expect(screen.queryByText('4 006381 333931')).not.toBeInTheDocument();
  });

  it('sizes the code-strip and human-readable text in pt, proportional to the plate (AC-S7-4/6)', () => {
    // A 40x22mm plate - the toolbar's default insert size. Against the BUG
    // (`Math.max(6, strip * 0.6)}mm`) this reads as a 6mm floor (~17pt): a
    // fixed, oversized font that does not move with the plate. The fix reads
    // it in pt (`MM_TO_PT`), well under 17pt and different for a differently
    // proportioned plate, which is what "proportional" asserts below.
    render(
      <TagSheetRenderer
        doc={docWith([barcodeLayer()])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: VALID_EAN13 }) }}
        assets={{}}
        images={{}}
      />,
    );

    const strip = screen.getByText('SK-1234');
    const stripFontSize = strip.style.fontSize;
    expect(stripFontSize).toMatch(/pt$/);
    expect(parseFloat(stripFontSize)).toBeLessThan(17);

    const human = screen.getByText('4 006381 333931');
    const humanFontSize = human.style.fontSize;
    expect(humanFontSize).toMatch(/pt$/);
    expect(parseFloat(humanFontSize)).toBeLessThan(17);

    // A taller plate at the same width grows the strip band, and the font
    // with it - pinning that the size is DERIVED from the plate, not a
    // constant every plate happens to clip to the same floor.
    const { container: tallerContainer } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'bc-tall',
            type: 'barcode',
            slot_binding: 'barcode',
            width_mm: 40,
            height_mm: 44,
            props: { kind: 'barcode', show_code: true },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved({ barcode: VALID_EAN13 }) }}
        assets={{}}
        images={{}}
      />,
    );
    const tallerStrip = tallerContainer.querySelectorAll('[style*="font-weight: 700"]')[0] as HTMLElement;
    expect(parseFloat(tallerStrip.style.fontSize)).toBeGreaterThan(
      parseFloat(stripFontSize),
    );
  });
});

describe('polygon shape on the print page (S4, AC-S4-6)', () => {
  it('prints an SVG path built by the same helper the canvas draws with', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'poly-1',
            type: 'shape',
            width_mm: 40,
            height_mm: 20,
            props: {
              kind: 'shape',
              shape: 'polygon',
              fill: '#ff0000',
              stroke: '#000000',
              strokeWidth: 0.5,
              cornerRadius: 0,
              points: [
                { x: 0.25, y: 0 },
                { x: 1, y: 0 },
                { x: 1, y: 1 },
                { x: 0, y: 1 },
              ],
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
        assets={{}}
        images={{}}
      />,
    );

    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
    // The viewBox is the layer's own mm box, so the path data is in mm and
    // `strokeWidth` means the same thing here as on every other shape.
    expect(svg?.getAttribute('viewBox')).toBe('0 0 40 20');
    const path = svg?.querySelector('path');
    expect(path?.getAttribute('d')).toBe('M 10 0 L 40 0 L 40 20 L 0 20 Z');
    expect(path?.getAttribute('fill')).toBe('#ff0000');
    expect(path?.getAttribute('stroke')).toBe('#000000');
    expect(path?.getAttribute('stroke-width')).toBe('0.5');
  });

  it('draws the four corners for a polygon saved without points (AC-S4-8)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'poly-2',
            type: 'shape',
            width_mm: 40,
            height_mm: 20,
            props: {
              kind: 'shape',
              shape: 'polygon',
              fill: '#ff0000',
              stroke: 'transparent',
              strokeWidth: 0,
              cornerRadius: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
        assets={{}}
        images={{}}
      />,
    );

    expect(container.querySelector('path')?.getAttribute('d')).toBe(
      'M 0 0 L 40 0 L 40 20 L 0 20 Z',
    );
  });
});

describe('padding on text and price badge layers (S3, AC-S3-1/2/3/4)', () => {
  it('adds no padding to a text layer when it is absent (AC-S3-3)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-1',
            type: 'text',
            props: {
              kind: 'text',
              text: 'Sale',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(screen.getByText('Sale')).toHaveStyle({
      padding: '0mm 0mm 0mm 0mm',
      boxSizing: 'border-box',
    });
  });

  it('prints the padding as one CSS shorthand, T R B L (AC-S3-1)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            id: 'text-1',
            type: 'text',
            props: {
              kind: 'text',
              text: 'Sale',
              fontFamily: 'DM Sans',
              fontSize: 10,
              fontWeight: 400,
              color: '#000',
              align: 'left',
              lineHeight: 1.2,
              letterSpacing: 0,
              padding: { top: 2, right: 4, bottom: 6, left: 8 },
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(screen.getByText('Sale')).toHaveStyle({
      padding: '2mm 4mm 6mm 8mm',
      boxSizing: 'border-box',
    });
  });

  it('pads the badge text container the same way, and the callout shrinks with it (AC-S3-2)', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            type: 'price_badge',
            width_mm: 40,
            height_mm: 20,
            props: {
              ...defaultPriceBadgeProps('list_only'),
              showBox: true,
              cornerRadius: 0,
              padding: { top: 0, right: 0, bottom: 0, left: 10 },
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    // 40mm less the 10mm left pad leaves 30mm of drawable width, and the
    // callout - the badge is the box (r4b, AC-S6-2) - shrinks with it.
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('viewBox')).toBe('0 0 30 20');
    expect(svg?.querySelector('path')?.getAttribute('d')).toBe('M 0 0 L 30 0 L 30 20 L 0 20 Z');

    const figure = screen.getByText('RM 1,599');
    expect(figure.parentElement).toHaveStyle({
      padding: '0mm 0mm 0mm 10mm',
      boxSizing: 'border-box',
    });
  });

  it('pads the unboxed list-only badge the same way (AC-S3-2)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            type: 'price_badge',
            props: {
              ...defaultPriceBadgeProps('list_only'),
              padding: { top: 2, right: 2, bottom: 2, left: 2 },
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    expect(screen.getByText('RM 1,599').parentElement).toHaveStyle({
      padding: '2mm 2mm 2mm 2mm',
      boxSizing: 'border-box',
    });
  });

  it('pads the promotional badge too, its filled box included (AC-S3-2)', () => {
    render(
      <TagSheetRenderer
        doc={docWith([
          layer({
            type: 'price_badge',
            props: {
              ...defaultPriceBadgeProps('promo'),
              padding: { top: 1, right: 1, bottom: 1, left: 1 },
            },
          }),
        ])}
        resolvedData={{ [LINE_ID]: resolved() }}
      />,
    );

    // amount span -> filled box div -> the padded text container.
    const content = screen.getByText('RM 599').parentElement?.parentElement;
    expect(content).toHaveStyle({ padding: '1mm 1mm 1mm 1mm', boxSizing: 'border-box' });
  });
});
