/** PRICETAG-TEMPLATE-PER-PRODUCT R6: one sheet builder for the preview and the approve screen. */
import { describe, expect, it } from 'vitest';

import { buildRequestSheet, defaultTemplateFor, type TagRequestTag } from './request-tags';
import type { TagTemplate } from './tag-template-types';

function template(id: string, family = 'ala_carte', width = 80, height = 50): TagTemplate {
  return {
    id,
    name: id,
    family,
    doc: { layers: [], width_mm: width, height_mm: height },
    print_size: { width_mm: width, height_mm: height },
    created_at: '',
    updated_at: '',
  } as TagTemplate;
}

function tag(id: string, lineId: string, quantity = 1): TagRequestTag {
  return {
    id,
    quantity,
    line: { id: lineId, line_type: 'product', product_id: `p-${lineId}`, product_set_id: null, quantity },
  };
}

describe('buildRequestSheet', () => {
  it('places every tag from its own line template, keyed on the request tag id', () => {
    let n = 0;
    const doc = buildRequestSheet(
      [tag('t1', 'l1'), tag('t2', 'l2')],
      { l1: template('A'), l2: template('B', 'ala_carte', 120, 90) },
      () => `id-${(n += 1)}`,
    );
    expect(doc.kind).toBe('tag_sheet');
    const placed = doc.sheets.flatMap((sheet) => sheet.tags);
    expect(placed.map((p) => [p.request_tag_id, p.template_id]).sort()).toEqual([
      ['t1', 'A'],
      ['t2', 'B'],
    ]);
    const b = placed.find((p) => p.request_tag_id === 't2');
    expect([b?.width_mm, b?.height_mm]).toEqual([120, 90]);
  });

  it('prints quantity copies and skips a line with no template', () => {
    const doc = buildRequestSheet([tag('t1', 'l1', 3), tag('t2', 'l2')], { l1: template('A') }, () => 'x');
    const placed = doc.sheets.flatMap((sheet) => sheet.tags);
    expect(placed).toHaveLength(3);
    expect(new Set(placed.map((p) => p.request_tag_id))).toEqual(new Set(['t1']));
  });
});

describe('defaultTemplateFor', () => {
  const templates = [template('sink', 'sink_combo'), template('plain', 'ala_carte'), template('picked')];

  it('prefers the line stored template', () => {
    expect(defaultTemplateFor({ line_type: 'product', tag_template_id: 'picked' }, templates, 'SRTKS1')?.id).toBe(
      'picked',
    );
  });

  it('falls back to the family rule when the stored one is not on offer', () => {
    expect(defaultTemplateFor({ line_type: 'product', tag_template_id: 'gone' }, templates, 'SRTKS1')?.id).toBe(
      'sink',
    );
    expect(defaultTemplateFor({ line_type: 'product' }, templates, 'SRTKS1')?.id).toBe('sink');
  });
});
