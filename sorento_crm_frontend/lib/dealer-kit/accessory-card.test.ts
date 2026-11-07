/**
 * PRICETAG-ACCESSORY-DESIGNER S2: the ONE card layout rule for an "Accessories" box that has a `card`
 * (canvas, request preview and print all call it, card rule A10).
 *
 * Plan: documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md "S2 Frontend lib contract".
 * Card rules V6-V9: one card layout per box, applied to every accessory; an empty field does not print
 * and the slot under it moves up; the box shrinks together to 70%, then whole cards only.
 *
 * Written test-FIRST: `./accessory-card` does not exist yet. The legacy path (`accessory-box.ts`) is
 * covered by `accessory-box.test.ts` and must not change.
 *
 * Assumed result shapes where the plan names none: `cardElementsFor` returns the visible elements with
 * the same id / kind / field, the final rect in `x_mm,y_mm,width_mm,height_mm`, a resolved `text` for
 * text elements and a resolved `colours: string[]` (hex) for colour dots.
 */
import { describe, expect, it } from 'vitest';

import {
  accessoryDesign,
  applyAccessoryDesign,
  boxColours,
  cardBoxLayout,
  cardElementsFor,
  cardFieldValue,
  cardFromLegacy,
} from './accessory-card';
import { accessoryBoxLayout } from './accessory-box';
import { formatTagPrice } from './price-badge';
import {
  defaultAccessoriesProps,
  type AccessoriesLayerProps,
  type TagAccessory,
} from './tag-template-types';

const BLACK = { name: 'Black', hex: '#1f2937' };
const GREY = { name: 'Grey', hex: '#9ca3af' };

// The owner's real examples (SRTKS7846).
const CHOPPING_BOARD = {
  kind: 'accessory',
  id: 'a1',
  name: 'CHOPPING BOARD',
  spec: null,
  remark: null,
  image: { attachment_id: 'p1', url: 'https://cdn.test/board.jpg' },
  images: [{ attachment_id: 'p1', url: 'https://cdn.test/board.jpg', colour_name: null, colour_hex: null }],
  colours: [],
} as unknown as TagAccessory;

const COLANDER = {
  kind: 'accessory',
  id: 'a2',
  name: 'COLANDER',
  spec: '390x200x140 / Depth: 160mm',
  remark: null,
  image: { attachment_id: 'p2', url: 'https://cdn.test/colander-black.jpg' },
  images: [
    { attachment_id: 'p2', url: 'https://cdn.test/colander-black.jpg', colour_name: 'Black', colour_hex: BLACK.hex },
    { attachment_id: 'p3', url: 'https://cdn.test/colander-grey.jpg', colour_name: 'Grey', colour_hex: GREY.hex },
  ],
  colours: [BLACK, GREY],
} as unknown as TagAccessory;

const DRAINER = { ...COLANDER, id: 'a3', name: 'DRAINER' } as unknown as TagAccessory;

const WASTE = {
  kind: 'product',
  id: 'p9',
  code: 'SRTW5000',
  name: 'Pop-up waste 80mm, brass',
  spec: null,
  remark: null,
  image: null,
  images: [],
  colours: [],
  list_price: 68,
} as unknown as TagAccessory;

type El = Record<string, unknown>;

/** The card used by most tests: picture left, name + spec right, dots under, a fixed note at the bottom. */
function card(extra: El[] = []) {
  return {
    width_mm: 40,
    height_mm: 30,
    elements: [
      { id: 'pic', kind: 'picture', field: 'picture', x_mm: 0, y_mm: 0, width_mm: 15, height_mm: 15 },
      { id: 'name', kind: 'text', field: 'name', x_mm: 16, y_mm: 0, width_mm: 24, height_mm: 5 },
      { id: 'spec', kind: 'text', field: 'spec', x_mm: 16, y_mm: 6, width_mm: 24, height_mm: 8 },
      { id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 16, y_mm: 15, width_mm: 24, height_mm: 4 },
      { id: 'note', kind: 'text', field: null, text: 'Note', x_mm: 16, y_mm: 20, width_mm: 24, height_mm: 5 },
      ...extra,
    ],
  } as unknown as NonNullable<AccessoriesLayerProps['card']>;
}

function boxProps(over: Record<string, unknown> = {}): AccessoriesLayerProps {
  return {
    ...defaultAccessoriesProps(),
    showHeader: false,
    headerText: '',
    showBadge: false,
    gap_mm: 0,
    card: { width_mm: 30, height_mm: 20, elements: [] },
    ...over,
  } as AccessoriesLayerProps;
}

const byId = (list: El[], id: string) => list.find((e) => e.id === id);

// ---------------------------------------------------------------------------
// cardBoxLayout
// ---------------------------------------------------------------------------

describe('cardBoxLayout', () => {
  it('draws 3 cards at scale 1 when they fit, stacked at the pad, closing the box up from the bottom', () => {
    const out = cardBoxLayout(3, boxProps(), 60, 70);
    expect(out.scale).toBe(1);
    expect(out.shown).toBe(3);
    expect(out.dropped).toBe(0);
    expect(out.cards).toHaveLength(3);
    expect(out.cards[0]).toMatchObject({ x_mm: 1.5, y_mm: 1.5, width_mm: 30, height_mm: 20 });
    expect(out.cards[1].y_mm).toBeCloseTo(21.5);
    expect(out.cards[2].y_mm).toBeCloseTo(41.5);
    expect(out.boxWidth_mm).toBe(60);
    expect(out.boxHeight_mm).toBeCloseTo(63);
    expect(out.footer).toBeNull();
  });

  it('shrinks every card by the same factor when the box is tighter, keeping all 3', () => {
    const out = cardBoxLayout(3, boxProps(), 60, 56);
    expect(out.scale).toBeGreaterThan(0.7);
    expect(out.scale).toBeLessThan(1);
    expect(out.scale).toBeCloseTo(53 / 60);
    expect(out.shown).toBe(3);
    expect(out.dropped).toBe(0);
    for (const c of out.cards) {
      expect(c.width_mm).toBeCloseTo(30 * out.scale);
      expect(c.height_mm).toBeCloseTo(20 * out.scale);
    }
    expect(out.boxHeight_mm).toBeLessThanOrEqual(56 + 1e-6);
  });

  it('stops at exactly 70% and keeps whole cards only, counting the dropped', () => {
    const out = cardBoxLayout(3, boxProps(), 60, 40);
    expect(out.scale).toBe(0.7);
    expect(out.shown).toBe(2);
    expect(out.dropped).toBe(1);
    expect(out.cards).toHaveLength(2);
    expect(out.cards[0].height_mm).toBeCloseTo(14);
    // closes up around the 2 cards that print: 1.5 + 2 * 14 + 1.5
    expect(out.boxHeight_mm).toBeCloseTo(31);
  });

  it('honours a different shrinkMin', () => {
    const out = cardBoxLayout(3, boxProps({ shrinkMin: 0.5 }), 60, 40);
    expect(out.scale).toBeCloseTo(37 / 60);
    expect(out.scale).toBeGreaterThanOrEqual(0.5);
    expect(out.shown).toBe(3);
  });

  it('runs horizontal boxes left to right and shrinks together on width', () => {
    const fits = cardBoxLayout(3, boxProps({ direction: 'horizontal', card: { width_mm: 20, height_mm: 20, elements: [] } }), 70, 40);
    expect(fits.scale).toBe(1);
    expect(fits.cards.map((c) => c.x_mm)).toEqual([1.5, 21.5, 41.5]);
    expect(fits.cards.every((c) => c.y_mm === 1.5)).toBe(true);
    expect(fits.boxWidth_mm).toBeCloseTo(63);

    const tight = cardBoxLayout(3, boxProps({ direction: 'horizontal', card: { width_mm: 20, height_mm: 20, elements: [] } }), 53, 40);
    expect(tight.scale).toBeCloseTo(50 / 60);
    expect(tight.shown).toBe(3);
    expect(tight.cards[0].height_mm).toBeCloseTo(20 * tight.scale);

    const tiny = cardBoxLayout(3, boxProps({ direction: 'horizontal', card: { width_mm: 20, height_mm: 20, elements: [] } }), 35, 40);
    expect(tiny.scale).toBe(0.7);
    expect(tiny.dropped).toBeGreaterThan(0);
    expect(tiny.shown + tiny.dropped).toBe(3);
  });

  it('puts the footer under the cards at its own height, unscaled, full inner width', () => {
    const props = boxProps({ footer: { show: true, height_mm: 6, elements: [] } });
    const out = cardBoxLayout(3, props, 60, 80);
    expect(out.footer).not.toBeNull();
    expect(out.footer).toMatchObject({ x_mm: 1.5, height_mm: 6 });
    expect(out.footer!.width_mm).toBeCloseTo(57);
    expect(out.footer!.y_mm).toBeCloseTo(1.5 + 60);
    expect(out.boxHeight_mm).toBeCloseTo(1.5 + 60 + 6 + 1.5);
  });

  it('draws no footer when footer.show is false', () => {
    const out = cardBoxLayout(3, boxProps({ footer: { show: false, height_mm: 6, elements: [] } }), 60, 80);
    expect(out.footer).toBeNull();
    expect(out.boxHeight_mm).toBeCloseTo(63);
  });

  it('makes room for the footer before shrinking the cards', () => {
    const props = boxProps({ footer: { show: true, height_mm: 6, elements: [] } });
    const out = cardBoxLayout(3, props, 60, 63);
    expect(out.scale).toBeLessThan(1);
    expect(out.footer!.height_mm).toBe(6);
    expect(out.boxHeight_mm).toBeLessThanOrEqual(63 + 1e-6);
  });

  it('draws nothing for 0 items', () => {
    const out = cardBoxLayout(0, boxProps({ footer: { show: true, height_mm: 6, elements: [] } }), 60, 80);
    expect(out.cards).toEqual([]);
    expect(out.shown).toBe(0);
    expect(out.dropped).toBe(0);
    expect(out.boxWidth_mm).toBe(0);
    expect(out.boxHeight_mm).toBe(0);
    expect(out.frame).toBeNull();
    expect(out.header).toBeNull();
    expect(out.footer).toBeNull();
  });

  it('keeps the frame and header geometry exactly as the legacy box', () => {
    const props = boxProps({ showHeader: true, headerText: 'ACCESSORIES INCLUDED', headerOnBorder: true });
    const card1 = cardBoxLayout(2, props, 60, 80);
    const legacy = accessoryBoxLayout(2, props, 60, 80);
    expect(card1.header).toEqual(legacy.header);
    expect(card1.frame!.x_mm).toBe(legacy.frame!.x_mm);
    expect(card1.frame!.y_mm).toBe(legacy.frame!.y_mm);
    expect(card1.frame!.width_mm).toBe(legacy.frame!.width_mm);
    expect(card1.badge).toEqual(legacy.badge);
  });
});

// ---------------------------------------------------------------------------
// cardElementsFor
// ---------------------------------------------------------------------------

describe('cardElementsFor', () => {
  it('prints everything for COLANDER, at the designed positions, with resolved content', () => {
    const out = cardElementsFor(COLANDER, card()) as unknown as El[];
    expect(out.map((e) => e.id)).toEqual(['pic', 'name', 'spec', 'dots', 'note']);
    expect(byId(out, 'name')).toMatchObject({ text: 'COLANDER', y_mm: 0 });
    expect(byId(out, 'spec')).toMatchObject({ text: '390x200x140 / Depth: 160mm', y_mm: 6 });
    expect(byId(out, 'dots')).toMatchObject({ colours: [BLACK.hex, GREY.hex], y_mm: 15 });
    expect(byId(out, 'note')).toMatchObject({ text: 'Note', y_mm: 20 });
    expect(byId(out, 'pic')).toMatchObject({ x_mm: 0, y_mm: 0, width_mm: 15, height_mm: 15 });
  });

  it('prints the same for DRAINER (one layout for every accessory, V6)', () => {
    const out = cardElementsFor(DRAINER, card()) as unknown as El[];
    expect(out.map((e) => e.id)).toEqual(['pic', 'name', 'spec', 'dots', 'note']);
    expect(byId(out, 'name')).toMatchObject({ text: 'DRAINER' });
  });

  it('drops the spec and the dots for CHOPPING BOARD and closes the gap under them (V7)', () => {
    const out = cardElementsFor(CHOPPING_BOARD, card()) as unknown as El[];
    expect(out.map((e) => e.id)).toEqual(['pic', 'name', 'note']);
    expect(byId(out, 'name')).toMatchObject({ text: 'CHOPPING BOARD', y_mm: 0 });
    // the note sat at 20; the spec (top 6, bottom 14) and then the dots (now at 6..10) left: it ends at 6
    expect(byId(out, 'note')!.y_mm).toBeCloseTo(6);
    expect(byId(out, 'pic')).toMatchObject({ y_mm: 0 });
  });

  it('moves an element up by (nearest below top - dropped top), only when the spans overlap horizontally', () => {
    const simple = {
      width_mm: 40,
      height_mm: 30,
      elements: [
        { id: 'spec', kind: 'text', field: 'spec', x_mm: 16, y_mm: 6, width_mm: 24, height_mm: 8 },
        { id: 'below', kind: 'text', field: null, text: 'B', x_mm: 20, y_mm: 16, width_mm: 10, height_mm: 4 },
        { id: 'beside', kind: 'text', field: null, text: 'S', x_mm: 0, y_mm: 16, width_mm: 10, height_mm: 4 },
      ],
    } as unknown as NonNullable<AccessoriesLayerProps['card']>;
    const out = cardElementsFor(CHOPPING_BOARD, simple) as unknown as El[];
    expect(out.map((e) => e.id)).toEqual(['below', 'beside']);
    expect(byId(out, 'below')!.y_mm).toBeCloseTo(6); // 16 - (16 - 6)
    expect(byId(out, 'beside')!.y_mm).toBe(16); // different column, stays
  });

  it('never changes the card size (v3 Q1 (a))', () => {
    const c = card();
    cardElementsFor(CHOPPING_BOARD, c);
    expect(c.width_mm).toBe(40);
    expect(c.height_mm).toBe(30);
  });

  it('drops a hidden element without moving anything else', () => {
    const c = card();
    (c.elements as unknown as El[]).find((e) => e.id === 'spec')!.hidden = true;
    const out = cardElementsFor(COLANDER, c) as unknown as El[];
    expect(out.map((e) => e.id)).toEqual(['pic', 'name', 'dots', 'note']);
    expect(byId(out, 'dots')!.y_mm).toBe(15);
    expect(byId(out, 'note')!.y_mm).toBe(20);
  });

  it('drops a picture element when the accessory has no picture, and a blank text', () => {
    const noPicture = { ...COLANDER, image: null, images: [] } as unknown as TagAccessory;
    expect((cardElementsFor(noPicture, card()) as unknown as El[]).map((e) => e.id)).not.toContain('pic');
    const blank = { ...COLANDER, name: '   ' } as unknown as TagAccessory;
    expect((cardElementsFor(blank, card()) as unknown as El[]).map((e) => e.id)).not.toContain('name');
  });

  it('keeps dots whose colours are hand-picked even when the accessory has none', () => {
    const c = card();
    (c.elements as unknown as El[]).find((e) => e.id === 'dots')!.colours = ['#d4af37'];
    const out = cardElementsFor(CHOPPING_BOARD, c) as unknown as El[];
    expect(byId(out, 'dots')).toMatchObject({ colours: ['#d4af37'] });
  });

  it('prints the price as "LP: RM 68" for a product entry and drops it for a library accessory', () => {
    const c = card([{ id: 'price', kind: 'text', field: 'price', x_mm: 16, y_mm: 26, width_mm: 24, height_mm: 4 }]);
    const product = cardElementsFor(WASTE, c) as unknown as El[];
    expect(byId(product, 'price')!.text).toBe(`LP: ${formatTagPrice(68)}`);
    expect(String(byId(product, 'price')!.text)).toContain('RM 68');
    const library = cardElementsFor(COLANDER, c) as unknown as El[];
    expect(library.map((e) => e.id)).not.toContain('price');
  });

  it('prints the code field for a product entry and drops it for a library accessory', () => {
    const c = card([{ id: 'code', kind: 'text', field: 'code', x_mm: 16, y_mm: 26, width_mm: 24, height_mm: 4 }]);
    expect(byId(cardElementsFor(WASTE, c) as unknown as El[], 'code')!.text).toBe('SRTW5000');
    expect((cardElementsFor(COLANDER, c) as unknown as El[]).map((e) => e.id)).not.toContain('code');
  });

  it('prints the remark field and drops it when blank', () => {
    const c = card([{ id: 'remark', kind: 'text', field: 'remark', x_mm: 16, y_mm: 26, width_mm: 24, height_mm: 4 }]);
    const withRemark = { ...COLANDER, remark: 'Colour follows sink' } as unknown as TagAccessory;
    expect(byId(cardElementsFor(withRemark, c) as unknown as El[], 'remark')!.text).toBe('Colour follows sink');
    expect((cardElementsFor(COLANDER, c) as unknown as El[]).map((e) => e.id)).not.toContain('remark');
  });

  it('keeps a fixed-text element and a shape whatever the accessory holds', () => {
    const c = card([{ id: 'rule', kind: 'shape', shape: 'line', x_mm: 0, y_mm: 27, width_mm: 40, height_mm: 0.2 }]);
    const out = cardElementsFor(CHOPPING_BOARD, c) as unknown as El[];
    expect(out.map((e) => e.id)).toContain('rule');
    expect(byId(out, 'note')!.text).toBe('Note');
  });
});

// ---------------------------------------------------------------------------
// cardFieldValue / boxColours
// ---------------------------------------------------------------------------

describe('cardFieldValue', () => {
  it('reads each field from the item', () => {
    expect(cardFieldValue(COLANDER, 'name')).toBe('COLANDER');
    expect(cardFieldValue(WASTE, 'code')).toBe('SRTW5000');
    expect(cardFieldValue(COLANDER, 'spec')).toBe('390x200x140 / Depth: 160mm');
    expect(cardFieldValue({ ...COLANDER, remark: 'R' } as unknown as TagAccessory, 'remark')).toBe('R');
    expect(cardFieldValue(WASTE, 'price')).toBe(`LP: ${formatTagPrice(68)}`);
    expect(cardFieldValue(COLANDER, 'colours')).toEqual([BLACK.hex, GREY.hex]);
  });
});

describe('boxColours', () => {
  it('de-duplicates in order of first appearance', () => {
    expect(boxColours([COLANDER, DRAINER, CHOPPING_BOARD])).toEqual([BLACK.hex, GREY.hex]);
    const silver = { ...CHOPPING_BOARD, colours: [{ name: 'Silver', hex: '#c0c0c0' }, GREY] } as unknown as TagAccessory;
    expect(boxColours([silver, COLANDER])).toEqual(['#c0c0c0', GREY.hex, BLACK.hex]);
  });

  it('is empty when nothing has a colour', () => {
    expect(boxColours([CHOPPING_BOARD, WASTE])).toEqual([]);
    expect(boxColours([])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// cardFromLegacy
// ---------------------------------------------------------------------------

describe('cardFromLegacy', () => {
  const fieldsOf = (layout: { elements: El[] }) => layout.elements.map((e) => e.field);

  it('builds picture, name and spec elements sized like the legacy card (picture above text)', () => {
    const props = { ...defaultAccessoriesProps(), direction: 'horizontal', itemLayout: 'stacked' } as AccessoriesLayerProps;
    const layout = cardFromLegacy(props, 2) as unknown as { width_mm: number; height_mm: number; elements: El[] };
    const legacy = accessoryBoxLayout(1, props, 200, 200, 2).cards[0];
    expect(layout.width_mm).toBeCloseTo(legacy.width_mm);
    expect(layout.height_mm).toBeCloseTo(legacy.height_mm);
    expect(fieldsOf(layout)).toEqual(expect.arrayContaining(['picture', 'name', 'spec']));
    const pic = byId(layout.elements, 'picture') ?? layout.elements.find((e) => e.field === 'picture')!;
    expect(pic.kind).toBe('picture');
    const name = layout.elements.find((e) => e.field === 'name')!;
    const spec = layout.elements.find((e) => e.field === 'spec')!;
    expect(name.kind).toBe('text');
    expect(spec.kind).toBe('text');
    expect(pic.y_mm as number).toBeLessThan(name.y_mm as number);
    expect(name.y_mm as number).toBeLessThan(spec.y_mm as number);
  });

  it('puts the picture left of the text for the side layout', () => {
    const props = { ...defaultAccessoriesProps(), direction: 'horizontal', itemLayout: 'side' } as AccessoriesLayerProps;
    const layout = cardFromLegacy(props, 2) as unknown as { width_mm: number; height_mm: number; elements: El[] };
    const legacy = accessoryBoxLayout(1, props, 200, 200, 2).cards[0];
    expect(layout.height_mm).toBeCloseTo(legacy.height_mm);
    const pic = layout.elements.find((e) => e.field === 'picture')!;
    const name = layout.elements.find((e) => e.field === 'name')!;
    expect((pic.x_mm as number) + (pic.width_mm as number)).toBeLessThanOrEqual((name.x_mm as number) + 1e-6);
  });

  it('adds the price line when the box lists a product (3 lines)', () => {
    const props = { ...defaultAccessoriesProps(), direction: 'horizontal' } as AccessoriesLayerProps;
    const layout = cardFromLegacy(props, 3) as unknown as { height_mm: number; elements: El[] };
    expect(fieldsOf(layout)).toContain('price');
    const legacy = accessoryBoxLayout(1, props, 200, 200, 3).cards[0];
    expect(layout.height_mm).toBeCloseTo(legacy.height_mm);
  });

  it('gives every element a unique id', () => {
    const layout = cardFromLegacy(defaultAccessoriesProps(), 3) as unknown as { elements: El[] };
    const ids = layout.elements.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('carries the box name and spec text styles onto the elements', () => {
    const props = {
      ...defaultAccessoriesProps(),
      nameFontSize: 9,
      specFontSize: 5,
      nameStyle: { fontWeight: 700 },
      specStyle: { fontWeight: 400 },
    } as AccessoriesLayerProps;
    const layout = cardFromLegacy(props, 2) as unknown as { elements: El[] };
    const name = layout.elements.find((e) => e.field === 'name')!;
    const spec = layout.elements.find((e) => e.field === 'spec')!;
    expect(name.fontSize).toBe(9);
    expect(name.fontWeight).toBe(700);
    expect(spec.fontSize).toBe(5);
    expect(spec.fontWeight).toBe(400);
  });

  it('a converted card lays out and prints the same item text as the legacy card', () => {
    const props = { ...defaultAccessoriesProps(), direction: 'horizontal' } as AccessoriesLayerProps;
    const layout = cardFromLegacy(props, 2);
    const out = cardElementsFor(COLANDER, layout) as unknown as El[];
    expect(out.find((e) => e.field === 'name')!.text).toBe('COLANDER');
    expect(out.find((e) => e.field === 'spec')!.text).toBe('390x200x140 / Depth: 160mm');
    expect(out.find((e) => e.field === 'picture')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// accessoryDesign / applyAccessoryDesign
// ---------------------------------------------------------------------------

describe('accessoryDesign / applyAccessoryDesign', () => {
  const own = {
    ...defaultAccessoriesProps(),
    subjectSlot: 'fixed',
    subjectPart: 2,
    presetId: 'old-preset',
    fill: '#111111',
    headerText: 'OLD',
  } as unknown as AccessoriesLayerProps;

  it('accessoryDesign drops kind, subjectSlot, subjectPart and presetId and nothing else', () => {
    const design = accessoryDesign(own) as unknown as El;
    for (const key of ['kind', 'subjectSlot', 'subjectPart', 'presetId']) expect(design).not.toHaveProperty(key);
    expect(design.fill).toBe('#111111');
    expect(design.headerText).toBe('OLD');
    expect(design.direction).toBe('vertical');
  });

  it('accessoryDesign does not mutate its input', () => {
    const before = JSON.stringify(own);
    accessoryDesign(own);
    expect(JSON.stringify(own)).toBe(before);
  });

  it('applyAccessoryDesign takes the design and keeps the per-box keys', () => {
    const design = { ...(accessoryDesign(defaultAccessoriesProps()) as unknown as El), fill: '#ffffff', headerText: 'FREE' };
    const applied = applyAccessoryDesign(own, design as never, 'new-preset') as unknown as El;
    expect(applied.kind).toBe('accessories');
    expect(applied.subjectSlot).toBe('fixed');
    expect(applied.subjectPart).toBe(2);
    expect(applied.presetId).toBe('new-preset');
    expect(applied.fill).toBe('#ffffff');
    expect(applied.headerText).toBe('FREE');
  });

  it('applyAccessoryDesign ignores per-box keys smuggled inside a design', () => {
    const design = { ...(accessoryDesign(defaultAccessoriesProps()) as unknown as El), kind: 'text', subjectSlot: 'main' };
    const applied = applyAccessoryDesign(own, design as never, 'p') as unknown as El;
    expect(applied.kind).toBe('accessories');
    expect(applied.subjectSlot).toBe('fixed');
  });

  it('applyAccessoryDesign with a null preset id detaches', () => {
    const applied = applyAccessoryDesign(own, accessoryDesign(own) as never, null) as unknown as El;
    expect(applied.presetId == null).toBe(true);
    expect(applied.subjectPart).toBe(2);
  });
});
