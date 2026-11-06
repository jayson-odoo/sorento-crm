/**
 * Crew browser pass (5 Nov): an icon that does not fit its layer box is not drawn, and that must
 * never be silent. `featureIconDrops` walks a tag sheet the way the print page does (each placed
 * tag, each feature icons layer, its subject's specs) and names every tag that loses icons.
 */
import { describe, expect, it } from 'vitest';

import { featureIconDrops } from './feature-icon-drops';
import type { TagSheetDoc } from './tag-template-types';

const spec = (key: string, value: string, raw: string) => ({ key, label: key, value, unit: null, raw });

const ICONS = [
  { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['mixer'] },
  { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
];
const URLS = { cold: 'https://cdn/cold.png', hot: 'https://cdn/hot.png' };

function sheet(widths: Record<string, number>): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [
      {
        id: 's1',
        tags: Object.entries(widths).map(([tagId, width]) => ({
          id: `placed-${tagId}`,
          template_id: 'tpl',
          request_tag_id: tagId,
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
              width_mm: width,
              height_mm: 10,
              rotation_deg: 0,
              z_index: 1,
              locked: false,
              visible: true,
              slot_binding: null,
              text_override: null,
              props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 2, align: 'left' },
            },
          ],
        })),
      },
    ],
  } as unknown as TagSheetDoc;
}

const data = (label: string) => ({ tag_label: label, specs: [spec('water_supply', 'Mixer', 'mixer')] });

describe('featureIconDrops', () => {
  it('names the tag whose box is too narrow, with how many icons it loses', () => {
    const doc = sheet({ t1: 40, t2: 10 });
    const out = featureIconDrops(doc, (id) => (id === 't1' ? data('1a') : data('2a')), ICONS, URLS);
    expect(out).toEqual([{ tagLabel: '2a', dropped: 1 }]);
  });

  it('lists nothing when every icon fits', () => {
    expect(featureIconDrops(sheet({ t1: 40 }), () => data('1a'), ICONS, URLS)).toEqual([]);
  });

  it('counts only icons that would print (an icon with no signed URL is not drawn anyway)', () => {
    const out = featureIconDrops(sheet({ t1: 10 }), () => data('1a'), ICONS, { cold: URLS.cold });
    expect(out).toEqual([]);
  });

  it('ignores a tag with no data and a missing document', () => {
    expect(featureIconDrops(sheet({ t1: 10 }), () => null, ICONS, URLS)).toEqual([]);
    expect(featureIconDrops(null, () => data('1a'), ICONS, URLS)).toEqual([]);
  });
});
