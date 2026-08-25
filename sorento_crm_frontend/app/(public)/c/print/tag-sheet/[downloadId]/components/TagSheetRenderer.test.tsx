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
