/**
 * PRICETAG-ACCESSORIES (A6): a box too small for its list never drops cards silently. Walks a tag
 * sheet the way the print page does and names every tag that loses accessories.
 */
import { describe, expect, it } from 'vitest';

import { accessoryDrops } from './accessory-drops';
import { defaultAccessoriesProps, type TagAccessory, type TagSheetDoc } from './tag-template-types';

const item = (n: number): TagAccessory => ({ id: `a${n}`, name: `ITEM ${n}`, spec: null, image: null });

function sheet(height: number, visible = true): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [
      {
        id: 's1',
        tags: ['t1', 't2'].map((tagId) => ({
          id: `placed-${tagId}`,
          template_id: 'tpl',
          request_tag_id: tagId,
          x_mm: 0,
          y_mm: 0,
          width_mm: 148,
          height_mm: 105,
          layers: [
            {
              id: 'acc',
              type: 'accessories',
              x_mm: 0,
              y_mm: 0,
              width_mm: 40,
              height_mm: height,
              rotation_deg: 0,
              z_index: 1,
              locked: false,
              visible,
              slot_binding: null,
              text_override: null,
              props: defaultAccessoriesProps(),
            },
          ],
        })),
      },
    ],
  } as unknown as TagSheetDoc;
}

const rows: Record<string, { tag_label: string; accessories: TagAccessory[] }> = {
  t1: { tag_label: '1a', accessories: [item(1), item(2), item(3), item(4), item(5)] },
  t2: { tag_label: '2a', accessories: [item(1)] },
};

describe('accessoryDrops', () => {
  it('names the tag whose box is too small, with how many accessories it loses', () => {
    const drops = accessoryDrops(sheet(40), (id) => rows[id]);
    expect(drops).toHaveLength(1);
    expect(drops[0].tagLabel).toBe('1a');
    expect(drops[0].dropped).toBeGreaterThan(0);
  });

  it('says nothing when everything fits', () => {
    expect(accessoryDrops(sheet(200), (id) => rows[id])).toEqual([]);
  });

  it('ignores a hidden box', () => {
    expect(accessoryDrops(sheet(40, false), (id) => rows[id])).toEqual([]);
  });
});
