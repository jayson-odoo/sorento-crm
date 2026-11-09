/**
 * PRICETAG-ACCESSORY-DESIGNER S6 "Hide when empty": picture, name, spec, remark and colour dots each
 * hide for an accessory with no value (V7). Proven on a layout as authored AND after it went through
 * JSON.stringify / parse (the saved doc form: the bug that lost the layout after Done hid this).
 */
import { describe, expect, it } from 'vitest';

import { cardElementsFor } from './accessory-card';
import type { TagAccessory } from './tag-template-types';

const BLACK = { name: 'Black', hex: '#1f2937' };
const GREY = { name: 'Grey', hex: '#9ca3af' };

const CHOPPING_BOARD = {
  kind: 'accessory', id: 'a1', name: 'CHOPPING BOARD', spec: null, remark: null, image: null, images: [], colours: [],
} as unknown as TagAccessory;

const PICTURED = (id: string, name: string) =>
  ({
    kind: 'accessory',
    id,
    name,
    spec: '390x200x140 / Depth: 160mm',
    remark: 'Colour follows sink',
    image: { attachment_id: 'p1', url: 'https://cdn.test/a.jpg' },
    images: [
      { attachment_id: 'p1', url: 'https://cdn.test/a.jpg', colour_name: 'Black', colour_hex: BLACK.hex },
      { attachment_id: 'p2', url: 'https://cdn.test/b.jpg', colour_name: 'Grey', colour_hex: GREY.hex },
    ],
    colours: [BLACK, GREY],
  }) as unknown as TagAccessory;

const COLANDER = PICTURED('a2', 'COLANDER');
const DRAINER = PICTURED('a3', 'DRAINER');
const LEGACY_IMAGE_ONLY = {
  kind: 'accessory', id: 'a4', name: 'PULL OUT DRAINER', spec: null, remark: null,
  image: { attachment_id: 'p9', url: 'https://cdn.test/pull.jpg' }, images: [], colours: [],
} as unknown as TagAccessory;

const LAYOUT = {
  width_mm: 40,
  height_mm: 30,
  elements: [
    { id: 'pic', kind: 'picture', field: 'picture', x_mm: 0, y_mm: 0, width_mm: 15, height_mm: 15 },
    { id: 'name', kind: 'text', field: 'name', x_mm: 16, y_mm: 0, width_mm: 24, height_mm: 5 },
    { id: 'spec', kind: 'text', field: 'spec', x_mm: 16, y_mm: 6, width_mm: 24, height_mm: 6 },
    { id: 'remark', kind: 'text', field: 'remark', x_mm: 16, y_mm: 13, width_mm: 24, height_mm: 4 },
    { id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 16, y_mm: 18, width_mm: 24, height_mm: 4 },
  ],
};

const forms: [string, typeof LAYOUT][] = [
  ['as authored', LAYOUT],
  ['after a JSON round trip (the saved doc)', JSON.parse(JSON.stringify(LAYOUT))],
];

const ids = (item: TagAccessory, layout: typeof LAYOUT) =>
  cardElementsFor(item, layout as never).map((e) => e.id);

describe.each(forms)('hide when empty, layout %s', (_label, layout) => {
  it('CHOPPING BOARD (no image, no spec, no remark, no colours) shows only its name', () => {
    expect(ids(CHOPPING_BOARD, layout)).toEqual(['name']);
  });

  it('COLANDER shows every element', () => {
    expect(ids(COLANDER, layout)).toEqual(['pic', 'name', 'spec', 'remark', 'dots']);
  });

  it('DRAINER shows every element', () => {
    expect(ids(DRAINER, layout)).toEqual(['pic', 'name', 'spec', 'remark', 'dots']);
  });

  it('an accessory with images [] but a legacy `image` still shows its picture', () => {
    const out = cardElementsFor(LEGACY_IMAGE_ONLY, layout as never);
    expect(out.map((e) => e.id)).toEqual(['pic', 'name']);
    expect(out.find((e) => e.id === 'pic')?.src).toBe('https://cdn.test/pull.jpg');
  });

  it('resolves the values it prints', () => {
    const out = cardElementsFor(COLANDER, layout as never);
    expect(out.find((e) => e.id === 'name')?.text).toBe('COLANDER');
    expect(out.find((e) => e.id === 'spec')?.text).toBe('390x200x140 / Depth: 160mm');
    expect(out.find((e) => e.id === 'remark')?.text).toBe('Colour follows sink');
    expect(out.find((e) => e.id === 'dots')?.colours).toEqual([BLACK.hex, GREY.hex]);
    expect(out.find((e) => e.id === 'pic')?.src).toBe('https://cdn.test/a.jpg');
  });

  it('a blank spec and an empty rich remark hide their elements', () => {
    const blank = { ...COLANDER, spec: '   ', remark: '<p></p>' } as unknown as TagAccessory;
    expect(ids(blank, layout)).toEqual(['pic', 'name', 'dots']);
  });
});
