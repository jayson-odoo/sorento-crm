/**
 * PRICETAG-COMBO-FORMAT R19: on a combo line the product description resolves to the COMBO's own
 * description when it has one, else the host's `price_tag_description`, through the slot, through
 * `{{product.price_tag_description}}` alone, and inside other text, with formatting kept; on canvas
 * (`layerRichBlocks`) and print (`TagSheetRenderer`) alike. A part / position subject keeps its own
 * product's description.
 *
 * Written test-FIRST: today the slot and the merge field read the host's description only.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { TagBindingData, TagLayer } from './tag-template-types';
import { layerRichBlocks, layerText } from './product-block';
import { richTextLayer, tagSheetDocWith } from './rich-text.e1.fixture';

const COMBO_HTML = '<p><strong>SRTBF11416</strong> (CABINET)</p>';
const TAG = 'tag-1';

function line(over: Record<string, unknown> = {}): ResolvedLineData {
  return {
    tag_id: TAG,
    tag_label: '1a',
    line_id: 'line-1',
    code: 'SRTBF11416',
    name: 'Cabinet',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: null,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    parts: [],
    specs: [],
    price_tag_description: '<p>host</p>',
    combo: { id: 'c1', name: '3 in 1', description: COMBO_HTML, free_items: null, choices: [], upgrades: [] },
    ...over,
  } as unknown as ResolvedLineData;
}

const binding = (l: ResolvedLineData) => ({ kind: 'line', line: l }) as unknown as TagBindingData;

function layer(slot: string | null, text: string, props: Record<string, unknown> = {}): TagLayer {
  return richTextLayer(text, { slot_binding: slot as TagLayer['slot_binding'] }, props);
}

type Seen = Array<[string, boolean]>;
const flat = (blocks: ReturnType<typeof layerRichBlocks>): Seen =>
  (blocks ?? []).flatMap((b) => b.runs).filter((r) => r.text.trim() !== '').map((r) => [r.text.trim(), !!r.bold]);

function printed(l: TagLayer, resolved: ResolvedLineData): Seen {
  const doc = tagSheetDocWith(l);
  (doc.sheets[0].tags[0] as { request_tag_id: string | null }).request_tag_id = TAG;
  const { container } = render(<TagSheetRenderer doc={doc} resolvedData={{ [TAG]: resolved }} />);
  return Array.from(container.querySelectorAll<HTMLElement>('span'))
    .filter((s) => s.childElementCount === 0 && (s.textContent ?? '').trim() !== '')
    .map((s) => [s.textContent!.trim(), s.style.fontWeight === 'bold' || Number(s.style.fontWeight) >= 600]);
}

const COMBO_RUNS: Seen = [['SRTBF11416', true], ['(CABINET)', false]];

describe.each([
  ['host has no description', null],
  ['host has a description', '<p>host</p>'],
])('combo line, %s', (_name, host) => {
  const resolved = line({ price_tag_description: host });

  it('R19 (a): the price_tag_description slot is the combo description, canvas and print', () => {
    const l = layer('price_tag_description', '');
    expect(flat(layerRichBlocks(l, binding(resolved), 'print'))).toEqual(COMBO_RUNS);
    expect(printed(l, resolved)).toEqual(COMBO_RUNS);
  });

  it('R19 (b): a layer that is exactly {{product.price_tag_description}} does the same', () => {
    const l = layer(null, '{{product.price_tag_description}}');
    expect(flat(layerRichBlocks(l, binding(resolved), 'print'))).toEqual(COMBO_RUNS);
    expect(printed(l, resolved)).toEqual(COMBO_RUNS);
  });

  it('R19 (c): Text{{product.price_tag_description}} renders blocks, formatting kept, canvas = print', () => {
    const l = layer(null, 'Text{{product.price_tag_description}}');
    const blocks = layerRichBlocks(l, binding(resolved), 'print');
    expect(blocks).not.toBeNull();
    expect(blocks![0].runs.map((r) => [r.text, !!r.bold])).toEqual([
      ['Text', false],
      ['SRTBF11416', true],
      [' (CABINET)', false],
    ]);
    expect(printed(l, resolved)).toEqual(flat(blocks));
  });

  it('R19 (f): the plain path of (c) holds the combo text and not the host\'s', () => {
    const text = layerText(layer(null, 'Text{{product.price_tag_description}}'), binding(resolved), 'print');
    expect(text).toMatch(/SRTBF11416(<\/strong>)? \(CABINET\)/);
    expect(text).not.toContain('host');
  });
});

describe('R19 fallbacks and position subjects', () => {
  it('R19 (d): a combo with NO description falls back to the host\'s price_tag_description', () => {
    const resolved = line({
      combo: { id: 'c1', name: '3 in 1', description: null, free_items: null, choices: [], upgrades: [] },
    });
    for (const l of [layer('price_tag_description', ''), layer(null, '{{product.price_tag_description}}')]) {
      expect(flat(layerRichBlocks(l, binding(resolved), 'print'))).toEqual([['host', false]]);
      expect(printed(l, resolved)).toEqual([['host', false]]);
    }
  });

  it('R19 (e): a layer whose subject is a part keeps that part\'s own description', () => {
    const resolved = line({
      slots: {
        main: { product_id: 'p1', code: 'SRTBF11416', name: 'Cabinet', images: [] },
        fixed: [
          { product_id: 'p-mirror', code: 'MIRROR', name: 'Mirror', images: [], price_tag_description: '<p>part desc</p>' },
        ],
        groups: [],
        upgrades: [],
      },
    });
    const l = layer('price_tag_description', '', { subjectSlot: { kind: 'fixed', index: 0 } });
    expect(flat(layerRichBlocks(l, binding(resolved), 'print'))).toEqual([['part desc', false]]);
    expect(printed(l, resolved)).toEqual([['part desc', false]]);
  });
});
