/**
 * Product blocks, bindings and the two presets (AC-L.3, L.4, L.5).
 *
 * The builders are pure, so this is where the binding rules are pinned: a
 * dropped block carries slot bindings and no values, typing over a bound layer
 * unlinks it without losing the binding, and "Relink" is one field going back
 * to null.
 */

import { describe, expect, it } from 'vitest';

import type {
  ProductSetTagData,
  ProductTagData,
  TagLayer,
} from './tag-template-types';
import {
  buildAccessoriesStrip,
  buildAlternativesRow,
  buildProductBlock,
  buildSetBlock,
  formatSetMemberLine,
  isUnlinked,
  layerDisplay,
  layerText,
  priceBadgeInput,
  primaryImageOf,
  resolveSlotText,
  slotImageAttachmentId,
} from './product-block';

let seq = 0;
const newId = () => `l${(seq += 1)}`;

function product(overrides: Partial<ProductTagData> = {}): ProductTagData {
  return {
    id: 'p1',
    code: 'SK-1234',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: ['Stainless steel', 'Overflow included'],
    images: [
      { attachment_id: 'att-primary', url: 'https://cdn/1.jpg', is_primary: true },
      { attachment_id: 'att-other', url: 'https://cdn/2.jpg', is_primary: false },
    ],
    list_price: 1599,
    offer_price: null,
    promotion_id: null,
    ...overrides,
  };
}

function productSet(): ProductSetTagData {
  return {
    id: 's1',
    set_code: 'BF-SET-01',
    name: 'Bathroom Furniture Set',
    members: [
      {
        product_id: 'p1',
        code: 'CAB-01',
        name: 'Cabinet',
        dimensions: '800 x 460 x 550 mm',
        quantity: 1,
      },
      {
        product_id: 'p2',
        code: 'BAS-01',
        name: 'Basin',
        dimensions: '800 x 460 x 180 mm',
        quantity: 1,
      },
    ],
    list_price: 2400,
    offer_price: 1800,
    promotion_id: 'promo-1',
  };
}

const OPTS = { newId, x_mm: 10, y_mm: 20, z_index: 1 };

function findBySlot(layers: TagLayer[], slot: string) {
  return layers.find((layer) => layer.slot_binding === slot);
}

// ---------------------------------------------------------------------------
// Dropping a product (AC-L.3)
// ---------------------------------------------------------------------------

describe('buildProductBlock', () => {
  it('creates a group bound to the product', () => {
    const layers = buildProductBlock(product(), OPTS);
    const group = layers.find((layer) => layer.props.kind === 'group');

    expect(group).toBeDefined();
    expect(group!.props).toMatchObject({ kind: 'group', binding: { product_id: 'p1' } });
    expect((group!.props as { children: string[] }).children).toHaveLength(
      layers.length - 1,
    );
  });

  it('gives every child its slot binding', () => {
    const layers = buildProductBlock(product(), OPTS);
    const slots = layers.map((layer) => layer.slot_binding);

    expect(slots).toEqual(
      expect.arrayContaining([
        'product_image',
        'code',
        'name',
        'dimensions',
        'spec_lines',
      ]),
    );
  });

  it('leaves every text layer linked - no overrides on a fresh block', () => {
    const layers = buildProductBlock(product(), OPTS);

    expect(layers.every((layer) => layer.text_override === null)).toBe(true);
  });

  it('points the image layer at the primary photo', () => {
    const layers = buildProductBlock(product(), OPTS);
    const image = findBySlot(layers, 'product_image');

    expect(image!.props).toMatchObject({
      source: { type: 'product_attachment', attachmentId: 'att-primary' },
    });
  });

  it('drops a promo badge when the product is on offer, a list badge otherwise', () => {
    const plain = buildProductBlock(product(), OPTS);
    const offered = buildProductBlock(product({ offer_price: 599 }), OPTS);

    expect(
      plain.find((layer) => layer.props.kind === 'price_badge')!.props,
    ).toMatchObject({ variant: 'list_only' });
    expect(
      offered.find((layer) => layer.props.kind === 'price_badge')!.props,
    ).toMatchObject({ variant: 'promo' });
  });

  it('places the block where it was asked to', () => {
    const layers = buildProductBlock(product(), OPTS);

    expect(Math.min(...layers.map((layer) => layer.x_mm))).toBe(10);
    expect(Math.min(...layers.map((layer) => layer.y_mm))).toBe(20);
  });
});

// ---------------------------------------------------------------------------
// Unlink and relink (AC-L.3)
// ---------------------------------------------------------------------------

describe('unlink and relink', () => {
  const data = { kind: 'product' as const, product: product() };

  it('shows the resolved value while the layer is linked', () => {
    const layers = buildProductBlock(product(), OPTS);
    const name = findBySlot(layers, 'name')!;

    expect(layerText(name, data)).toBe('Kitchen Sink');
    expect(isUnlinked(name)).toBe(false);
  });

  it('shows the typed text once somebody types over it', () => {
    const layers = buildProductBlock(product(), OPTS);
    const name = { ...findBySlot(layers, 'name')!, text_override: 'Showroom Special' };

    expect(layerText(name, data)).toBe('Showroom Special');
    expect(isUnlinked(name)).toBe(true);
  });

  it('restores the resolved value when the override is cleared', () => {
    const layers = buildProductBlock(product(), OPTS);
    const overridden = {
      ...findBySlot(layers, 'name')!,
      text_override: 'Showroom Special',
    };
    const relinked = { ...overridden, text_override: null };

    expect(layerText(relinked, data)).toBe('Kitchen Sink');
    expect(isUnlinked(relinked)).toBe(false);
  });

  it('keeps the binding through the override, so a rebind still reaches it', () => {
    const layers = buildProductBlock(product(), OPTS);
    const overridden = { ...findBySlot(layers, 'name')!, text_override: 'Typed' };

    expect(overridden.slot_binding).toBe('name');
    expect(
      layerText({ ...overridden, text_override: null }, {
        kind: 'product',
        product: product({ name: 'Another Sink' }),
      }),
    ).toBe('Another Sink');
  });

  it('resolves spec lines as one text block', () => {
    const layers = buildProductBlock(product(), OPTS);

    expect(layerText(findBySlot(layers, 'spec_lines')!, data)).toBe(
      'Stainless steel\nOverflow included',
    );
  });
});

// ---------------------------------------------------------------------------
// Sets (AC-L.4)
// ---------------------------------------------------------------------------

describe('buildSetBlock', () => {
  it('formats one line per member', () => {
    expect(
      formatSetMemberLine({
        product_id: 'p1',
        code: 'CAB-01',
        name: 'Cabinet',
        dimensions: '800 x 460 x 550 mm',
        quantity: 1,
      }),
    ).toBe('- CAB-01 (Cabinet) 800 x 460 x 550 mm');
  });

  it('binds the group to the set and fills the members slot', () => {
    const set = productSet();
    const layers = buildSetBlock(set, OPTS);
    const group = layers.find((layer) => layer.props.kind === 'group');

    expect(group!.props).toMatchObject({ binding: { product_set_id: 's1' } });
    expect(
      resolveSlotText(findBySlot(layers, 'set_members')!, { kind: 'set', set }),
    ).toBe(
      '- CAB-01 (Cabinet) 800 x 460 x 550 mm\n- BAS-01 (Basin) 800 x 460 x 180 mm',
    );
  });

  it('takes its prices off the set', () => {
    const set = productSet();

    expect(priceBadgeInput({ kind: 'set', set })).toEqual({
      listPrice: 2400,
      offerPrice: 1800,
    });
  });
});

// ---------------------------------------------------------------------------
// Presets (AC-L.5)
// ---------------------------------------------------------------------------

describe('buildAlternativesRow', () => {
  it('places N blocks with N-1 OR connectors and one leading plus', () => {
    const products = [
      product({ id: 'a', code: 'TAP-1' }),
      product({ id: 'b', code: 'TAP-2' }),
      product({ id: 'c', code: 'TAP-3' }),
    ];
    const layers = buildAlternativesRow(products, OPTS);

    const texts = layers
      .filter((layer) => layer.props.kind === 'text')
      .map((layer) => (layer.props as { text: string }).text);

    expect(texts.filter((text) => text === '+')).toHaveLength(1);
    expect(texts.filter((text) => text === 'OR')).toHaveLength(2);
    expect(layers.filter((layer) => layer.props.kind === 'image')).toHaveLength(3);
    expect(layers.filter((layer) => layer.props.kind === 'price_badge')).toHaveLength(
      3,
    );
  });

  it('needs no connector for a single alternative', () => {
    const layers = buildAlternativesRow([product()], OPTS);
    const texts = layers
      .filter((layer) => layer.props.kind === 'text')
      .map((layer) => (layer.props as { text: string }).text);

    expect(texts.filter((text) => text === 'OR')).toHaveLength(0);
    expect(texts.filter((text) => text === '+')).toHaveLength(1);
  });

  it('leaves the row as ordinary layers - nothing is bound to a group', () => {
    const layers = buildAlternativesRow([product(), product({ id: 'b' })], OPTS);

    expect(layers.some((layer) => layer.props.kind === 'group')).toBe(false);
  });
});

describe('buildAccessoriesStrip', () => {
  it('titles the strip and gives every item a picture and a caption', () => {
    const layers = buildAccessoriesStrip(
      [
        { caption: 'WASTE-1', source: { type: 'asset', assetId: 'a1' } },
        {
          caption: 'TRAP-1',
          source: { type: 'product_attachment', attachmentId: 'att-1' },
        },
      ],
      OPTS,
    );

    const texts = layers
      .filter((layer) => layer.props.kind === 'text')
      .map((layer) => (layer.props as { text: string }).text);

    expect(texts[0]).toBe('Accessories Included');
    expect(texts).toContain('WASTE-1');
    expect(texts).toContain('TRAP-1');
    expect(layers.filter((layer) => layer.props.kind === 'image')).toHaveLength(2);
  });

  it('takes a title of its own', () => {
    const layers = buildAccessoriesStrip([], { ...OPTS, title: 'Free Gifts' });

    expect((layers[0].props as { text: string }).text).toBe('Free Gifts');
  });
});

// ---------------------------------------------------------------------------
// A product-photo slot follows the bound product (D42, AC-M.11)
// ---------------------------------------------------------------------------

function imageLayer(overrides: Partial<TagLayer> = {}): TagLayer {
  return {
    id: 'img',
    type: 'image',
    x_mm: 0,
    y_mm: 0,
    width_mm: 38,
    height_mm: 38,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: 'product_image',
    text_override: null,
    props: { kind: 'image', source: null, fit: 'contain', maskShape: 'none' },
    ...overrides,
  } as TagLayer;
}

function slotLayer(fieldKey: string): TagLayer {
  return {
    ...imageLayer(),
    id: 'slot',
    type: 'product_slot',
    slot_binding: null,
    props: { kind: 'product_slot', fieldKey },
  } as TagLayer;
}

const IMAGES = product().images;

describe('primaryImageOf', () => {
  it('takes the primary photo, or the first when none is marked', () => {
    expect(primaryImageOf(IMAGES)?.attachment_id).toBe('att-primary');
    expect(
      primaryImageOf([{ attachment_id: 'att-other', url: 'u', is_primary: false }])
        ?.attachment_id,
    ).toBe('att-other');
    expect(primaryImageOf([])).toBeUndefined();
  });
});

describe('slotImageAttachmentId', () => {
  it('lets the designer pinned photo win', () => {
    const layer = imageLayer({
      props: {
        kind: 'image',
        source: { type: 'product_attachment', attachmentId: 'att-other' },
        fit: 'contain',
      },
    });

    expect(slotImageAttachmentId(layer, IMAGES)).toBe('att-other');
  });

  it('follows the primary photo when the template pinned nothing', () => {
    expect(slotImageAttachmentId(imageLayer(), IMAGES)).toBe('att-primary');
  });

  it('falls back to the primary when the pinned photo is another product\'s', () => {
    const layer = imageLayer({
      props: {
        kind: 'image',
        source: { type: 'product_attachment', attachmentId: 'att-gone' },
        fit: 'contain',
      },
    });

    expect(slotImageAttachmentId(layer, IMAGES)).toBe('att-primary');
  });

  it('leaves a decorative image layer empty', () => {
    expect(slotImageAttachmentId(imageLayer({ slot_binding: null }), IMAGES)).toBeNull();
  });

  it('leaves an asset source to the asset map', () => {
    const layer = imageLayer({
      props: { kind: 'image', source: { type: 'asset', assetId: 'a1' }, fit: 'contain' },
    });

    expect(slotImageAttachmentId(layer, IMAGES)).toBeNull();
  });

  it('answers for a product_slot layer that holds the photo', () => {
    expect(slotImageAttachmentId(slotLayer('product_image'), IMAGES)).toBe('att-primary');
    expect(slotImageAttachmentId(slotLayer('code'), IMAGES)).toBeNull();
  });
});

describe('layerDisplay', () => {
  const data = { kind: 'product' as const, product: product() };

  it('draws the primary photo for a slot-bound image layer with no source', () => {
    expect(layerDisplay(imageLayer(), data, {})).toEqual({
      imageUrl: 'https://cdn/1.jpg',
    });
  });

  it('draws the pinned photo when the designer chose one', () => {
    const layer = imageLayer({
      props: {
        kind: 'image',
        source: { type: 'product_attachment', attachmentId: 'att-other' },
        fit: 'contain',
      },
    });

    expect(layerDisplay(layer, data, {})).toEqual({ imageUrl: 'https://cdn/2.jpg' });
  });

  it('shows nothing while no product is bound', () => {
    expect(layerDisplay(imageLayer(), null, {})).toEqual({ imageUrl: null });
  });

  it('shows nothing for an image layer bound to no slot', () => {
    expect(layerDisplay(imageLayer({ slot_binding: null }), data, {})).toEqual({
      imageUrl: null,
    });
  });

  it('resolves a line the same way a product resolves', () => {
    const line = {
      kind: 'line' as const,
      line: {
        line_id: 'l1',
        code: 'SK-1234',
        name: 'Kitchen Sink',
        dimensions: '800 x 500 x 220 mm',
        spec_lines: 'Stainless steel',
        set_members: '',
        images: IMAGES,
        list_price: 1599,
        sell_price: 599,
        show_promo_price: true,
        included_accessories: '',
        quantity: 1,
      },
    };

    expect(layerDisplay(imageLayer(), line, {})).toEqual({
      imageUrl: 'https://cdn/1.jpg',
    });
  });

  it('draws the photo for a product_slot layer, and the text for its other keys', () => {
    expect(layerDisplay(slotLayer('product_image'), data, {})).toEqual({
      imageUrl: 'https://cdn/1.jpg',
    });
    expect(layerDisplay(slotLayer('code'), data, {})).toEqual({ text: 'SK-1234' });
    expect(layerDisplay(slotLayer('dimensions'), data, {})).toEqual({
      text: '800 x 500 x 220 mm',
    });
  });

  it('leaves a product_slot layer on its placeholder while nothing is bound', () => {
    expect(layerDisplay(slotLayer('code'), null, {})).toBeUndefined();
    expect(layerDisplay(slotLayer('product_image'), null, {})).toEqual({
      imageUrl: null,
    });
  });
});
