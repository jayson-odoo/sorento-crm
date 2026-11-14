/**
 * PRICETAG-DESIGNER-FEEDBACK B2: what the print page draws.
 *
 * AC-1.7 a run's fontFamily and fontSize print exactly as the canvas (`runFace`): a 14pt Montserrat
 * word in a 7pt layer prints in Montserrat at 14 x 0.35 mm.
 * AC-1.8 accessory cards scale run sizes with the card: a card at 50% prints a 14pt run at 7pt.
 * AC-7.6 the Spec icons box lays out with `featureIconGrid` (Columns / Rows, never hide).
 * AC-8.3 hidden icons (`hiddenIconIds`) are skipped and the rest close up.
 *
 * Written test-FIRST, through the rendered page only.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { richTextLayer, tagSheetDocWith } from '@/lib/dealer-kit/rich-text.e1.fixture';
import {
  defaultAccessoriesProps,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { TEXT_MM_PER_PT } from '@/lib/dealer-kit/text-layout';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

function leafSpan(container: HTMLElement, word: string): HTMLElement {
  const span = Array.from(container.querySelectorAll<HTMLElement>('span')).find(
    (s) => s.childElementCount === 0 && s.textContent?.trim() === word,
  );
  expect(span, `a printed span "${word}"`).toBeDefined();
  return span!;
}

/** The font size a span prints at, in mm: its own, else the nearest ancestor's. */
function printedSizeMm(el: HTMLElement): number {
  let cur: HTMLElement | null = el;
  while (cur) {
    if (cur.style.fontSize) {
      expect(cur.style.fontSize.endsWith('mm'), cur.style.fontSize).toBe(true);
      return parseFloat(cur.style.fontSize);
    }
    cur = cur.parentElement;
  }
  return NaN;
}

function printedFamily(el: HTMLElement): string {
  let cur: HTMLElement | null = el;
  while (cur) {
    if (cur.style.fontFamily) return cur.style.fontFamily;
    cur = cur.parentElement;
  }
  return '';
}

function sheet(layer: TagLayer, width_mm = 148, height_mm = 105): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [
      {
        id: 's1',
        tags: [{ id: 't1', template_id: 'tpl', request_tag_id: TAG_ID, x_mm: 5, y_mm: 5, width_mm, height_mm, layers: [layer] }],
      },
    ],
  } as TagSheetDoc;
}

const spec = (key: string, value: string, raw: string) => ({ key, label: key, value, unit: null, raw });

function lineData(over: Record<string, unknown> = {}): ResolvedLineData {
  return {
    tag_id: TAG_ID, tag_label: '1a', line_id: 'l', code: 'TP-1', name: 'Mixer Tap', dimensions: '', spec_lines: '',
    set_members: '', list_price: 1, sell_price: null, show_promo_price: false, included_accessories: '', quantity: 1,
    specs: [spec('water_supply', 'Mixer', 'mixer')],
    ...over,
  } as unknown as ResolvedLineData;
}

describe('AC-1.7: a run font prints as on the canvas', () => {
  it('a 14pt Montserrat word in a 7pt layer prints in Montserrat at 14pt', () => {
    const html = '<p>plain <span style="font-family: Montserrat; font-size: 14pt">BIGWORD</span></p>';
    const { container } = render(
      <TagSheetRenderer doc={tagSheetDocWith(richTextLayer(html, {}, { fontSize: 7, fontFamily: 'DM Sans' }))} resolvedData={{}} />,
    );
    const big = leafSpan(container, 'BIGWORD');
    expect(printedFamily(big)).toContain('Montserrat');
    expect(printedSizeMm(big)).toBeCloseTo(14 * TEXT_MM_PER_PT, 4);

    const plain = leafSpan(container, 'plain');
    expect(printedFamily(plain)).not.toContain('Montserrat');
    expect(printedSizeMm(plain)).toBeCloseTo(7 * TEXT_MM_PER_PT, 4);
  });

  it('a run family alone keeps the layer size', () => {
    const html = '<p><span style="font-family: Jost">JOSTWORD</span> rest</p>';
    const { container } = render(
      <TagSheetRenderer doc={tagSheetDocWith(richTextLayer(html, {}, { fontSize: 10 }))} resolvedData={{}} />,
    );
    const word = leafSpan(container, 'JOSTWORD');
    expect(printedFamily(word)).toContain('Jost');
    expect(printedSizeMm(word)).toBeCloseTo(10 * TEXT_MM_PER_PT, 4);
  });
});

describe('AC-1.8: an accessory card scales its run sizes', () => {
  it('a card drawn at 50% prints a 14pt run at 7pt', () => {
    // Card 114 mm wide in a box whose inner width is 57 mm: one column at scale 0.5.
    const layer = {
      id: 'acc', type: 'accessories', x_mm: 0, y_mm: 0, width_mm: 60, height_mm: 80, rotation_deg: 0,
      z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
      props: {
        ...defaultAccessoriesProps(),
        showHeader: false,
        headerText: '',
        showBadge: false,
        gap_mm: 0,
        columns: 1,
        shrinkMin: 0.5,
        card: {
          width_mm: 114,
          height_mm: 20,
          elements: [
            {
              id: 'txt', kind: 'text', field: null, x_mm: 0, y_mm: 0, width_mm: 114, height_mm: 20,
              text: '<p>small <span style="font-size: 14pt">CARDBIG</span></p>', fontSize: 7,
            },
          ],
        },
      },
    } as unknown as TagLayer;
    const data = lineData({
      accessories: [{ id: 'a', name: 'COLANDER', spec: null, image: null, colours: [] } as unknown as TagAccessory],
    });
    const { container } = render(
      <TagSheetRenderer doc={sheet(layer)} resolvedData={{ [TAG_ID]: data }} assets={{}} />,
    );
    const big = leafSpan(container, 'CARDBIG');
    expect(printedSizeMm(big)).toBeCloseTo(7 * TEXT_MM_PER_PT, 4);
    const small = leafSpan(container, 'small');
    expect(printedSizeMm(small)).toBeCloseTo(3.5 * TEXT_MM_PER_PT, 4);
  });
});

const ICONS = [
  { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['mixer'] },
  { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
  { id: 'warm', name: 'Warm', spec_key: 'water_supply', values: ['mixer'] },
];
const ASSETS = { cold: 'https://cdn.test/cold.png', hot: 'https://cdn.test/hot.png', warm: 'https://cdn.test/warm.png' };

function iconsLayer(props: Record<string, unknown>, width_mm = 40, height_mm = 30): TagLayer {
  return {
    id: 'fi', type: 'feature_icons', x_mm: 3, y_mm: 4, width_mm, height_mm, rotation_deg: 0, z_index: 1,
    locked: false, visible: true, slot_binding: null, text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 2, align: 'left', ...props },
  } as unknown as TagLayer;
}

function printIcons(layer: TagLayer) {
  const extra = { featureIcons: ICONS } as Record<string, unknown>;
  const { container } = render(
    <TagSheetRenderer doc={sheet(layer, 95, 130)} resolvedData={{ [TAG_ID]: lineData() }} assets={ASSETS} {...extra} />,
  );
  return Array.from(container.querySelectorAll('img'));
}

describe('AC-7.6: the Spec icons box prints with the grid', () => {
  it('Columns 1 stacks the icons from the top, gap between rows', () => {
    const imgs = printIcons(iconsLayer({ columns: 1 }));
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Cold', 'Hot', 'Warm']);
    expect(imgs.map((i) => parseFloat(i.style.left))).toEqual([0, 0, 0]);
    expect(imgs.map((i) => parseFloat(i.style.top))).toEqual([0, 10, 20]);
  });

  it('Rows 2 puts 2 icons on the first row and 1 on the second', () => {
    const imgs = printIcons(iconsLayer({ rows: 2 }));
    expect(imgs.map((i) => parseFloat(i.style.top))).toEqual([0, 0, 10]);
    expect(imgs.map((i) => parseFloat(i.style.left))).toEqual([0, 10, 0]);
  });

  it('never hides an icon that does not fit the width: it wraps or shrinks', () => {
    // 15 mm wide: one 8 mm icon per row at full size; the old row dropped the other two.
    const imgs = printIcons(iconsLayer({}, 15, 10));
    expect(imgs).toHaveLength(3);
    for (const img of imgs) {
      expect(parseFloat(img.style.left) + parseFloat(img.style.width)).toBeLessThanOrEqual(15 + 1e-6);
      expect(parseFloat(img.style.width)).toBeGreaterThanOrEqual(4);
    }
  });
});

describe('AC-8.3: hidden icons are skipped on print', () => {
  it('a hidden icon is not printed and the rest close up', () => {
    const imgs = printIcons(iconsLayer({ hiddenIconIds: ['cold'] }));
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Hot', 'Warm']);
    expect(imgs.map((i) => parseFloat(i.style.left))).toEqual([0, 10]);
  });

  it('an empty hiddenIconIds prints them all', () => {
    const imgs = printIcons(iconsLayer({ hiddenIconIds: [] }));
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Cold', 'Hot', 'Warm']);
  });
});

describe('AC-8.2: hiding an icon is per tag (each PlacedTag has its own layer copy)', () => {
  it('tag A hides Cold, tag B of the same template still prints it', () => {
    const layerA = iconsLayer({ hiddenIconIds: ['cold'] });
    const layerB = iconsLayer({});
    const doc = {
      kind: 'tag_sheet',
      imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
      sheets: [
        {
          id: 's1',
          tags: [
            { id: 'tA', template_id: 'tpl', request_tag_id: 'rt-A', x_mm: 5, y_mm: 5, width_mm: 95, height_mm: 60, layers: [layerA] },
            { id: 'tB', template_id: 'tpl', request_tag_id: 'rt-B', x_mm: 105, y_mm: 5, width_mm: 95, height_mm: 60, layers: [layerB] },
          ],
        },
      ],
    } as TagSheetDoc;
    const extra = { featureIcons: ICONS } as Record<string, unknown>;
    const { container } = render(
      <TagSheetRenderer
        doc={doc}
        resolvedData={{ 'rt-A': lineData({ tag_id: 'rt-A' }), 'rt-B': lineData({ tag_id: 'rt-B' }) }}
        assets={ASSETS}
        {...extra}
      />,
    );
    const alts = Array.from(container.querySelectorAll('img')).map((i) => i.getAttribute('alt'));
    // Tag A: Hot, Warm. Tag B: Cold, Hot, Warm.
    expect(alts.filter((a) => a === 'Cold')).toHaveLength(1);
    expect(alts.filter((a) => a === 'Hot')).toHaveLength(2);
    expect(alts).toHaveLength(5);
    // The tag props were not shared: B's own copy still has nothing hidden.
    expect((layerB.props as { hiddenIconIds?: string[] }).hiddenIconIds).toBeUndefined();
  });
});
