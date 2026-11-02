/** PRICETAG-TEMPLATE-PER-PRODUCT AC-10/AC-14: the line's Template field state and payload. */
import { describe, expect, it } from 'vitest';

import {
  draftLinesPayload,
  emptyDraftLine,
  lineNeedsTemplate,
  lineTemplateState,
  type DraftLine,
} from './price-tag-draft-lines';

const opt = (id: string) => ({ id, name: `T ${id}`, family: 'ala_carte', published: true, width_mm: 80, height_mm: 50 });

function line(patch: Partial<DraftLine>): DraftLine {
  return { ...emptyDraftLine(), key: 'k', product_id: 'p1', ...patch };
}

describe('lineTemplateState', () => {
  it('is loading until the lookup answered for THIS product', () => {
    expect(lineTemplateState(line({ tag_templates_for: null })).kind).toBe('loading');
    expect(lineTemplateState(line({ tag_templates_for: 'other', tag_templates: [opt('a')] })).kind).toBe('loading');
  });

  it('none / single / many', () => {
    expect(lineTemplateState(line({ tag_templates_for: 'p1', tag_templates: [] })).kind).toBe('none');
    expect(lineTemplateState(line({ tag_templates_for: 'p1', tag_templates: [opt('a')] })).kind).toBe('single');
    const many = lineTemplateState(
      line({ tag_templates_for: 'p1', tag_templates: [opt('a'), opt('b')], tag_template_id: 'b' }),
    );
    expect(many.kind === 'many' && many.picked?.id).toBe('b');
  });

  it('a set line never has a field', () => {
    expect(lineTemplateState(line({ line_type: 'product_set', product_id: null, product_set_id: 's1' })).kind).toBe(
      'none',
    );
  });
});

describe('lineNeedsTemplate', () => {
  it('only a many-template line with no valid pick', () => {
    const many = { tag_templates_for: 'p1', tag_templates: [opt('a'), opt('b')] };
    expect(lineNeedsTemplate(line({ ...many, tag_template_id: null }))).toBe(true);
    expect(lineNeedsTemplate(line({ ...many, tag_template_id: 'zzz' }))).toBe(true);
    expect(lineNeedsTemplate(line({ ...many, tag_template_id: 'a' }))).toBe(false);
    expect(lineNeedsTemplate(line({ tag_templates_for: 'p1', tag_templates: [opt('a')] }))).toBe(false);
  });
});

describe('draftLinesPayload', () => {
  it('sends the pick on a product line and null on a set line', () => {
    const [product, set] = draftLinesPayload([
      line({ tag_template_id: 'a' }),
      line({ line_type: 'product_set', product_id: null, product_set_id: 's1', tag_template_id: 'a' }),
    ]);
    expect(product.tag_template_id).toBe('a');
    expect(set.tag_template_id).toBeNull();
  });
});
