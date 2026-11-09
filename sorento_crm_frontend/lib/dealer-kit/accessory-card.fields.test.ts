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
