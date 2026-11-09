/**
 * PRICETAG-HEADER-DRAG (owner 9 Nov): the accessories box header can be dragged anywhere inside its
 * box. The spot is stored on the box (`headerPos`, mm from the box's top-left) and applied in the ONE
 * chrome function every render uses. Rulings: no reflow (cards, frame and footer never move with the
 * header), a moved header is plain text (no border break), an unmoved header is exactly today's.
 */
import { describe, expect, it } from 'vitest';

import { ACCESSORY_BOX_PAD_MM, accessoryBoxLayout, accessoryChrome } from './accessory-box';
import {
  accessoryDesign,
  accessoryDesignChanged,
  applyAccessoryDesign,
  cardBoxLayout,
  snapHeader,
} from './accessory-card';
import { defaultAccessoriesProps, type AccessoriesLayerProps } from './tag-template-types';

const CARD = {
  width_mm: 40,
  height_mm: 20,
  elements: [{ id: 'n', kind: 'text', field: 'name', x_mm: 1, y_mm: 1, width_mm: 30, height_mm: 4 }],
} as unknown as NonNullable<AccessoriesLayerProps['card']>;

const base = (extra: Partial<AccessoriesLayerProps> = {}): AccessoriesLayerProps =>
  ({ ...defaultAccessoriesProps(), headerText: 'FREE', ...extra }) as AccessoriesLayerProps;

describe('accessoryChrome with a stored header position', () => {
  it('an unmoved header is where it was (on the border: centred on the top edge, not moved)', () => {
    const chrome = accessoryChrome(base({ headerOnBorder: true }), 50, 40);
    expect(chrome.header).not.toBeNull();
    expect(chrome.header!.y_mm).toBe(0);
    expect(chrome.header!.x_mm).toBeCloseTo((50 - chrome.header!.width_mm) / 2, 6);
    expect(chrome.header!.onBorder).toBe(true);
    expect(chrome.header!.moved).toBe(false);
  });

  it('inside the frame the text rect is the text\'s own span in the band (the handle starts there)', () => {
    const h = accessoryChrome(base({ headerOnBorder: false }), 60, 40).header!;
    expect(h.width_mm).toBeGreaterThan(h.text.width_mm);
    // Centred by default: the text's centre is the band's centre.
    expect(h.text.x_mm + h.text.width_mm / 2).toBeCloseTo(h.x_mm + h.width_mm / 2, 6);
    const left = accessoryChrome(base({ headerOnBorder: false, headerStyle: { align: 'left' } as never }), 60, 40).header!;
    // Left aligned, the letters start at the band's left edge; a moved header centres its letters in
    // the text-wide band (text + a pad each side), so that band starts a pad further left.
    expect(left.text.x_mm).toBeCloseTo(left.x_mm - ACCESSORY_BOX_PAD_MM, 6);
    const moved = accessoryChrome(
      base({ headerOnBorder: false, headerStyle: { align: 'left' } as never, headerPos: { x_mm: left.text.x_mm, y_mm: 10 } }),
      60,
      40,
    ).header!;
    expect(moved.x_mm + ACCESSORY_BOX_PAD_MM).toBeCloseTo(left.x_mm, 6);
  });

  it('first drag of an inside-frame header: dropped straight down, the text stays at the same x', () => {
    const props = base({ headerOnBorder: false });
    const before = accessoryChrome(props, 60, 40).header!;
    const frame = accessoryChrome(props, 60, 40).frame;
    // The handle starts from header.text; drag it 10 mm down with no sideways move.
    const at = snapHeader({ ...before.text, y_mm: before.text.y_mm + 10 }, frame, { width_mm: 60, height_mm: 40 });
    const after = accessoryChrome({ ...props, headerPos: { x_mm: at.x_mm, y_mm: at.y_mm } }, 60, 40).header!;
    expect(after.text.x_mm + after.text.width_mm / 2).toBeCloseTo(before.text.x_mm + before.text.width_mm / 2, 1);
    // And it can be dragged well right of the band's left inset.
    const right = snapHeader({ ...before.text, x_mm: 40 }, frame, { width_mm: 60, height_mm: 40 });
    expect(right.x_mm).toBeGreaterThan(30);
  });

  it('null and absent positions draw the same header', () => {
    const a = accessoryChrome(base({ headerOnBorder: true }), 50, 40);
    const b = accessoryChrome(base({ headerOnBorder: true, headerPos: null }), 50, 40);
    expect(b).toEqual(a);
  });

  it('a moved header sits at its stored spot and is plain text, even with "on border" set', () => {
    const chrome = accessoryChrome(base({ headerOnBorder: true, headerPos: { x_mm: 4, y_mm: 30 } }), 50, 40);
    expect(chrome.header!.x_mm).toBe(4);
    expect(chrome.header!.y_mm).toBe(30);
    expect(chrome.header!.onBorder).toBe(false);
    expect(chrome.header!.moved).toBe(true);
  });

  it('a moved header keeps its text size and is only as wide as its text', () => {
    const unmoved = accessoryChrome(base({ headerOnBorder: true }), 50, 40).header!;
    const moved = accessoryChrome(base({ headerOnBorder: true, headerPos: { x_mm: 1, y_mm: 1 } }), 50, 40).header!;
    expect(moved.fontSize_pt).toBe(unmoved.fontSize_pt);
    expect(moved.height_mm).toBe(unmoved.height_mm);
    expect(moved.width_mm).toBeCloseTo(unmoved.width_mm, 6);
    expect(moved.width_mm).toBeLessThan(50);
  });

  it('moving the header never moves the frame (no reflow)', () => {
    const before = accessoryChrome(base({ headerOnBorder: true }), 50, 40);
    const after = accessoryChrome(base({ headerOnBorder: true, headerPos: { x_mm: 2, y_mm: 25 } }), 50, 40);
    expect(after.frame).toEqual(before.frame);
    expect(after.badge).toEqual(before.badge);
  });

  it('a spot past the box edge is pulled back inside (the box closed up)', () => {
    const chrome = accessoryChrome(base({ headerPos: { x_mm: 500, y_mm: 500 } }), 50, 40);
    const h = chrome.header!;
    expect(h.x_mm).toBeCloseTo(50 - h.width_mm, 6);
    expect(h.y_mm).toBeCloseTo(40 - h.height_mm, 6);
    const neg = accessoryChrome(base({ headerPos: { x_mm: -5, y_mm: -5 } }), 50, 40).header!;
    expect(neg.x_mm).toBe(0);
    expect(neg.y_mm).toBe(0);
  });

  it('a hidden header stays hidden whatever its stored spot', () => {
    expect(accessoryChrome(base({ showHeader: false, headerPos: { x_mm: 1, y_mm: 1 } }), 50, 40).header).toBeNull();
  });
});

describe('box layouts: the cards never move with the header (Q2)', () => {
  it('designed card box: same cards, footer and size with and without a moved header', () => {
    const props = base({ headerOnBorder: true, card: CARD });
    const before = cardBoxLayout(2, props, 50, 80);
    const after = cardBoxLayout(2, { ...props, headerPos: { x_mm: 3, y_mm: 30 } }, 50, 80);
    expect(after.cards).toEqual(before.cards);
    expect(after.footer).toEqual(before.footer);
    expect(after.boxHeight_mm).toBe(before.boxHeight_mm);
    expect(after.header!.y_mm).toBe(30);
  });

  it('legacy box: same cards with and without a moved header', () => {
    const props = base();
    const before = accessoryBoxLayout(2, props, 50, 80);
    const after = accessoryBoxLayout(2, { ...props, headerPos: { x_mm: 3, y_mm: 10 } }, 50, 80);
    expect(after.cards).toEqual(before.cards);
    expect(after.header!.x_mm).toBe(3);
  });
});

describe('snapHeader: dragging the header inside its box', () => {
  const header = { x_mm: 0, y_mm: 0, width_mm: 10, height_mm: 4 };
  const frame = { x_mm: 0, y_mm: 2, width_mm: 50, height_mm: 38 };

  it('snaps the header centre onto the box centre line', () => {
    const at = snapHeader({ ...header, x_mm: 19.4, y_mm: 15 }, frame, { width_mm: 50, height_mm: 40 });
    expect(at.x_mm).toBeCloseTo(20, 6);
    expect(at.guides.some((g) => g.orientation === 'vertical' && g.position_mm === 25)).toBe(true);
  });

  it('snaps the header middle onto the frame top border', () => {
    const at = snapHeader({ ...header, x_mm: 7, y_mm: 0.3 }, frame, { width_mm: 50, height_mm: 40 });
    expect(at.y_mm).toBeCloseTo(0, 6);
  });

  it('never lets the header leave the box', () => {
    const at = snapHeader({ ...header, x_mm: 80, y_mm: -9 }, frame, { width_mm: 50, height_mm: 40 });
    expect(at.x_mm).toBe(40);
    expect(at.y_mm).toBe(0);
  });
});

describe('Q5 (a): the header spot is part of the linked design', () => {
  it('is saved with the design and applied from it', () => {
    const props = base({ headerPos: { x_mm: 5, y_mm: 6 }, presetId: 'tpl-1' });
    expect(accessoryDesign(props).headerPos).toEqual({ x_mm: 5, y_mm: 6 });
    const applied = applyAccessoryDesign(base({ presetId: 'tpl-1' }), accessoryDesign(props), 'tpl-1');
    expect(applied.headerPos).toEqual({ x_mm: 5, y_mm: 6 });
  });

  it('moving it is a design change (live link updates the saved template, detach mode detaches)', () => {
    expect(accessoryDesignChanged(base(), { headerPos: { x_mm: 1, y_mm: 2 } })).toBe(true);
  });
});

describe('cardBoxLayout with a design missing a number', () => {
  it('lays out nothing instead of throwing (a saved design with no gap)', () => {
    const props = { ...base({ card: CARD }), gap_mm: undefined } as unknown as AccessoriesLayerProps;
    expect(() => cardBoxLayout(2, props, 50, 80)).not.toThrow();
    expect(cardBoxLayout(2, props, 50, 80).header).toBeNull();
  });
});
