/** SPEC-SHEET-DESIGNER-PARITY B3 follow-up: the price tag Insert field never offers the spec-sheet-only paths. */
import { describe, expect, it } from 'vitest';

import { PRICE_TAG_FIELD_GROUPS, mergeFieldCatalog } from './merge-fields';

const SPEC_SHEET_ONLY = [
  'line.description',
  'line.uom',
  'line.technical_spec',
  'line.notes',
  'line.item_label',
  'doc.subject_title',
  'doc.page_no',
  'accessory.1.code',
];

describe('mergeFieldCatalog for a price tag template', () => {
  it('leaves out the spec sheet only paths but keeps the Line fields that print there', () => {
    const paths = mergeFieldCatalog([], PRICE_TAG_FIELD_GROUPS).map((f) => f.path);
    for (const path of SPEC_SHEET_ONLY) expect(paths).not.toContain(path);
    expect(paths).toContain('line.quantity');
    expect(paths).toContain('line.parts');
  });

  it('a spec sheet template (no group filter) keeps them', () => {
    const paths = mergeFieldCatalog([]).map((f) => f.path);
    for (const path of SPEC_SHEET_ONLY) expect(paths).toContain(path);
  });
});
