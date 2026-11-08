/**
 * Owner hand test 07/11 ("after i click done, it isn't saved eh?"): the card was saved, but while it was
 * edited the box drew two made-up sample accessories (sample black + grey dots, placeholder picture) instead
 * of the previewed list, so after Done the real accessories (no colours, two without a picture) looked like
 * a different layout. CARD V1: card 1 is the editable frame and the OTHER cards follow live; the samples are
 * for a box with no list only (CARD edge cases, A7).
 */
import { describe, expect, it } from 'vitest';
import type { CardLayout, TagAccessory } from './tag-template-types';
import {
  accessoryDesignSamples,
  accessoryEditItems,
  cardElementsFor,
  cardElementsForDesign,
} from './accessory-card';

const BOARD = {
  kind: 'accessory',
  id: 'a1',
  name: 'CHOPPING BOARD',
  spec: null,
  remark: null,
  image: null,
  images: [],
  colours: [],
} as unknown as TagAccessory;

const COLANDER = {
  kind: 'accessory',
  id: 'a2',
  name: 'COLANDER',
  spec: '390x300x140, Depth: 160mm',
  remark: null,
  image: { attachment_id: 'p2', url: 'https://cdn.test/colander.jpg' },
  images: [{ attachment_id: 'p2', url: 'https://cdn.test/colander.jpg', colour_name: null, colour_hex: null }],
  colours: [],
} as unknown as TagAccessory;

/** The owner's card: picture on top, name centred, spec under it, dots bottom-left. */
const CARD = {
  width_mm: 40,
  height_mm: 30,
  elements: [
    { id: 'pic', kind: 'picture', field: 'picture', x_mm: 10, y_mm: 1, width_mm: 20, height_mm: 12 },
    { id: 'name', kind: 'text', field: 'name', x_mm: 2, y_mm: 14, width_mm: 36, height_mm: 4, align: 'center' },
    { id: 'spec', kind: 'text', field: 'spec', x_mm: 2, y_mm: 19, width_mm: 36, height_mm: 4, align: 'center' },
    { id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 2, y_mm: 25, width_mm: 10, height_mm: 3 },
  ],
} as unknown as CardLayout;

describe('accessoryEditItems (what a box under card editing draws)', () => {
  it('draws the previewed accessories, not samples, so the faded cards show what will print', () => {
    expect(accessoryEditItems([BOARD, COLANDER])).toEqual([BOARD, COLANDER]);
  });

  it('falls back to the two design samples only when there is no list to show', () => {
    expect(accessoryEditItems(undefined)).toEqual(accessoryDesignSamples());
    expect(accessoryEditItems([])).toEqual(accessoryDesignSamples());
  });
});

describe('card 1 while editing a real accessory', () => {
  it('still shows every element where the accessory has nothing for it, so each can be placed', () => {
    const out = cardElementsForDesign(BOARD, CARD);
    expect(out.map((element) => element.id)).toEqual(['pic', 'name', 'spec', 'dots']);
    const spec = out.find((element) => element.id === 'spec')!;
    expect(spec.text).toBeTruthy();
    expect(spec.y_mm).toBe(19);
    const dots = out.find((element) => element.id === 'dots')!;
    expect(dots.colours!.length).toBeGreaterThan(0);
    expect(out.find((element) => element.id === 'name')!.text).toBe('CHOPPING BOARD');
  });

  it('the faded cards keep the print rule: the same accessory prints without the empty elements', () => {
    const printed = cardElementsFor(BOARD, CARD).map((element) => element.id);
    expect(printed).toEqual(['name']);
  });
});
