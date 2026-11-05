/**
 * PRICETAG-DESIGNER-GAPS item 1: the print page (and every preview built on
 * it) honours an image layer's flip, so a mirrored tap prints mirrored.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ImageLayerProps, TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

function resolved(): ResolvedLineData {
  return {
    tag_id: TAG_ID,
    tag_label: '1a',
    line_id: 'line-1',
    code: 'TP-1',
    name: 'Mixer Tap',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: 100,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
  } as ResolvedLineData;
}

function docWith(props: Partial<ImageLayerProps>, cropped = false): TagSheetDoc {
  const layer = {
    id: 'img',
    type: 'image',
    x_mm: 0,
    y_mm: 0,
    width_mm: 30,
    height_mm: 30,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'image',
      source: { type: 'asset', assetId: 'a1' },
      fit: 'contain',
      ...(cropped ? { cropRect: { x: 0.1, y: 0.1, width: 0.5, height: 0.5 } } : {}),
      ...props,
    },
  } as TagLayer;
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [
      {
        id: 's1',
        tags: [
          {
            id: 't1',
            template_id: 'tpl-1',
            request_tag_id: TAG_ID,
            x_mm: 5,
            y_mm: 5,
            width_mm: 95,
            height_mm: 130,
            layers: [layer],
          },
        ],
      },
    ],
  };
}

function mirrorOf(container: HTMLElement): HTMLElement | null {
  const img = container.querySelector('img');
  let node: HTMLElement | null = img;
  while (node && node !== container) {
    if (node.style.transform.includes('scale(')) return node;
    node = node.parentElement;
  }
  return null;
}

describe('TagSheetRenderer image flip', () => {
  it('prints an unflipped image with no mirror transform', () => {
    const { container } = render(
      <TagSheetRenderer doc={docWith({})} resolvedData={{ [TAG_ID]: resolved() }} assets={{ a1: 'https://cdn.test/a1.png' }} />,
    );
    expect(container.querySelector('img')).not.toBeNull();
    expect(mirrorOf(container)).toBeNull();
  });

  it('prints a flipX image mirrored left-right', () => {
    const { container } = render(
      <TagSheetRenderer doc={docWith({ flipX: true })} resolvedData={{ [TAG_ID]: resolved() }} assets={{ a1: 'https://cdn.test/a1.png' }} />,
    );
    expect(mirrorOf(container)?.style.transform).toBe('scale(-1, 1)');
  });

  it('prints a flipY image mirrored top-bottom', () => {
    const { container } = render(
      <TagSheetRenderer doc={docWith({ flipY: true })} resolvedData={{ [TAG_ID]: resolved() }} assets={{ a1: 'https://cdn.test/a1.png' }} />,
    );
    expect(mirrorOf(container)?.style.transform).toBe('scale(1, -1)');
  });

  it('mirrors a cropped image too', () => {
    const { container } = render(
      <TagSheetRenderer doc={docWith({ flipX: true }, true)} resolvedData={{ [TAG_ID]: resolved() }} assets={{ a1: 'https://cdn.test/a1.png' }} />,
    );
    expect(mirrorOf(container)?.style.transform).toBe('scale(-1, 1)');
  });
});
