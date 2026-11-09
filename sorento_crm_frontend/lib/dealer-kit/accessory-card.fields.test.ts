/**
 * TAG-ACC-CARD-RESIZE Q4: a card's fixed text takes `{{product.*}}` fields, resolved per accessory
 * through the SAME merge-field resolver a normal text layer uses (`renderMergeFields` /
 * `renderPriceTagDescription`), with the card's item as the bound product (`accessoryBinding`).
 */
import { describe, expect, it } from 'vitest';

import { accessoryBinding, cardElementsFor, cardElementsForDesign } from './accessory-card';
import { renderMergeFields } from './merge-fields';
import type { CardLayout, TagAccessory } from './tag-template-types';

const PRODUCT = {
  kind: 'product',
  id: 'p1',
  name: 'Kitchen Sink Mixer',
  spec: 'Brushed steel\nPull-out spray',
  remark: null,
  image: null,
  code: 'KM-100',
  list_price: 1550,
  sell_price: 1200,
  spec_lines: ['400 x 220 mm', 'Ceramic cartridge'],
  price_tag_description: 'Tag copy for {{product.code}}',
} as unknown as TagAccessory;

const LIBRARY = {
  kind: 'accessory',
  id: 'a1',
  name: 'Chopping Board',
  spec: 'Bamboo',
  remark: null,
  image: null,
  code: null,
  list_price: null,
} as unknown as TagAccessory;

function cardWith(text: string): CardLayout {
  return {
    width_mm: 40,
    height_mm: 20,
    elements: [
      { id: 't', kind: 'text', field: null, text, x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 10 },
      { id: 'under', kind: 'text', field: null, text: 'Under', x_mm: 0, y_mm: 11, width_mm: 40, height_mm: 5 },
    ],
  } as CardLayout;
}

const textOf = (item: TagAccessory, text: string) =>
  cardElementsFor(item, cardWith(text)).find((e) => e.id === 't')?.text;

describe('card fixed text with fields (TAG-ACC-CARD-RESIZE Q4)', () => {
  it('fixed text with no field prints exactly as typed (existing cards unchanged)', () => {
    expect(textOf(PRODUCT, 'FREE GIFT')).toBe('FREE GIFT');
  });

  it('resolves code, name, list price and sell price of a catalogue product', () => {
    const binding = accessoryBinding(PRODUCT);
    const lp = renderMergeFields('{{product.list_price}}', binding, 'print');
    const sp = renderMergeFields('{{product.sell_price}}', binding, 'print');
    expect(lp).toContain('1,550');
    expect(sp).toContain('1,200');
    expect(textOf(PRODUCT, '{{product.code}} {{product.name}}')).toBe('KM-100 Kitchen Sink Mixer');
    expect(textOf(PRODUCT, 'LP {{product.list_price}}')).toBe(`LP ${lp}`);
  });

  it('reads the price tag description (its own fields resolved against the same item)', () => {
    expect(textOf(PRODUCT, '{{product.price_tag_description}}')).toBe('Tag copy for KM-100');
  });

  it('reads spec lines', () => {
    expect(textOf(PRODUCT, '{{product.spec_lines}}')).toContain('400 x 220 mm');
  });

  it('a library accessory: name and spec resolve, code and prices print nothing', () => {
    expect(textOf(LIBRARY, '{{product.name}}')).toBe('Chopping Board');
    expect(textOf(LIBRARY, '{{product.price_tag_description}}')).toBe('Bamboo');
    expect(textOf(LIBRARY, '{{product.spec_lines}}')).toBe('Bamboo');
    expect(textOf(LIBRARY, 'Name: {{product.name}}\n{{product.list_price}}')).toBe('Name: Chopping Board');
  });

  it('a text whose only fields are all empty is dropped and the element under it moves up', () => {
    const out = cardElementsFor(LIBRARY, cardWith('{{product.code}}'));
    expect(out.find((e) => e.id === 't')).toBeUndefined();
    expect(out.find((e) => e.id === 'under')?.y_mm).toBe(0);
  });

  it('a rich text resolves its fields with the value escaped (never markup)', () => {
    const item = { ...LIBRARY, name: '<b>x</b>' } as TagAccessory;
    const text = textOf(item, '<p><strong>{{product.name}}</strong></p>');
    expect(text).toBe('<p><strong>&lt;b&gt;x&lt;/b&gt;</strong></p>');
  });

  it('card 1 under edit shows the resolved text, or the typed text when it resolves to nothing', () => {
    const design = (item: TagAccessory, text: string) =>
      cardElementsForDesign(item, cardWith(text)).find((e) => e.id === 't')?.text;
    expect(design(PRODUCT, '{{product.code}}')).toBe('KM-100');
    expect(design(LIBRARY, '{{product.code}}')).toBe('{{product.code}}');
  });
});

// ---------------------------------------------------------------------------
// Owner 22:30: a card Text element styles like the box header (background, padding, corner radius)
// ---------------------------------------------------------------------------

import { cardTextBox } from './accessory-card';

describe('cardTextBox (card Text background / padding / radius)', () => {
  const base = { id: 't', kind: 'text', x_mm: 2, y_mm: 3, width_mm: 20, height_mm: 6 } as const;

  it('no stored style: no background and the text box is the element itself (unchanged)', () => {
    const out = cardTextBox({ ...base }, 0.8);
    expect(out.background).toBeNull();
    expect(out.text).toMatchObject({ x_mm: 0, y_mm: 0, width_mm: 16 });
    expect(out.text.height_mm).toBeCloseTo(4.8);
  });

  it('a fill draws behind the whole element with its corner radius, both at the card scale', () => {
    const out = cardTextBox({ ...base, fill: '#dc2626', cornerRadius_mm: 1 }, 0.5);
    expect(out.background).toEqual({ fill: '#dc2626', radius_mm: 0.5, width_mm: 10, height_mm: 3 });
  });

  it('transparent fill draws no background', () => {
    expect(cardTextBox({ ...base, fill: 'transparent' }, 1).background).toBeNull();
  });

  it('padding insets the text box, at the card scale, never below zero', () => {
    const out = cardTextBox({ ...base, padding: { top: 1, right: 2, bottom: 1, left: 2 } }, 0.5);
    expect(out.text).toEqual({ x_mm: 1, y_mm: 0.5, width_mm: 8, height_mm: 2 });
    const tight = cardTextBox({ ...base, padding: { top: 9, right: 0, bottom: 9, left: 0 } }, 1);
    expect(tight.text.height_mm).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Owner 22:35: Upgrades cards read the price tag description too, rich formatting kept
// ---------------------------------------------------------------------------

import { upgradesOf } from './upgrade-items';

const UPGRADE = {
  kind: 'upgrade',
  id: 'u1',
  code: 'SRTKT71SS',
  name: 'Kitchen tap stainless',
  spec: null,
  image: null,
  list_price: 440,
  topup_amount: 150,
  price_with_upgrade: 1099,
  price_tag_description: '<p><strong>Pull-out</strong> spray {{product.code}}</p>',
  spec_lines: ['Stainless steel'],
} as unknown as TagAccessory;

describe('Upgrades card fields (owner 22:35)', () => {
  it('the price tag description of an upgrade item, rich formatting kept and its own fields resolved', () => {
    expect(textOf(UPGRADE, '{{product.price_tag_description}}')).toBe(
      '<p><strong>Pull-out</strong> spray SRTKT71SS</p>',
    );
  });

  it('mixed text reads the description as plain text, like a normal text layer', () => {
    expect(textOf(UPGRADE, 'Desc: {{product.price_tag_description}}')).toBe('Desc: Pull-out spray SRTKT71SS');
  });

  it('code and list price on an upgrade card; the fixed Top-up choice still works', () => {
    expect(textOf(UPGRADE, '{{product.code}}')).toBe('SRTKT71SS');
    const card = {
      width_mm: 40,
      height_mm: 20,
      elements: [{ id: 'top', kind: 'text', field: 'topup', prefix: 'TOPUP ', x_mm: 0, y_mm: 0, width_mm: 20, height_mm: 5 }],
    } as CardLayout;
    expect(cardElementsFor(UPGRADE, card)[0].text).toMatch(/^TOPUP .*150/);
  });

  it('upgradesOf carries the slot row price tag description, sell price and spec lines', () => {
    const data = {
      kind: 'product',
      product: {
        combo: {
          id: 'c', name: 'C', description: null, free_items: null, choices: [],
          upgrades: [{ product_id: 'u1', code: 'SRTKT71SS', description: 'Tap', topup_amount: 150, picked: false }],
        },
        slots: {
          fixed: [], groups: [],
          upgrades: [{ product_id: 'u1', code: 'SRTKT71SS', name: 'Tap', dimensions: '', list_price: 440, sell_price: 400,
            spec_lines: ['Stainless steel'], price_tag_description: 'Tap copy' }],
        },
      },
    } as unknown as Parameters<typeof upgradesOf>[0];
    const [item] = upgradesOf(data);
    expect(item.price_tag_description).toBe('Tap copy');
    expect(item.sell_price).toBe(400);
    expect(item.spec_lines).toEqual(['Stainless steel']);
    expect(item.spec).toBeNull();
  });
});
