/**
 * COMBO-SETTINGS-UX owner ruling 10 Nov 20:1x: ONE description box. Each part's fields are tied to
 * the PART (its product), never its position, so reordering parts never moves text to another part;
 * a part removed later prints blank. A choice group (2+ parts) is ONE entry that prints whichever
 * option is chosen. `{{combo.parts}}` (with a stored part line) keeps printing exactly as before.
 */
import { describe, expect, it } from 'vitest';

import {
  allPartsHtml,
  groupRef,
  partChipLabel,
  partFieldCatalog,
  partRef,
  type ComboPartLike,
} from './combo-part-fields';
import { comboPartsHtml } from './combo-parts';
import { renderMergeFields } from './merge-fields';
import { richBlocksWithFields } from './product-block';
import { blocksPlainText } from './rich-text';
import type { TagBindingData, TagPartData } from './tag-template-types';

const A = '11111111-1111-1111-1111-111111111111';
const B = '22222222-2222-2222-2222-222222222222';
const T1 = '33333333-3333-3333-3333-333333333333';
const T2 = '44444444-4444-4444-4444-444444444444';
const HOST = '55555555-5555-5555-5555-555555555555';

const row = (product_id: string, code: string, over: Partial<TagPartData> = {}): TagPartData => ({
  product_id, code, name: code, dimensions: '', dimensions_lwh: '', ...over,
});

function line(fixed: TagPartData[], picks: TagPartData[] = [], extra: Record<string, unknown> = {}): TagBindingData {
  return {
    kind: 'line',
    line: {
      code: 'SRTBF11829',
      slots: {
        main: row(HOST, 'SRTBF11829', { dimensions_lwh: 'L780xW480xH400mm', price_tag_description: 'old combo text' }),
        fixed,
        groups: [{ role: 'TAP', size: 2, picks }],
        upgrades: [],
      },
      combo: {
        id: 'c', name: 'BF', description: null, free_items: null, upgrades: [],
        choices: [{ role: 'TAP', options: [
          { product_id: T1, code: 'SRTKT1633SS-BL', description: '', list_price: null, sell_price: 899, picked: false },
          { product_id: T2, code: 'SRTKT71SS-BL', description: '', list_price: null, sell_price: 1099, picked: true },
        ] }],
        main_label: 'CABINET',
        part_labels: { [A]: 'BASIN', [B]: 'MIRROR CABINET' },
        ...extra,
      },
    },
  } as unknown as TagBindingData;
}

const BASIN = row(A, 'SRTWB2380');
const MIRROR = row(B, 'SRTMCB8083-BL', { dimensions_lwh: 'L800xW130xH700mm' });
const field = (token: string, data: TagBindingData) => renderMergeFields(token, data, 'print');

describe('per-part fields, tied to the part', () => {
  it('reordering the parts keeps each text on its own part', () => {
    const token = `{{${partRef(A)}.label}} {{${partRef(B)}.code}}`;
    expect(field(token, line([BASIN, MIRROR]))).toBe('BASIN SRTMCB8083-BL');
    expect(field(token, line([MIRROR, BASIN]))).toBe('BASIN SRTMCB8083-BL');
  });

  it('a part removed from the combo prints blank, never another part', () => {
    expect(field(`[{{${partRef(B)}.code}}]`, line([BASIN]))).toBe('[]');
  });

  it('the main product reads its own label, code, dimensions and price tag description', () => {
    const data = line([BASIN]);
    expect(field('{{part.main.code}} ({{part.main.label}}) {{part.main.dimensions_lwh}}', data)).toBe(
      'SRTBF11829 (CABINET) L780xW480xH400mm',
    );
    expect(field('{{part.main.price_tag_description}}', data)).toBe('old combo text');
  });

  it('a choice group prints whichever option is chosen, with its sell price if picked', () => {
    const tap = groupRef('TAP');
    expect(field(`{{${tap}.code}} {{${tap}.sell_price}}`, line([BASIN], [row(T2, 'SRTKT71SS-BL')]))).toBe(
      'SRTKT71SS-BL 1,099',
    );
    // Nothing chosen yet: blank.
    expect(field(`[{{${tap}.code}}]`, line([BASIN], []))).toBe('[]');
  });

  it('refs are plain token characters (no dashes, spaces or braces)', () => {
    expect(partRef(A)).toMatch(/^part\.[a-f0-9]{32}$/);
    expect(groupRef('Basin colour')).toMatch(/^group\.[a-f0-9]+$/);
  });
});

const COMBO_PARTS: ComboPartLike[] = [
  { product_id: A, code: 'SRTWB2380', label: 'BASIN', choice_group: null },
  { product_id: B, code: 'SRTMCB8083-BL', label: null, choice_group: 'Mirror' },
  { product_id: T1, code: 'SRTKT1633SS-BL', label: null, choice_group: 'TAP' },
  { product_id: T2, code: 'SRTKT71SS-BL', label: null, choice_group: 'TAP' },
];

describe('the Parts group of Insert field', () => {
  it('lists the main product and each part by name, a one-part group as a plain part, a choice group once', () => {
    const fields = partFieldCatalog(COMBO_PARTS, { code: 'SRTBF11829', label: 'CABINET' });
    const owners = [...new Set(fields.map((f) => f.label.split(': ')[0]))];
    expect(owners).toEqual([
      'All parts (one line each)',
      'CABINET - SRTBF11829',
      'BASIN - SRTWB2380',
      'SRTMCB8083-BL',
      'TAP (picked)',
    ]);
    expect(fields.every((f) => f.group === 'Parts')).toBe(true);
    const basin = fields.filter((f) => f.label.startsWith('BASIN - SRTWB2380: ')).map((f) => f.label.split(': ')[1]);
    expect(basin).toEqual(['code', 'label', 'name', 'dimensions (LxWxH)', 'price tag description', 'list price']);
    const tap = fields.filter((f) => f.label.startsWith('TAP (picked): ')).map((f) => f.label.split(': ')[1]);
    expect(tap).toContain('sell price (if picked)');
  });

  it('"All parts" drops one editable line per part: bold "code (label)" then the dimensions', () => {
    const html = allPartsHtml(COMBO_PARTS, { code: 'SRTBF11829', label: 'CABINET' });
    expect(html).toBe(
      [
        '<p><strong>{{part.main.code}} ({{part.main.label}})</strong></p><p>{{part.main.dimensions_lwh}}</p>',
        `<p><strong>{{${partRef(A)}.code}} ({{${partRef(A)}.label}})</strong></p><p>{{${partRef(A)}.dimensions_lwh}}</p>`,
        // No label on record: the code alone, so no "( )" is printed.
        `<p><strong>{{${partRef(B)}.code}}</strong></p><p>{{${partRef(B)}.dimensions_lwh}}</p>`,
        `<p><strong>{{${groupRef('TAP')}.code}}</strong></p><p>{{${groupRef('TAP')}.dimensions_lwh}}</p>`,
      ].join(''),
    );
  });

  it('prints each line with real values; an empty dimension line is dropped', () => {
    const html = allPartsHtml(COMBO_PARTS.slice(0, 1), { code: 'SRTBF11829', label: 'CABINET' });
    const text = blocksPlainText(richBlocksWithFields(html, line([BASIN]), 'print') ?? []);
    expect(text).toBe('SRTBF11829 (CABINET)\nL780xW480xH400mm\nSRTWB2380 (BASIN)');
  });
});

describe('chips name the part', () => {
  it('names a part field by the part, a removed part as removed', () => {
    const main = { code: 'SRTBF11829', label: 'CABINET' };
    expect(partChipLabel(`${partRef(A)}.code`, COMBO_PARTS, main)).toBe('BASIN - SRTWB2380: code');
    expect(partChipLabel('part.main.label', COMBO_PARTS, main)).toBe('CABINET - SRTBF11829: label');
    expect(partChipLabel(`${groupRef('TAP')}.code`, COMBO_PARTS, main)).toBe('TAP (picked): code');
    expect(partChipLabel(`${partRef('99999999-9999-9999-9999-999999999999')}.code`, COMBO_PARTS, main)).toBe(
      'Removed part: code',
    );
    expect(partChipLabel(`${groupRef('Gone')}.code`, COMBO_PARTS, main)).toBe('Removed group "Gone": code');
    expect(partChipLabel('combo.name', COMBO_PARTS, main)).toBeNull();
  });
});

describe('legacy {{combo.parts}}', () => {
  it('prints exactly as before with a stored part line', () => {
    const data = line([BASIN, MIRROR], [], { parts_line: '<p>- {{part.code}} ({{part.label}})</p>' });
    expect(blocksPlainText(richBlocksWithFields(comboPartsHtml(data), data, 'print') ?? [])).toBe(
      ['- SRTBF11829 (CABINET)', '- SRTWB2380 (BASIN)', '- SRTMCB8083-BL (MIRROR CABINET)'].join('\n'),
    );
  });
});
