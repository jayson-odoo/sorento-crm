/**
 * PRICETAG-ACCESSORY-DESIGNER S7: the card's colour dots are the accessory's colours list, whatever the
 * pictures (owner: "only 1 picture, but the dots there are two colour"). Plan: "S7 Pictures and colours are
 * independent". Written test-FIRST (some cases may already hold; the ones that do are regression guards).
 */
import { describe, expect, it } from 'vitest';

import { boxColours, cardElementsFor } from './accessory-card';
import type { TagAccessory } from './tag-template-types';

const BLACK = { name: 'Black', hex: '#1f2937' };
const GREY = { name: 'Grey', hex: '#9ca3af' };

const ONE_PICTURE_TWO_COLOURS = {
  kind: 'accessory',
  id: 'a1',
  name: 'COLANDER',
  spec: null,
  remark: null,
  image: { attachment_id: 'p1', url: 'https://cdn.test/a.jpg' },
  images: [{ attachment_id: 'p1', url: 'https://cdn.test/a.jpg', colour_name: null, colour_hex: null }],
  colours: [BLACK, GREY],
} as unknown as TagAccessory;

const OLD_PICTURE_COLOURS_ONLY = {
  kind: 'accessory',
  id: 'a2',
  name: 'DRAINER',
  spec: null,
  remark: null,
  image: { attachment_id: 'p2', url: 'https://cdn.test/b.jpg' },
  images: [{ attachment_id: 'p2', url: 'https://cdn.test/b.jpg', colour_name: 'Gold', colour_hex: '#d4af37' }],
  colours: [],
} as unknown as TagAccessory;

const NO_PICTURE_TWO_COLOURS = { ...ONE_PICTURE_TWO_COLOURS, id: 'a3', image: null, images: [] } as unknown as TagAccessory;

const CARD = {
  width_mm: 40,
  height_mm: 30,
  elements: [
    { id: 'pic', kind: 'picture', field: 'picture', x_mm: 0, y_mm: 0, width_mm: 15, height_mm: 15 },
    { id: 'name', kind: 'text', field: 'name', x_mm: 16, y_mm: 0, width_mm: 24, height_mm: 5 },
    { id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 16, y_mm: 15, width_mm: 24, height_mm: 4 },
  ],
};

const dots = (item: TagAccessory) =>
  cardElementsFor(item, CARD as never).find((e) => e.id === 'dots');

describe('colour dots come from the colours list', () => {
  it('one picture and two colours render two dots', () => {
    expect(dots(ONE_PICTURE_TWO_COLOURS)?.colours).toEqual([BLACK.hex, GREY.hex]);
  });

  it('two colours still render with no picture at all', () => {
    expect(dots(NO_PICTURE_TWO_COLOURS)?.colours).toEqual([BLACK.hex, GREY.hex]);
    const ids = cardElementsFor(NO_PICTURE_TWO_COLOURS, CARD as never).map((e) => e.id);
    expect(ids).toEqual(['name', 'dots']);
  });

  it('a colour carried only on a picture (the old coupling) is not a dot', () => {
    expect(dots(OLD_PICTURE_COLOURS_ONLY)).toBeUndefined();
  });

  it('the picture still prints beside the dots', () => {
    const ids = cardElementsFor(ONE_PICTURE_TWO_COLOURS, CARD as never).map((e) => e.id);
    expect(ids).toEqual(['pic', 'name', 'dots']);
  });
});

describe('boxColours uses item.colours', () => {
  it('collects the colours list in order, de-duplicated across accessories', () => {
    expect(boxColours([ONE_PICTURE_TWO_COLOURS, NO_PICTURE_TWO_COLOURS])).toEqual([BLACK.hex, GREY.hex]);
  });

  it('ignores colours that only a picture carries', () => {
    expect(boxColours([OLD_PICTURE_COLOURS_ONLY])).toEqual([]);
    expect(boxColours([OLD_PICTURE_COLOURS_ONLY, ONE_PICTURE_TWO_COLOURS])).toEqual([BLACK.hex, GREY.hex]);
  });
});
