/**
 * PRICETAG-UPGRADE-VARIANTS review fix round 1, item 5a: the dropped-icon warning counts a layer on
 * "All variants" with the same rule the renderers draw it with (`layerFeatureIcons`): the union of
 * the line's own icons and every variant's, not the line's own alone.
 */
import { describe, expect, it } from 'vitest';

import { featureIconDrops } from './feature-icon-drops';
import { FAMILY_VARIANTS, spec, TRAP_ICONS } from './test-support/upgrade-variants-fixtures';
import type { TagSheetDoc } from './tag-template-types';

const URLS = Object.fromEntries(TRAP_ICONS.map((i) => [i.id, `https://cdn/${i.id}.png`]));

/** One placed tag with a feature icons layer that holds two 8 mm icons (8 + 2 + 8 = 18 of 20). */
function sheet(subjectSlot?: unknown): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [
      {
        id: 's1',
        tags: [
          {
            id: 'placed-t1',
            template_id: 'tpl',
            request_tag_id: 't1',
            x_mm: 0,
            y_mm: 0,
            width_mm: 90,
            height_mm: 60,
            layers: [
              {
                id: 'fi',
                type: 'feature_icons',
                x_mm: 0,
                y_mm: 0,
                width_mm: 20,
                height_mm: 10,
                rotation_deg: 0,
                z_index: 1,
                locked: false,
                visible: true,
                slot_binding: null,
                text_override: null,
                props: {
                  kind: 'feature_icons',
                  iconSize_mm: 8,
                  gap_mm: 2,
                  align: 'left',
                  ...(subjectSlot ? { subjectSlot } : {}),
                },
              },
            ],
          },
        ],
      },
    ],
  } as unknown as TagSheetDoc;
}

const familyRow = {
  tag_label: '1a',
  specs: [spec('trap_length', '250', '250'), spec('trap_type', 'S Trap', 's_trap')],
  variants: FAMILY_VARIANTS.map((v) => ({ product_id: `id-${v.code}`, ...v })),
};

describe('featureIconDrops on "All variants"', () => {
  it('counts the family union: five icons in a box for two drops three', () => {
    const drops = featureIconDrops(sheet({ kind: 'variants' }), () => familyRow, TRAP_ICONS, URLS);
    expect(drops).toEqual([{ tagLabel: '1a', dropped: 3 }]);
  });

  it('a layer on the main product counts only the line own icon (nothing dropped)', () => {
    expect(featureIconDrops(sheet(), () => familyRow, TRAP_ICONS, URLS)).toEqual([]);
  });

  it('a row with no variants counts its own icons only', () => {
    const leaf = { ...familyRow, variants: [] };
    expect(featureIconDrops(sheet({ kind: 'variants' }), () => leaf, TRAP_ICONS, URLS)).toEqual([]);
  });
});
