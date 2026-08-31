/**
 * Which product each BLOCK of a template is being looked at with (D53).
 *
 * The sink combo tag carries four product blocks and one accessories strip.
 * Everything that can go wrong there is a question about layers and a map:
 * which blocks may be previewed at all, what each of them is called so a person
 * can tell three identical alternatives apart, and which binding any one layer
 * resolves against. None of it needs a canvas.
 */

import { describe, expect, it } from 'vitest';

import type { GroupBinding, SlotBinding, TagLayer } from './tag-template-types';
import { defaultImageProps, defaultShapeProps, defaultTextProps } from './tag-template-types';
import { previewBindingFor, previewBlockOf, previewableBlocks } from './preview';

// ---------------------------------------------------------------------------
// Fixtures, shaped like the seeded templates
// ---------------------------------------------------------------------------

function text(id: string, slot: SlotBinding, content: string): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 5,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: slot,
    text_override: null,
    props: { ...defaultTextProps(), text: content },
  };
}

function image(id: string, slot: SlotBinding): TagLayer {
  return { ...text(id, slot, ''), type: 'image', props: defaultImageProps() };
}

function shape(id: string): TagLayer {
  return { ...text(id, null, ''), type: 'shape', props: defaultShapeProps() };
}

function group(
  id: string,
  children: string[],
  binding: GroupBinding | null | undefined = {},
): TagLayer {
  return {
    ...shape(id),
    type: 'group',
    props: { kind: 'group', children, binding: binding ?? undefined },
  };
}

/**
 * The seed writes `binding: null` on a block that is NOT about a product, and
 * `binding: {}` on one that is meant to be bound but ships unbound. The
 * difference is what keeps the accessories strip out of the picker, so it has
 * to survive the fixture rather than be normalised away by the type.
 */
function unbindableGroup(id: string, children: string[]): TagLayer {
  const layer = group(id, children);
  (layer.props as { binding?: GroupBinding | null }).binding = null;
  return layer;
}

/** childId -> its group, the way the editor memoises it. */
function groupsOf(layers: TagLayer[]): Map<string, TagLayer> {
  const map = new Map<string, TagLayer>();
  for (const layer of layers) {
    if (layer.props.kind !== 'group') continue;
    for (const child of layer.props.children) map.set(child, layer);
  }
  return map;
}

/**
 * The Kitchen Sink Combo, cut down to what preview cares about: the main block,
 * an accessories strip whose title is an `included_accessories` slot, three
 * unbound alternatives that are identical apart from their position, and the
 * ungrouped brand band nobody previews.
 */
function sinkCombo(): TagLayer[] {
  return [
    shape('band'),
    image('main-hero', 'product_image'),
    text('main-code', 'code', 'Product code'),
    text('main-price', 'sell_price', ''),
    group('main', ['main-hero', 'main-code', 'main-price']),

    text('acc-title', 'included_accessories', 'Accessories Included'),
    image('acc-0', null),
    unbindableGroup('accessories', ['acc-title', 'acc-0']),

    image('alt-a-image', 'product_image'),
    text('alt-a-code', 'code', 'Product code'),
    group('alt-a', ['alt-a-image', 'alt-a-code']),

    image('alt-b-image', 'product_image'),
    text('alt-b-code', 'code', 'Product code'),
    group('alt-b', ['alt-b-image', 'alt-b-code']),

    image('alt-c-image', 'product_image'),
    text('alt-c-code', 'code', 'Product code'),
    group('alt-c', ['alt-c-image', 'alt-c-code']),
  ];
}

// ---------------------------------------------------------------------------
// previewableBlocks
// ---------------------------------------------------------------------------

describe('previewableBlocks', () => {
  it('lists every block that is about a product, in document order', () => {
    expect(previewableBlocks(sinkCombo()).map((b) => b.groupId)).toEqual([
      'main',
      'alt-a',
      'alt-b',
      'alt-c',
    ]);
  });

  it('leaves out the accessories strip, which is written unbindable', () => {
    expect(previewableBlocks(sinkCombo()).map((b) => b.groupId)).not.toContain(
      'accessories',
    );
  });

  it('leaves out a group of plain shapes, which has nothing to resolve', () => {
    const layers = [shape('a'), shape('b'), group('plain', ['a', 'b'])];
    expect(previewableBlocks(layers)).toEqual([]);
  });

  it('asks for a SET when the block holds the set members slot', () => {
    const layers = [
      text('members', 'set_members', 'Set members'),
      text('set-code', 'code', 'Set code'),
      group('set-block', ['members', 'set-code']),
    ];
    expect(previewableBlocks(layers)[0].mode).toBe('set');
  });

  it('asks for a product otherwise', () => {
    expect(previewableBlocks(sinkCombo())[0].mode).toBe('product');
  });

  it('names three identical alternatives so they can be told apart', () => {
    const labels = previewableBlocks(sinkCombo()).map((b) => b.label);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels).toEqual([
      'Group (3) - block 1 - Product code',
      'Group (2) - block 2 - Product code',
      'Group (2) - block 3 - Product code',
      'Group (2) - block 4 - Product code',
    ]);
  });

  it('never labels a block with its id', () => {
    for (const block of previewableBlocks(sinkCombo())) {
      expect(block.label).not.toContain(block.groupId);
    }
  });
});

// ---------------------------------------------------------------------------
// previewBindingFor
// ---------------------------------------------------------------------------

describe('previewBindingFor', () => {
  const layers = sinkCombo();
  const groupOf = groupsOf(layers);
  const find = (id: string) => layers.find((l) => l.id === id)!;

  it('resolves two previewed blocks against their own products', () => {
    const previews = {
      main: { product_id: 'p-main' },
      'alt-a': { product_id: 'p-alt' },
    };
    expect(previewBindingFor(find('main-code'), previews, groupOf, layers)).toEqual({
      product_id: 'p-main',
    });
    expect(previewBindingFor(find('alt-a-code'), previews, groupOf, layers)).toEqual({
      product_id: 'p-alt',
    });
  });

  it('leaves an unpreviewed block on its placeholders', () => {
    const previews = { main: { product_id: 'p-main' } };
    expect(previewBindingFor(find('alt-b-code'), previews, groupOf, layers)).toBeUndefined();
    expect(previewBindingFor(find('alt-b'), previews, groupOf, layers)).toBeUndefined();
  });

  it('answers for the group layer itself, not only its children', () => {
    const previews = { 'alt-c': { product_id: 'p-c' } };
    expect(previewBindingFor(find('alt-c'), previews, groupOf, layers)).toEqual({
      product_id: 'p-c',
    });
  });

  it('resolves nothing anywhere while no block is previewed', () => {
    for (const layer of layers) {
      expect(previewBindingFor(layer, {}, groupOf, layers)).toBeUndefined();
    }
  });

  it('follows the first previewed block for a slot layer in no group', () => {
    const loose = [...layers, text('loose-code', 'code', 'Product code')];
    const previews = {
      'alt-b': { product_id: 'p-b' },
      main: { product_id: 'p-main' },
    };
    // Document order decides, not the order the previews were chosen in.
    expect(
      previewBindingFor(loose[loose.length - 1], previews, groupsOf(loose), loose),
    ).toEqual({ product_id: 'p-main' });
  });

  it('leaves an unbound layer in no group alone', () => {
    expect(
      previewBindingFor(find('band'), { main: { product_id: 'p' } }, groupOf, layers),
    ).toBeUndefined();
  });

  it('leaves the accessories strip alone, previewed or not', () => {
    const previews = { main: { product_id: 'p-main' } };
    expect(previewBindingFor(find('acc-title'), previews, groupOf, layers)).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// previewBlockOf
// ---------------------------------------------------------------------------

describe('previewBlockOf', () => {
  const layers = sinkCombo();
  const blocks = previewableBlocks(layers);
  const groupOf = groupsOf(layers);
  const find = (id: string) => layers.find((l) => l.id === id)!;

  it('finds the block a selected child belongs to', () => {
    expect(previewBlockOf(find('alt-b-image'), blocks, groupOf)?.groupId).toBe('alt-b');
  });

  it('finds the block when the block itself is selected', () => {
    expect(previewBlockOf(find('main'), blocks, groupOf)?.groupId).toBe('main');
  });

  it('finds nothing for a layer outside every previewable block', () => {
    expect(previewBlockOf(find('band'), blocks, groupOf)).toBeNull();
    expect(previewBlockOf(find('acc-title'), blocks, groupOf)).toBeNull();
  });
});
