/**
 * COMBO-SETTINGS-UX rule 3 (owner 10 Nov, mock v2 approved): `{{combo.parts}}` prints every part of
 * the combo (the main product first, then each fixed part, then the chosen option of each pick-one
 * group) through the combo's own "Each part prints as" line, a rich template of `{{part.*}}` fields.
 * Real dev rows: SRTBF11829 + SRTMCB8083-BL (sorento_prod_1104, 10 Nov).
 */
import { describe, expect, it } from 'vitest';

import { comboPartsHtml, DEFAULT_PARTS_LINE, PART_FIELDS } from './combo-parts';
import { renderMergeFields } from './merge-fields';
import { layerRichBlocks, richBlocksWithFields } from './product-block';
import { blocksPlainText } from './rich-text';
import type { TagBindingData, TagLayer, TagPartData } from './tag-template-types';

const row = (code: string, over: Partial<TagPartData> = {}): TagPartData => ({
  product_id: `id-${code}`,
  code,
  name: code,
  dimensions: '',
  dimensions_lwh: '',
  ...over,
});

const MAIN = row('SRTBF11829', { dimensions: '780 x 480 x 400 mm', dimensions_lwh: 'L780xW480xH400mm' });
const BASIN = row('SRTWB2380');
const MIRROR = row('SRTMCB8083-BL', { dimensions: '800 x 130 x 700 mm', dimensions_lwh: 'L800xW130xH700mm' });
const TAP = row('SRTWT6203-GM', { price_tag_description: 'Basin Cold Tap\nBrass\nGunmetal' });
const WASTE = row('SRTW2600', { price_tag_description: 'Popup Waste 80mm\n(c/w Overflow)\nBrass' });

function bathroom(over: Record<string, unknown> = {}): TagBindingData {
  return {
    kind: 'line',
    line: {
      code: 'SRTBF11829',
      slots: { main: MAIN, fixed: [BASIN, MIRROR, TAP, WASTE], groups: [], upgrades: [] },
      combo: {
        id: 'c1',
        name: 'SRTBF11829 + SRTMCB8083-BL',
        description: null,
        free_items: null,
        choices: [],
        upgrades: [],
        main_label: 'CABINET',
        parts_line: null,
        part_labels: {
          'id-SRTWB2380': 'BASIN',
          'id-SRTMCB8083-BL': 'MIRROR CABINET',
          'id-SRTWT6203-GM': 'BASIN COLD TAP',
        },
        ...over,
      },
    },
  } as unknown as TagBindingData;
}

const textOf = (data: TagBindingData) => blocksPlainText(richBlocksWithFields(comboPartsHtml(data), data, 'print') ?? []);

describe('{{combo.parts}}', () => {
  it('default line: bold "CODE (LABEL)" then the LxWxH line, main first; reproduces the hand-typed description', () => {
    expect(textOf(bathroom())).toBe(
      [
        'SRTBF11829 (CABINET)',
        'L780xW480xH400mm',
        'SRTWB2380 (BASIN)',
        'SRTMCB8083-BL (MIRROR CABINET)',
        'L800xW130xH700mm',
        'SRTWT6203-GM (BASIN COLD TAP)',
        'SRTW2600',
      ].join('\n'),
    );
    const blocks = richBlocksWithFields(comboPartsHtml(bathroom()), bathroom(), 'print')!;
    expect(blocks[0].runs.every((run) => run.bold)).toBe(true);
    expect(blocks[1].runs.some((run) => run.bold)).toBe(false);
  });

  it('an empty label drops its "( )"; a line whose only field is empty is dropped', () => {
    const text = textOf(bathroom());
    expect(text).not.toContain('()');
    expect(text).not.toContain('( )');
    expect(text.split('\n')).toHaveLength(7);
  });

  it('a custom line: "- CODE (price tag description)", a multi-line description joined on one line', () => {
    const text = textOf(bathroom({ parts_line: '<p>- {{part.code}} ({{part.price_tag_description}})</p>' }));
    expect(text.split('\n')).toEqual([
      '- SRTBF11829',
      '- SRTWB2380',
      '- SRTMCB8083-BL',
      '- SRTWT6203-GM (Basin Cold Tap Brass Gunmetal)',
      '- SRTW2600 (Popup Waste 80mm (c/w Overflow) Brass)',
    ]);
  });

  it('lists only the CHOSEN option of a pick-one group, never the ones not picked', () => {
    const sink = {
      kind: 'line',
      line: {
        code: 'SRTKS7061-BL',
        slots: {
          main: row('SRTKS7061-BL'),
          fixed: [],
          groups: [{ role: 'TAP', size: 5, picks: [row('SRTKT1634SS-BL')] }],
          upgrades: [{ ...row('SRTKT1690-BL'), chosen: true }],
        },
        combo: { id: 'c2', name: 'SRTKS7061-BL', description: null, free_items: null, choices: [], upgrades: [], parts_line: '<p>{{part.code}}</p>' },
      },
    } as unknown as TagBindingData;
    expect(textOf(sink)).toBe('SRTKS7061-BL\nSRTKT1634SS-BL');
  });

  it('a value is text, never markup; a part line cannot pull in the combo parts or description again', () => {
    const data = bathroom({
      main_label: '<b>x</b>',
      parts_line: '<p>{{part.code}} {{part.label}} {{combo.parts}}{{combo.description}}</p>',
      description: '<p>{{combo.parts}}</p>',
    });
    const text = textOf(data);
    expect(text.split('\n')[0].trim()).toBe('SRTBF11829 <b>x</b>');
    expect(text).not.toContain('{{');
  });

  it('a combo with no slots, or no combo, prints nothing (never the token)', () => {
    const bare = { kind: 'line', line: { code: 'X', combo: null } } as unknown as TagBindingData;
    expect(comboPartsHtml(bare)).toBe('');
    expect(renderMergeFields('A {{combo.parts}} B', bare, 'print')).toBe('A  B');
  });

  it('a plain text layer reads it as plain lines', () => {
    expect(renderMergeFields('{{combo.parts}}', bathroom(), 'print').split('\n')[0]).toBe('SRTBF11829 (CABINET)');
  });

  it('inside the combo description (rich), the parts keep their formatting', () => {
    const data = bathroom({ description: '<p><strong>5 IN 1 BATHROOM FURNITURE</strong></p><p>{{combo.parts}}</p>' });
    const layer = {
      id: 'd', type: 'text', slot_binding: null, text_override: null,
      props: { kind: 'text', text: '{{combo.description}}' },
    } as unknown as TagLayer;
    const blocks = layerRichBlocks(layer, data, 'print')!;
    expect(blocks.map((b) => b.runs.map((r) => r.text).join(''))).toEqual([
      '5 IN 1 BATHROOM FURNITURE',
      'SRTBF11829 (CABINET)',
      'L780xW480xH400mm',
      'SRTWB2380 (BASIN)',
      'SRTMCB8083-BL (MIRROR CABINET)',
      'L800xW130xH700mm',
      'SRTWT6203-GM (BASIN COLD TAP)',
      'SRTW2600',
    ]);
    expect(blocks[1].runs.every((run) => run.bold)).toBe(true);
  });

  it('offers the part fields the owner named, and a default line', () => {
    expect(PART_FIELDS.map((f) => f.path)).toEqual([
      'part.code',
      'part.label',
      'part.name',
      'part.price_tag_description',
      'part.dimensions_lwh',
      'part.dimensions',
    ]);
    expect(DEFAULT_PARTS_LINE).toBe('<p><strong>{{part.code}} ({{part.label}})</strong></p><p>{{part.dimensions_lwh}}</p>');
  });
});
