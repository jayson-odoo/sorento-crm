/**
 * PRICETAG-DESIGNER-GAPS item 3 (crew pass, 5 Nov): a Feature icons layer
 * reads the product it is bound to (main item or a combo position) with no
 * slot binding of its own, so "Preview the whole tag" must offer itself for
 * it and the layer must follow that preview like a loose slot-bound layer.
 */
import { describe, expect, it } from 'vitest';

import type { TagLayer } from './tag-template-types';
import { defaultFeatureIconsProps } from './tag-template-types';
import { WHOLE_TAG_BLOCK_ID, previewBindingFor, wholeTagBlock } from './preview';

function iconsLayer(id = 'icons'): TagLayer {
  return {
    id,
    type: 'feature_icons',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultFeatureIconsProps(),
  } as TagLayer;
}

describe('Feature icons and the whole-tag preview', () => {
  it('offers the whole-tag preview on a tag whose only data layer is Feature icons', () => {
    expect(wholeTagBlock([iconsLayer()])).toEqual(
      expect.objectContaining({ groupId: WHOLE_TAG_BLOCK_ID, mode: 'product' }),
    );
  });

  it('a loose Feature icons layer follows the whole-tag preview product', () => {
    const layers = [iconsLayer()];
    const previews = { [WHOLE_TAG_BLOCK_ID]: { product_id: 'p-mixer' } };
    expect(previewBindingFor(layers[0], previews, new Map())).toEqual({
      product_id: 'p-mixer',
    });
  });

  it('stays unresolved while nothing is previewed', () => {
    expect(previewBindingFor(iconsLayer(), {}, new Map())).toBeUndefined();
  });
});
