/**
 * SPEC-SHEET-DESIGNER-PARITY B2: an Accessories box added on a spec sheet template starts with a
 * card of picture above, a bold "BRAND CODE" line, then the spec sheet description. A price tag's
 * box keeps the legacy default (no designed card).
 */
import { describe, expect, it } from 'vitest';

import { cardElementsFor, defaultAccessoriesPropsFor } from './accessory-card';
import type { TagAccessory } from './tag-template-types';

const ITEM = {
  kind: 'product',
  id: 'p1',
  code: 'WC-100',
  name: 'Wall hung WC',
  brand: 'Acme',
  spec_sheet_description: 'Soft close seat',
  spec: null,
  image: { attachment_id: 'a1', url: 'https://img/1.png' },
} as unknown as TagAccessory;

describe('defaultAccessoriesPropsFor', () => {
  it('a price tag keeps the legacy card', () => {
    expect(defaultAccessoriesPropsFor(false).card).toBeUndefined();
  });

  it('a spec sheet gets a designed card: picture, bold brand + code, spec sheet description', () => {
    const props = defaultAccessoriesPropsFor(true);
    expect(props.card).toBeDefined();
    const elements = cardElementsFor(ITEM, props.card!);
    expect(elements.map((e) => e.kind)).toEqual(['picture', 'text', 'text']);
    const [picture, title, body] = elements;
    expect(picture.src).toBe('https://img/1.png');
    expect(title.text).toBe('Acme WC-100');
    expect(title.fontWeight).toBeGreaterThanOrEqual(700);
    expect(body.text).toBe('Soft close seat');
    // Picture above the text, in order.
    expect(picture.y_mm).toBeLessThan(title.y_mm);
    expect(title.y_mm).toBeLessThan(body.y_mm);
  });

  it('an item with no brand prints just its code', () => {
    const props = defaultAccessoriesPropsFor(true);
    const [, title] = cardElementsFor({ ...ITEM, brand: null } as TagAccessory, props.card!);
    expect(title.text?.trim()).toBe('WC-100');
  });
});
