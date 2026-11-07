/**
 * PRICETAG-COMBO-FORMAT fix round 1, R6: a loaded line keeps its saved template even when it no
 * longer fits the line's LP / SP (AC-37). The select shows it by name and the payload re-sends the
 * same id; only a user change re-filters.
 *
 * Written test-FIRST. Today `lineTemplateState` filters by the line's type, so a saved LP-only
 * template on an SP line vanishes (or the line reads "No SP template linked") and the next save
 * would drop it.
 */
import { describe, expect, it } from 'vitest';

import {
  draftLinesPayload,
  emptyDraftLine,
  lineTemplateState,
  type DraftLine,
} from './price-tag-draft-lines';

const tpl = (id: string, price_type: string | null, flags: { s?: boolean } = {}) => ({
  id,
  name: `Tpl ${id}`,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  price_type,
  default_list: false,
  default_selling: !!flags.s,
});

function savedSpLine(options: unknown[]): DraftLine {
  return {
    ...emptyDraftLine(),
    key: 'l1',
    line_type: 'product',
    product_id: 'p1',
    code: 'ZZT1',
    name: 'ZZT 1',
    price_type: 'selling',
    tag_templates_for: 'p1',
    tag_templates: options,
    // Saved while the template was LP-capable; the owner has since typed it LP only.
    tag_template_id: 'lp',
  } as unknown as DraftLine;
}

function shownId(line: DraftLine): string | null {
  const state = lineTemplateState(line, 'list');
  if (state.kind === 'many') return state.picked?.id ?? null;
  if (state.kind === 'single') return state.template.id;
  return null;
}

describe('a saved template that no longer fits is kept (R6, AC-37)', () => {
  it('R6: with another fitting link, the saved template is still the picked one, by name', () => {
    const line = savedSpLine([tpl('lp', 'list'), tpl('sp', 'selling', { s: true })]);
    expect(shownId(line)).toBe('lp');
    const state = lineTemplateState(line, 'list');
    const names =
      state.kind === 'many' ? state.options.map((o) => o.name) : state.kind === 'single' ? [state.template.name] : [];
    expect(names).toContain('Tpl lp');
  });

  it('R6: when the item has no fitting link at all, the saved template shows rather than "No SP template linked"', () => {
    const line = savedSpLine([tpl('lp', 'list')]);
    expect(lineTemplateState(line, 'list').kind).not.toBe('mismatch');
    expect(shownId(line)).toBe('lp');
  });

  it('R6: the payload re-sends the same template id', () => {
    const line = savedSpLine([tpl('lp', 'list'), tpl('sp', 'selling', { s: true })]);
    expect(draftLinesPayload([line], 'list')[0].tag_template_id).toBe('lp');
  });

  it('R6: a line with no saved template still offers only the fitting ones (unchanged)', () => {
    const line = { ...savedSpLine([tpl('lp', 'list'), tpl('sp', 'selling', { s: true }), tpl('both', 'both')]), tag_template_id: null };
    const state = lineTemplateState(line as DraftLine, 'list');
    expect(state.kind).toBe('many');
    if (state.kind === 'many') expect(state.options.map((o) => o.id).sort()).toEqual(['both', 'sp']);
  });
});
