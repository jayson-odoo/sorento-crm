/**
 * PRICETAG-UPGRADE-VARIANTS FE tests 3 and 4: card fields `topup` / `price_with_upgrade`, the `prefix`
 * on a text element, the `feature_icons` card element, and `defaultUpgradeCard()`.
 *
 * Written test-FIRST. Chosen: a resolved `feature_icons` element carries its matched icons as
 * `icons: FeatureIcon[]` (library order); `cardElementsFor(item, card, featureIcons?)`;
 * `defaultUpgradeCard` is exported from `./accessory-card`. AC-U3, U7, Q2 (a).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import {
  cardElementsFor,
  cardElementsForDesign,
  cardFieldValue,
  defaultUpgradeCard,
} from './accessory-card';
import { icon, spec, SUS_ICON, TRAP_ICONS } from './test-support/upgrade-variants-fixtures';
import type { CardLayout, TagAccessory } from './tag-template-types';

const item = (over: Record<string, unknown> = {}) =>
  ({
    kind: 'upgrade',
    id: 'id-SRTKT71SS',
    code: 'SRTKT71SS',
    name: 'Pull-out shower mixer',
    spec: null,
    image: null,
    list_price: 440,
    topup_amount: 150,
    price_with_upgrade: 1099,
    specs: [spec('steel_grade', 'SUS 304', '304')],
    ...over,
  }) as unknown as TagAccessory;

describe('cardFieldValue topup / price_with_upgrade', () => {
  it('formats the top-up with the shared price formatter', () => {
    expect(cardFieldValue(item(), 'topup' as never)).toBe('RM 150');
  });
  it('formats the price with upgrade', () => {
    expect(cardFieldValue(item(), 'price_with_upgrade' as never)).toBe('RM 1,099');
  });
  it('is null when there is no figure', () => {
    expect(cardFieldValue(item({ topup_amount: null }), 'topup' as never)).toBeNull();
    expect(cardFieldValue(item({ price_with_upgrade: null }), 'price_with_upgrade' as never)).toBeNull();
    expect(cardFieldValue(item({ topup_amount: undefined }), 'topup' as never)).toBeNull();
  });
  it('stays null on a free item (no such field), so the element hides', () => {
    const free = { kind: 'accessory', id: 'a1', name: 'DRAINER', spec: null, image: null } as TagAccessory;
    expect(cardFieldValue(free, 'topup' as never)).toBeNull();
    expect(cardFieldValue(free, 'price_with_upgrade' as never)).toBeNull();
  });
});

const CARD = {
  width_mm: 71,
  height_mm: 21.5,
  elements: [
    { id: 'topup', kind: 'text', field: 'topup', prefix: 'TOPUP ', x_mm: 17, y_mm: 1, width_mm: 50, height_mm: 4 },
    { id: 'code', kind: 'text', field: 'code', x_mm: 17, y_mm: 5.6, width_mm: 50, height_mm: 3 },
    { id: 'icons', kind: 'feature_icons', x_mm: 17, y_mm: 15.2, width_mm: 50, height_mm: 5, iconSize_mm: 4.6, gap_mm: 0.8 },
  ],
} as unknown as CardLayout;

const byId = (list: { id: string }[], id: string) => list.find((e) => e.id === id) as Record<string, unknown> | undefined;

describe('cardElementsFor prefix', () => {
  it('prints the prefix before the value: TOPUP RM 150', () => {
    const out = cardElementsFor(item(), CARD, [SUS_ICON]);
    expect(byId(out, 'topup')?.text).toBe('TOPUP RM 150');
    expect(byId(out, 'code')?.text).toBe('SRTKT71SS');
  });

  it('an empty top-up drops the element, prefix and all, and closes up', () => {
    const out = cardElementsFor(item({ topup_amount: null }), CARD, [SUS_ICON]);
    expect(byId(out, 'topup')).toBeUndefined();
    expect(byId(out, 'code')?.y_mm).toBeCloseTo(1, 6);
  });

  it('a value with no prefix prints bare, as today', () => {
    const card = { ...CARD, elements: [{ ...CARD.elements[0], prefix: undefined }] } as unknown as CardLayout;
    expect(byId(cardElementsFor(item(), card), 'topup')?.text).toBe('RM 150');
  });
});

describe('cardElementsFor feature_icons', () => {
  it('resolves the item own icons from its specs', () => {
    const out = cardElementsFor(item(), CARD, [SUS_ICON, icon('x', 'Other', 'colour', ['red'])]);
    const el = byId(out, 'icons') as { icons?: { id: string }[] };
    expect(el.icons?.map((i) => i.id)).toEqual(['sus']);
  });

  it('is dropped when no icon matches, and the elements below move up (V7)', () => {
    const card = {
      ...CARD,
      elements: [
        { id: 'icons', kind: 'feature_icons', x_mm: 17, y_mm: 2, width_mm: 50, height_mm: 5, iconSize_mm: 4.6, gap_mm: 0.8 },
        { id: 'code', kind: 'text', field: 'code', x_mm: 17, y_mm: 8, width_mm: 50, height_mm: 3 },
      ],
    } as unknown as CardLayout;
    const out = cardElementsFor(item({ specs: [] }), card, TRAP_ICONS);
    expect(byId(out, 'icons')).toBeUndefined();
    expect(byId(out, 'code')?.y_mm).toBeCloseTo(2, 6);
  });

  it('is dropped when no library icons are given at all', () => {
    expect(byId(cardElementsFor(item(), CARD), 'icons')).toBeUndefined();
  });

  it('the designer view keeps the element, drawn from sample icons, never dropped', () => {
    const out = cardElementsForDesign(item({ specs: [] }), CARD);
    expect(byId(out, 'icons')).toBeDefined();
  });
});

describe('defaultUpgradeCard (FE test 4, Q2 a)', () => {
  // Built per test so a missing export fails the test, not the whole file at collection.
  let card: CardLayout;
  let els: Record<string, unknown>[];
  beforeEach(() => {
    card = defaultUpgradeCard();
    els = card.elements as unknown as Record<string, unknown>[];
  });

  it('is 71 x 21.5 mm', () => {
    expect([card.width_mm, card.height_mm]).toEqual([71, 21.5]);
  });

  it('carries picture, top-up, code, name, price and feature icons', () => {
    expect(els.some((e) => e.kind === 'picture')).toBe(true);
    for (const field of ['topup', 'code', 'name', 'price']) {
      expect(els.some((e) => e.kind === 'text' && e.field === field), field).toBe(true);
    }
    expect(els.some((e) => e.kind === 'feature_icons')).toBe(true);
  });

  it('does NOT carry price_with_upgrade (off by default)', () => {
    expect(els.some((e) => e.field === 'price_with_upgrade')).toBe(false);
  });

  it('the top-up reads TOPUP in bold red 10.8pt at (17, 1)', () => {
    const topup = els.find((e) => e.field === 'topup') as Record<string, unknown>;
    expect(topup).toMatchObject({ prefix: 'TOPUP ', fontWeight: 700, fontSize: 10.8, x_mm: 17, y_mm: 1 });
    expect(String(topup.color).toLowerCase()).toBe('#b91c1c');
  });

  it('places the rest where the plan says', () => {
    const at = (field: string) => els.find((e) => e.field === field) as Record<string, number>;
    expect([at('code').x_mm, at('code').y_mm]).toEqual([17, 5.6]);
    expect([at('name').x_mm, at('name').y_mm]).toEqual([17, 9.2]);
    expect([at('price').x_mm, at('price').y_mm]).toEqual([17, 12.2]);
    const pic = els.find((e) => e.kind === 'picture') as Record<string, number>;
    expect([pic.x_mm, pic.y_mm, pic.width_mm, pic.height_mm]).toEqual([1, 1.5, 14, 19]);
    const fi = els.find((e) => e.kind === 'feature_icons') as Record<string, number>;
    expect([fi.x_mm, fi.y_mm, fi.width_mm, fi.height_mm]).toEqual([17, 15.2, 50, 5]);
  });

  it('survives a JSON round trip (the saved doc)', () => {
    expect(JSON.parse(JSON.stringify(card))).toEqual(card);
  });

  it('with the card, the SRTKT71SS item prints the owner sample words', () => {
    const out = cardElementsFor(item(), card, [SUS_ICON]);
    const texts = out.map((e) => (e as { text?: string }).text).filter(Boolean);
    expect(texts).toEqual(expect.arrayContaining(['TOPUP RM 150', 'SRTKT71SS', 'Pull-out shower mixer', 'LP: RM 440']));
  });
});
