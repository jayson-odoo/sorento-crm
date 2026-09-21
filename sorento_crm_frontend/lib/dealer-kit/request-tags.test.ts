/**
 * The arithmetic behind designing a request's tags (D51).
 *
 * Which template a line starts from, what its tag looks like the moment it is
 * cloned, and where the quantity copies land on the sheets. All of it is a pure
 * function over the request lines and the templates, so the parts a marketing
 * user would notice going wrong are pinned without a canvas.
 */

import { describe, expect, it } from 'vitest';

import type {
  ImpositionConfig,
  LineTagData,
  PlacedTag,
  TagLayer,
  TagTemplate,
  TagTemplateFamily,
} from './tag-template-types';
import { IMPOSITION_PRESETS, defaultTextProps } from './tag-template-types';
import { PRODUCT_BLOCK_SIZE, SET_BLOCK_SIZE } from './product-block';
import {
  applyDesignToAllTags,
  applyDesignToSiblings,
  autoArrange,
  copiesOf,
  defaultTemplateFor,
  DEFAULT_IMPOSITION,
  impositionFit,
  normaliseImpositionPreset,
  PRINT_MARGIN_MM,
  resizeAllTags,
  resizeTag,
  resolveSizeGrid,
  resolveTagSize,
  starterTemplateFor,
  tagForTag,
  tagSizeBounds,
  tagSizePresets,
  templateFromTag,
} from './request-tags';
import type { TagRequestTag } from './request-tags';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function textLayer(id: string, z: number): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 2,
    y_mm: 3,
    width_mm: 40,
    height_mm: 10,
    rotation_deg: 0,
    z_index: z,
    locked: false,
    visible: true,
    slot_binding: 'code',
    text_override: null,
    props: defaultTextProps(),
  };
}

function groupLayer(id: string, children: string[]): TagLayer {
  return {
    id,
    type: 'group',
    x_mm: 0,
    y_mm: 0,
    width_mm: 60,
    height_mm: 40,
    rotation_deg: 0,
    z_index: 10,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'group', children },
  };
}

function template(
  id: string,
  family: TagTemplateFamily,
  size = { width_mm: 60, height_mm: 40 },
): TagTemplate {
  return {
    id,
    name: `${family} template`,
    family,
    doc: {
      layers: [textLayer(`${id}-code`, 1), groupLayer(`${id}-group`, [`${id}-code`])],
      width_mm: size.width_mm,
      height_mm: size.height_mm,
    },
    print_size: size,
    created_at: '2026-08-30T00:00:00Z',
    updated_at: '2026-08-30T00:00:00Z',
  };
}

const TEMPLATES: TagTemplate[] = [
  template('t-sink', 'sink_combo'),
  template('t-wc', 'wc'),
  template('t-set', 'furniture_set'),
  template('t-plain', 'ala_carte'),
];

function productLine(id: string, quantity = 1) {
  return { id, line_type: 'product' as const, product_id: `p-${id}`, product_set_id: null, quantity };
}

function setLine(id: string, quantity = 1) {
  return {
    id,
    line_type: 'product_set' as const,
    product_id: null,
    product_set_id: `s-${id}`,
    quantity,
  };
}

// A line carries tags since S3 (D3). The everyday case is one tag per line, so
// the tag reuses the line's id: the ids these tests assert on stay the ones the
// pre-S3 suite asserted on, and what they guarded stays guarded.
function productTag(id: string, quantity = 1): TagRequestTag {
  return { id, quantity, line: productLine(id, quantity) };
}

function setTag(id: string, quantity = 1): TagRequestTag {
  return { id, quantity, line: setLine(id, quantity) };
}

// A4, auto preset - kept only for `normaliseImpositionPreset`'s own tests
// (the old per-request page/bleed/gap fields it migrates off). r10 S7
// replaced everything else here: `autoArrange` no longer takes a page at
// all - every sheet is the fixed `DEFAULT_IMPOSITION` A4 page.
const PAGE_A4: ImpositionConfig = { preset: 'auto', ...IMPOSITION_PRESETS.auto };

let layerSeq = 0;
const newId = () => `layer-${(layerSeq += 1)}`;

// ---------------------------------------------------------------------------
// defaultTemplateFor
// ---------------------------------------------------------------------------

describe('defaultTemplateFor', () => {
  it('takes the template whose family matches the code prefix', () => {
    expect(defaultTemplateFor(productLine('l1'), TEMPLATES, 'SRTKS2435')?.id).toBe('t-sink');
    expect(defaultTemplateFor(productLine('l2'), TEMPLATES, 'SRTWC8036-SH')?.id).toBe('t-wc');
  });

  it('a set line takes the furniture set template whatever its code', () => {
    expect(defaultTemplateFor(setLine('l3'), TEMPLATES, 'SRTWC8608')?.id).toBe('t-set');
  });

  it('falls back to ala carte when the family has no template', () => {
    const without = TEMPLATES.filter((t) => t.family !== 'wc');
    expect(defaultTemplateFor(productLine('l4'), without, 'SRTWC8036')?.id).toBe('t-plain');
  });

  it('falls back to the first template when there is no ala carte either', () => {
    const only = [template('t-mirror', 'mirror')];
    expect(defaultTemplateFor(productLine('l5'), only, 'SRTWC8036')?.id).toBe('t-mirror');
  });

  it('answers null when there is no template at all', () => {
    expect(defaultTemplateFor(productLine('l6'), [], 'SRTKS2435')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// starterTemplateFor
// ---------------------------------------------------------------------------

function lineTagData(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    tag_id: 'l1',
    line_id: 'l1',
    tag_label: '1a',
    open_groups: [],
    parts: [],
    code: 'SRT-1234',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: 'Stainless steel\nOverflow included',
    specs: [],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
    ...overrides,
  };
}

describe('starterTemplateFor', () => {
  it('builds the product block layer set - and slots - from the resolved line', () => {
    const line = productLine('l1');
    const data = lineTagData();
    const source = starterTemplateFor(line, data, newId);

    // image, code, name, dimensions, spec_lines, price_badge + the wrapping group.
    expect(source.doc.layers).toHaveLength(7);

    const slots = source.doc.layers.map((l) => l.slot_binding).filter(Boolean);
    expect(slots).toEqual(
      expect.arrayContaining(['product_image', 'code', 'name', 'dimensions', 'spec_lines', 'list_price']),
    );

    const codeLayer = source.doc.layers.find((l) => l.slot_binding === 'code');
    expect(codeLayer?.props).toMatchObject({ kind: 'text', text: 'SRT-1234' });
    const nameLayer = source.doc.layers.find((l) => l.slot_binding === 'name');
    expect(nameLayer?.props).toMatchObject({ kind: 'text', text: 'Kitchen Sink' });
    const dimensionsLayer = source.doc.layers.find((l) => l.slot_binding === 'dimensions');
    expect(dimensionsLayer?.props).toMatchObject({ kind: 'text', text: '800 x 500 x 220 mm' });
    const specLayer = source.doc.layers.find((l) => l.slot_binding === 'spec_lines');
    expect(specLayer?.props).toMatchObject({
      kind: 'text',
      text: 'Stainless steel\nOverflow included',
    });
  });

  it('never throws on a line whose price data has not resolved yet', () => {
    const line = productLine('l2');
    expect(() => starterTemplateFor(line, undefined, newId)).not.toThrow();

    const source = starterTemplateFor(line, undefined, newId);
    const codeLayer = source.doc.layers.find((l) => l.slot_binding === 'code');
    expect(codeLayer?.props).toMatchObject({ kind: 'text', text: '' });
    // Still a complete block: an unresolved line must not draw fewer layers.
    expect(source.doc.layers).toHaveLength(7);
  });

  it('draws the promo price only when the line is showing its promo price AND has one', () => {
    const line = productLine('l3');

    const promo = starterTemplateFor(
      line,
      lineTagData({ show_promo_price: true, sell_price: 899 }),
      newId,
    );
    const promoBadge = promo.doc.layers.find((l) => l.props.kind === 'price_badge');
    expect(promoBadge).toMatchObject({
      slot_binding: 'sell_price',
      props: { variant: 'promo' },
    });

    const noPromoValue = starterTemplateFor(
      line,
      lineTagData({ show_promo_price: true, sell_price: null }),
      newId,
    );
    const listBadge1 = noPromoValue.doc.layers.find((l) => l.props.kind === 'price_badge');
    expect(listBadge1).toMatchObject({
      slot_binding: 'list_price',
      props: { variant: 'list_only' },
    });

    const promoSwitchedOff = starterTemplateFor(
      line,
      lineTagData({ show_promo_price: false, sell_price: 899 }),
      newId,
    );
    const listBadge2 = promoSwitchedOff.doc.layers.find((l) => l.props.kind === 'price_badge');
    expect(listBadge2).toMatchObject({
      slot_binding: 'list_price',
      props: { variant: 'list_only' },
    });
  });

  it('is always the ala carte family - a starter has no family of its own', () => {
    const source = starterTemplateFor(productLine('l4'), lineTagData(), newId);
    expect(source.family).toBe('ala_carte');
  });

  it('is sized at the default product block footprint, not any template size', () => {
    const source = starterTemplateFor(productLine('l5'), lineTagData(), newId);
    expect(source.print_size).toEqual(PRODUCT_BLOCK_SIZE);
    expect(source.doc.width_mm).toBe(PRODUCT_BLOCK_SIZE.width_mm);
    expect(source.doc.height_mm).toBe(PRODUCT_BLOCK_SIZE.height_mm);
  });

  it('binds the group to the LINE\'S REAL product id, never the line id itself', () => {
    const line = productLine('l7');
    const source = starterTemplateFor(line, lineTagData(), newId);
    const group = source.doc.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_id: 'p-l7' } });
    // The line id and the product id are deliberately different strings in
    // this fixture, so a binding of { product_id: 'l7' } - the line id
    // masquerading as the product id - would fail this assertion too.
    expect(group?.props).not.toMatchObject({ binding: { product_id: 'l7' } });
  });

  it('a set line gets a SET block - set_members text, no empty product-only slots - not buildProductBlock', () => {
    const line = setLine('l6');
    const data = lineTagData({
      code: 'BF-SET-01',
      name: 'Bathroom Furniture Set',
      set_members: '- A1 (Basin)\n- A2 (Tap)',
    });
    const source = starterTemplateFor(line, data, newId);

    expect(source.print_size).toEqual(SET_BLOCK_SIZE);
    expect(source.doc.width_mm).toBe(SET_BLOCK_SIZE.width_mm);
    expect(source.doc.height_mm).toBe(SET_BLOCK_SIZE.height_mm);

    const membersLayer = source.doc.layers.find((l) => l.slot_binding === 'set_members');
    expect(membersLayer?.props).toMatchObject({
      kind: 'text',
      text: '- A1 (Basin)\n- A2 (Tap)',
    });

    // A set has no product photo, dimensions or spec lines of its own - a
    // set-line starter must not carry the empty boxes buildProductBlock would
    // draw for them.
    const slots = source.doc.layers.map((l) => l.slot_binding).filter(Boolean);
    expect(slots).not.toEqual(
      expect.arrayContaining(['product_image', 'dimensions', 'spec_lines']),
    );

    // Bound to the set, not the line id and not a product id.
    const group = source.doc.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_set_id: 's-l6' } });
  });
});

// ---------------------------------------------------------------------------
// tagForTag
// ---------------------------------------------------------------------------

describe('tagForTag', () => {
  it('clones the template layers and binds the group to the line item', () => {
    const source = TEMPLATES[0];
    const tag = tagForTag(productTag('l1'), source, 'tag-1');

    expect(tag).toMatchObject({
      id: 'tag-1',
      template_id: 't-sink',
      request_tag_id: 'l1',
      x_mm: 0,
      y_mm: 0,
      width_mm: 60,
      height_mm: 40,
    });
    const group = tag.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_id: 'p-l1' } });
  });

  it('binds a set line to the product set', () => {
    const tag = tagForTag(setTag('l2'), TEMPLATES[2], 'tag-2');
    const group = tag.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_set_id: 's-l2' } });
  });

  it('never writes back into the template it was cloned from', () => {
    const source = template('t-copy', 'wc');
    const before = JSON.stringify(source.doc.layers);
    const tag = tagForTag(productTag('l3'), source, 'tag-3');

    tag.layers[0].x_mm = 99;
    tag.layers[0].text_override = 'typed over';

    expect(JSON.stringify(source.doc.layers)).toBe(before);
  });

  it('takes its size from the template print size, not from the doc', () => {
    const source = template('t-big', 'mirror', { width_mm: 100, height_mm: 70 });
    source.doc.width_mm = 10;
    source.doc.height_mm = 10;
    const tag = tagForTag(productTag('l4'), source, 'tag-4');
    expect(tag.width_mm).toBe(100);
    expect(tag.height_mm).toBe(70);
  });
});

// ---------------------------------------------------------------------------
// impositionFit (S6, D8): the golden set behind the "C x R = N per sheet"
// read-out replacing the fixed presets.
// ---------------------------------------------------------------------------

describe('impositionFit', () => {
  it('95 x 44.5 mm tags on A4 (3mm bleed, 2mm gap) fit 2 x 6 = 12 per sheet (AC-S6-2)', () => {
    expect(impositionFit(210, 297, 3, 2, 95, 44.5)).toEqual({ cols: 2, rows: 6, perSheet: 12 });
  });

  it('a tag that exactly fills the usable area fits exactly one', () => {
    expect(impositionFit(100, 100, 0, 0, 100, 100)).toEqual({ cols: 1, rows: 1, perSheet: 1 });
  });

  it('a tag wider than the usable area fits none (AC-S6-3)', () => {
    expect(impositionFit(50, 297, 3, 2, 95, 44.5)).toEqual({ cols: 0, rows: 6, perSheet: 0 });
  });

  it('a zero tag size + zero gap divides by zero (Infinity) - treated as 0, not an unbounded grid (S2)', () => {
    expect(impositionFit(210, 297, 3, 0, 0, 0)).toEqual({ cols: 0, rows: 0, perSheet: 0 });
  });

  it('a NaN input (empty/invalid field) never reaches the grid as NaN (S2)', () => {
    expect(impositionFit(NaN, 297, 3, 2, 95, 44.5)).toEqual({ cols: 0, rows: 6, perSheet: 0 });
  });

  it('clamps an absurd page/tag ratio to a ceiling per axis rather than materialising 10^5+ slots (S2)', () => {
    const fit = impositionFit(10000, 10000, 0, 0, 10, 10);
    expect(fit.cols).toBeLessThanOrEqual(200);
    expect(fit.rows).toBeLessThanOrEqual(200);
  });
});

// ---------------------------------------------------------------------------
// normaliseImpositionPreset - old presets migrate to 'auto' on load (S3, AC-S6-4)
// ---------------------------------------------------------------------------

describe('normaliseImpositionPreset', () => {
  it.each(['a4_3up', 'a4_2x2'] as const)('migrates a pre-S6 %s preset to auto', (preset) => {
    const result = normaliseImpositionPreset({ ...PAGE_A4, preset });
    expect(result.preset).toBe('auto');
  });

  it('leaves auto alone', () => {
    const doc = { ...PAGE_A4, preset: 'auto' as const };
    expect(normaliseImpositionPreset(doc)).toEqual(doc);
  });

  it('leaves custom alone - a field edit already wrote it deliberately', () => {
    const doc = { ...PAGE_A4, preset: 'custom' as const };
    expect(normaliseImpositionPreset(doc)).toEqual(doc);
  });

  it('keeps every other field unchanged', () => {
    const doc = { ...PAGE_A4, preset: 'a4_3up' as const, gap_mm: 7 };
    expect(normaliseImpositionPreset(doc)).toMatchObject({ gap_mm: 7 });
  });
});

// ---------------------------------------------------------------------------
// copiesOf, resolveSizeGrid and autoArrange (r10 S7)
// ---------------------------------------------------------------------------

function placed(
  id: string,
  tagId: string,
  templateId = 't-sink',
  width_mm = 60,
  height_mm = 40,
): PlacedTag {
  return {
    id,
    template_id: templateId,
    request_tag_id: tagId,
    x_mm: 0,
    y_mm: 0,
    width_mm,
    height_mm,
    layers: [textLayer(`${id}-l`, 1)],
  };
}

describe('copiesOf', () => {
  it('repeats each tag its quantity times, in line order', () => {
    const copies = copiesOf([
      { tag: placed('a', 'l1'), quantity: 2 },
      { tag: placed('b', 'l2'), quantity: 1 },
    ]);
    expect(copies.map((c) => c.id)).toEqual(['a-c0', 'a-c1', 'b-c0']);
  });

  it('a quantity below one still places the tag once', () => {
    expect(copiesOf([{ tag: placed('a', 'l1'), quantity: 0 }])).toHaveLength(1);
  });

  it('AC-S6-8: a print_excluded tag gets no copy at all', () => {
    const copies = copiesOf([
      { tag: placed('a', 'l1'), quantity: 2 },
      { tag: placed('b', 'l2'), quantity: 3, print_excluded: true },
      { tag: placed('c', 'l3'), quantity: 1 },
    ]);
    expect(copies.map((c) => c.id)).toEqual(['a-c0', 'a-c1', 'c-c0']);
  });
});

// ---------------------------------------------------------------------------
// autoArrange + resolveSizeGrid (r10 S7): sheets are always A4 portrait, a
// fixed 5mm printable margin on every edge (Q3), copies grouped by SIZE and
// packed at zero gap - a group turns 90deg when that seats more per sheet.
// `pinKeyForPlacement`/`pinnedFromDoc`/manual drag are RETIRED (AC-S7-4): a
// saved doc's positions are always re-flowed, never read back as a pin.
// ---------------------------------------------------------------------------

describe('resolveSizeGrid', () => {
  it('AC-S7-1: 66.7 x 31.9mm (Small) derives 3 cols x 9 rows, no rotation', () => {
    expect(resolveSizeGrid(66.7, 31.9, null)).toEqual({
      cols: 3,
      rows: 9,
      rotation: 0,
      perSheet: 27,
      configured: false,
    });
  });

  it('AC-S7-2: 143.5 x 100mm (Kitchen Sink) derives 2 x 2 TURNED - rotating seats more', () => {
    expect(resolveSizeGrid(143.5, 100, null)).toEqual({
      cols: 2,
      rows: 2,
      rotation: 90,
      perSheet: 4,
      configured: false,
    });
  });

  it('AC-S7-2: 98 x 140mm derives 2 x 2 with NO rotation - turning would seat fewer', () => {
    expect(resolveSizeGrid(98, 140, null)).toEqual({
      cols: 2,
      rows: 2,
      rotation: 0,
      perSheet: 4,
      configured: false,
    });
  });

  it('tolerance boundary (tester test list): 66.7mm fits 3 columns of 200mm usable width (200.1mm, within FIT_TOLERANCE_MM)', () => {
    expect(impositionFit(210, 297, PRINT_MARGIN_MM, 0, 66.7, 100).cols).toBe(3);
  });

  it('tolerance boundary: 67mm does NOT fit 3 columns (201mm, past the 0.5mm tolerance) - only 2', () => {
    expect(impositionFit(210, 297, PRINT_MARGIN_MM, 0, 67, 100).cols).toBe(2);
  });

  it('AC-S7-12: a configured 2 x 7 grid lays out at its own cell size (100 x 41), ignoring the derived fit', () => {
    const grid = resolveSizeGrid(100, 41, { cols: 2, rows: 7, turn: false });
    expect(grid).toEqual({
      cols: 2,
      rows: 7,
      rotation: 0,
      perSheet: 14,
      configured: true,
    });
  });

  it('AC-S7-13: a configured grid whose cell is smaller than the tag is refused, names the cell, and falls back to derive', () => {
    // 5 x 5 over the 200 x 287 usable block: each cell is 40 x 57.4mm, too
    // small for a 66.7 x 31.9mm tag on the width axis.
    const grid = resolveSizeGrid(66.7, 31.9, { cols: 5, rows: 5, turn: false });
    expect(grid.configured).toBe(false);
    expect(grid).toMatchObject({ cols: 3, rows: 9, rotation: 0, perSheet: 27 });
    expect(grid.refusedCell).toEqual({ width_mm: 40, height_mm: 57.4 });
  });

  it('a configured grid with turn: true rotates the tag inside its own cell', () => {
    const grid = resolveSizeGrid(41, 100, { cols: 2, rows: 7, turn: true });
    expect(grid).toEqual({
      cols: 2,
      rows: 7,
      rotation: 90,
      perSheet: 14,
      configured: true,
    });
  });
});

describe('autoArrange', () => {
  it('AC-S7-16: two DIFFERENT tags of the same size (one line split into two, D6) both get placed', () => {
    // Live browser finding, phase 3 review: "2 sheets / 3 tags" with only
    // one of two same-size sink tags actually placed, reproduced after save
    // and reload. Two distinct PlacedTag ids, two distinct request_tag_ids,
    // same template and same footprint - exactly what an open group's two
    // candidates look like once split.
    const result = autoArrange([
      { tag: placed('sink-copy-a', 'req-tag-a', 't-sink', 143.5, 100), quantity: 1 },
      { tag: placed('sink-copy-b', 'req-tag-b', 't-sink', 143.5, 100), quantity: 1 },
    ]);

    const placedIds = result.sheets.flatMap((s) => s.tags.map((t) => t.request_tag_id));
    expect(placedIds.sort()).toEqual(['req-tag-a', 'req-tag-b']);
  });

  it('AC-S7-1: 30 copies of 66.7 x 31.9mm (3 x 9 = 27/sheet) yields two sheets, 27 then 3', () => {
    const result = autoArrange([{ tag: placed('a', 'l1', 't-sink', 66.7, 31.9), quantity: 30 }]);

    expect(result.sheets).toHaveLength(2);
    expect(result.sheets[0].tags).toHaveLength(27);
    expect(result.sheets[1].tags).toHaveLength(3);
    expect(result.placement[0]).toMatchObject({ cols: 3, rows: 9, rotation: 0, capacity: 27 });
  });

  it('AC-S7-2: 4 copies of 143.5 x 100mm lay out 2 x 2, turned, on one sheet - the page itself stays portrait', () => {
    const result = autoArrange([{ tag: placed('a', 'l1', 't-sink', 143.5, 100), quantity: 4 }]);

    expect(result.sheets).toHaveLength(1);
    expect(result.sheets[0].tags).toHaveLength(4);
    expect(result.sheets[0].tags.every((t) => t.rotation === 90)).toBe(true);
    expect(result.placement[0]).toMatchObject({ cols: 2, rows: 2, rotation: 90, capacity: 4 });
    expect(DEFAULT_IMPOSITION.page_width_mm).toBeLessThan(DEFAULT_IMPOSITION.page_height_mm);
  });

  it('AC-S7-3: adjacent slots in a group touch - column 2 starts exactly where column 1 ends, same for rows', () => {
    const result = autoArrange([{ tag: placed('a', 'l1', 't-sink', 60, 40), quantity: 4 }]);
    const tags = result.sheets[0].tags;

    // Row-major: tags[0]/[1] are column 1/2 of row 1; find the first tag of row 2.
    expect(tags[1].x_mm - tags[0].x_mm).toBe(60);
    const rowTwo = tags.find((t) => t.y_mm > tags[0].y_mm);
    expect(rowTwo).toBeDefined();
    expect((rowTwo as PlacedTag).y_mm - tags[0].y_mm).toBe(40);
  });

  it('AC-S7-4: no output placement ever carries `pinned` - arrange always re-flows', () => {
    const result = autoArrange([{ tag: placed('a', 'l1', 't-sink', 60, 40), quantity: 3 }]);
    for (const tag of result.sheets[0].tags) {
      expect(tag).not.toHaveProperty('pinned');
    }
  });

  it('AC-S7-5: 2 kitchen sink (143.5 x 100, turned) + 30 small (66.7 x 31.9) yield three sheets in that order - kitchen sink first (larger area)', () => {
    const result = autoArrange([
      { tag: placed('sink', 'l1', 't-sink', 143.5, 100), quantity: 2 },
      { tag: placed('small', 'l2', 't-sink', 66.7, 31.9), quantity: 30 },
    ]);

    expect(result.sheets).toHaveLength(3);
    expect(result.sheets[0].tags).toHaveLength(2);
    expect(result.sheets[0].tags.every((t) => t.request_tag_id === 'l1')).toBe(true);
    expect(result.sheets[0].tags.every((t) => t.rotation === 90)).toBe(true);
    expect(result.sheets[1].tags).toHaveLength(27);
    expect(result.sheets[1].tags.every((t) => t.request_tag_id === 'l2')).toBe(true);
    expect(result.sheets[2].tags).toHaveLength(3);
  });

  it('AC-S7-12: a configured grid lookup is honoured per size group', () => {
    const result = autoArrange(
      [{ tag: placed('a', 'l1', 't-diy', 100, 41), quantity: 14 }],
      () => ({ cols: 2, rows: 7, turn: false }),
    );

    expect(result.sheets).toHaveLength(1);
    expect(result.placement[0]).toMatchObject({ cols: 2, rows: 7, rotation: 0, capacity: 14 });
    // The grid fills the usable block exactly (2 x 100 = 200, 7 x 41 = 287),
    // so the first tag sits at the block's own top-left, no centring offset.
    expect(result.sheets[0].tags[0]).toMatchObject({ x_mm: PRINT_MARGIN_MM, y_mm: PRINT_MARGIN_MM });
  });

  it('is deterministic: the same input answers the same document', () => {
    const items = [
      { tag: placed('a', 'l1', 't-sink', 60, 40), quantity: 2 },
      { tag: placed('b', 'l2', 't-sink', 60, 40), quantity: 2 },
    ];
    expect(autoArrange(items)).toEqual(autoArrange(items));
  });

  it('every copy carries the tag layers, its template and its line', () => {
    const result = autoArrange([{ tag: placed('a', 'l1', 't-wc'), quantity: 2 }]);
    for (const tag of result.sheets[0].tags) {
      expect(tag.template_id).toBe('t-wc');
      expect(tag.request_tag_id).toBe('l1');
      expect(tag.layers).toHaveLength(1);
    }
  });

  it('answers one empty sheet and no placement when the request has nothing to place', () => {
    const result = autoArrange([]);
    expect(result.sheets).toEqual([{ id: 'sheet-1', tags: [] }]);
    expect(result.placement).toEqual([]);
  });

  it('AC-S7-10 (existing AC-S6-3 of r6 kept): a tag too large for the page in both rotations still gets one overflowing centred slot', () => {
    const result = autoArrange([{ tag: placed('a', 'l1', 't-sink', 400, 400), quantity: 1 }]);
    expect(result.sheets).toHaveLength(1);
    expect(result.sheets[0].tags).toHaveLength(1);
    expect(result.placement[0].capacity).toBe(0);
  });

  it('AC-S6-8/S6-12: a print_excluded tag never reaches a sheet or the placement/sheet counts', () => {
    const result = autoArrange([
      { tag: placed('a', 'l1', 't-sink', 60, 40), quantity: 2 },
      { tag: placed('b', 'l2', 't-sink', 60, 40), quantity: 5, print_excluded: true },
    ]);
    const ids = result.sheets.flatMap((s) => s.tags.map((t) => t.request_tag_id));
    expect(ids).toEqual(['l1', 'l1']);
  });
});


// ---------------------------------------------------------------------------
// Tag size bounds + refusal (r10 S7, AC-S7-7): no longer per-imposition -
// every sheet is the same A4 page with the same 5mm printable margin, so the
// ceiling is a constant, page minus 10mm per axis.
// ---------------------------------------------------------------------------

describe('tagSizeBounds', () => {
  it('AC-S7-7: is the usable A4 page area after the 5mm printable margin, on both axes - no args', () => {
    expect(tagSizeBounds()).toEqual({
      min_mm: 10,
      max_width_mm: 200,
      max_height_mm: 287,
    });
  });
});

describe('resolveTagSize', () => {
  const bounds = tagSizeBounds();

  it('accepts a size that fits, unchanged', () => {
    expect(resolveTagSize(95, 44.5, bounds)).toEqual({
      ok: true,
      width_mm: 95,
      height_mm: 44.5,
    });
  });

  it('clamps a value below the minimum up to it', () => {
    expect(resolveTagSize(5, 5, bounds)).toEqual({ ok: true, width_mm: 10, height_mm: 10 });
  });

  it('refuses a width that does not fit the sheet, with a reason (400mm refused)', () => {
    const result = resolveTagSize(400, 44.5, bounds);
    expect(result.ok).toBe(false);
    expect((result as { ok: false; reason: string }).reason.length).toBeGreaterThan(0);
  });

  it('refuses a height that does not fit the sheet, with a reason', () => {
    const result = resolveTagSize(95, 400, bounds);
    expect(result.ok).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// templateFromTag - "Save as template" (S4, AC-S4-6/7/9)
// ---------------------------------------------------------------------------

describe('templateFromTag', () => {
  function tagWithLayers(layers: TagLayer[]): PlacedTag {
    return {
      id: 'tag-1',
      template_id: 't-sink',
      request_tag_id: 'l1',
      x_mm: 0,
      y_mm: 0,
      width_mm: 72,
      height_mm: 48,
      layers,
    };
  }

  it('strips text_override off a bound layer - a slot binding is what makes a template apply to every product (AC-S4-9)', () => {
    const bound: TagLayer = { ...textLayer('code', 1), text_override: 'SRT-9999' };
    const tag = tagWithLayers([bound]);

    const result = templateFromTag(tag, { name: 'My Template', family: 'ala_carte', newId });

    expect(result.doc.layers[0].slot_binding).toBe('code');
    expect(result.doc.layers[0].text_override).toBeNull();
  });

  it('keeps unbound text exactly as typed - it has no binding to fall back to', () => {
    const unbound: TagLayer = {
      ...textLayer('heading', 1),
      slot_binding: null,
      text_override: 'Sale Now On',
    };
    const tag = tagWithLayers([unbound]);

    const result = templateFromTag(tag, { name: 'My Template', family: 'ala_carte', newId });

    expect(result.doc.layers[0].slot_binding).toBeNull();
    expect(result.doc.layers[0].text_override).toBe('Sale Now On');
  });

  it('gives every layer a fresh id, sharing none with the tag it was cloned from', () => {
    const tag = tagWithLayers([textLayer('code', 1), groupLayer('group', ['code'])]);

    const result = templateFromTag(tag, { name: 'My Template', family: 'ala_carte', newId });

    const resultIds = result.doc.layers.map((l) => l.id);
    expect(resultIds).toHaveLength(2);
    expect(resultIds).not.toEqual(expect.arrayContaining(['code', 'group']));
    expect(new Set(resultIds).size).toBe(2);
  });

  it("remaps a group's children ids to the same fresh ids their layers got", () => {
    const tag = tagWithLayers([textLayer('code', 1), groupLayer('group', ['code'])]);

    const result = templateFromTag(tag, { name: 'My Template', family: 'ala_carte', newId });

    const remappedCodeId = result.doc.layers.find((l) => l.slot_binding === 'code')?.id;
    const group = result.doc.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ children: [remappedCodeId] });
  });

  it("print_size is the tag's own width/height, not the template it was cloned from", () => {
    const tag = tagWithLayers([textLayer('code', 1)]);

    const result = templateFromTag(tag, { name: 'My Template', family: 'ala_carte', newId });

    expect(result.print_size).toEqual({ width_mm: 72, height_mm: 48 });
    expect(result.doc).toMatchObject({ width_mm: 72, height_mm: 48 });
  });

  it('name and family pass through as given', () => {
    const tag = tagWithLayers([textLayer('code', 1)]);

    const result = templateFromTag(tag, { name: 'Sink Combo v2', family: 'sink_combo', newId });

    expect(result.name).toBe('Sink Combo v2');
    expect(result.family).toBe('sink_combo');
  });
});

// ---------------------------------------------------------------------------
// applyDesignToAllTags - "Apply this design to all lines" (S5, D3, AC-S5-2/5/6)
// ---------------------------------------------------------------------------

describe('applyDesignToAllTags', () => {
  function sourceTag(overrides: Partial<PlacedTag> = {}): PlacedTag {
    return {
      id: 'tag-src',
      template_id: 't-sink',
      request_tag_id: 'l1',
      x_mm: 0,
      y_mm: 0,
      width_mm: 95,
      height_mm: 44.5,
      layers: [
        { ...textLayer('code', 1), text_override: 'Hand typed' },
        groupLayer('group', ['code']),
      ],
      ...overrides,
    };
  }

  it('clones the source tag to every OTHER line, rebound to each line\'s own product', () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), productTag('l2'), productTag('l3')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    expect(next.l2).toBeDefined();
    expect(next.l3).toBeDefined();
    const group2 = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group2?.props).toMatchObject({ binding: { product_id: 'p-l2' } });
    const group3 = next.l3.layers.find((l) => l.props.kind === 'group');
    expect(group3?.props).toMatchObject({ binding: { product_id: 'p-l3' } });
  });

  it('copies template_id and size from the source onto every other line', () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    expect(next.l2).toMatchObject({
      template_id: 't-sink',
      width_mm: 95,
      height_mm: 44.5,
    });
  });

  it('copies a hand-typed text_override VERBATIM (D3) - no stripping, unlike templateFromTag', () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    const codeLayer = next.l2.layers.find((l) => l.slot_binding === 'code');
    expect(codeLayer?.text_override).toBe('Hand typed');
  });

  it('gives every clone fresh layer ids, sharing none with the source or with each other', () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), productTag('l2'), productTag('l3')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    const l2Ids = next.l2.layers.map((l) => l.id);
    const l3Ids = next.l3.layers.map((l) => l.id);
    expect(l2Ids).not.toEqual(expect.arrayContaining(['code', 'group']));
    expect(l3Ids).not.toEqual(expect.arrayContaining(['code', 'group']));
    expect(new Set([...l2Ids, ...l3Ids]).size).toBe(l2Ids.length + l3Ids.length);
  });

  it("remaps a group's children to the same fresh ids their layers got", () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    const remappedCodeId = next.l2.layers.find((l) => l.slot_binding === 'code')?.id;
    const group = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ children: [remappedCodeId] });
  });

  it("keeps a target line's existing position rather than resetting it (r10 S7: PlacedTag no longer carries `pinned` at all - arrange always re-flows)", () => {
    const tags = {
      l1: sourceTag(),
      l2: { ...placed('old-l2', 'l2'), x_mm: 12, y_mm: 34 },
    };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    expect(next.l2).toMatchObject({ x_mm: 12, y_mm: 34 });
    expect(next.l2).not.toHaveProperty('pinned');
  });

  it('gives a target line a fresh tag id even when it already had one, so Undo is not silently defeated (B1)', () => {
    const tags = {
      l1: sourceTag(),
      l2: { ...placed('old-l2', 'l2'), x_mm: 12, y_mm: 34, pinned: true },
    };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    expect(next.l2.id).not.toBe('old-l2');
  });

  it('a line with no tag yet gets one too, so it never re-clones from the default template later (AC-S5-5)', () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    expect(next.l2).toBeDefined();
    expect(next.l2.layers.length).toBeGreaterThan(0);
  });

  it('never touches the source line\'s own tag', () => {
    const source = sourceTag();
    const tags = { l1: source };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    expect(next.l1).toBe(source);
  });

  it('answers the map unchanged when the source line has no tag', () => {
    const tags = {};
    const requestTags = [productTag('l1'), productTag('l2')];

    expect(applyDesignToAllTags(tags, requestTags, 'l1', newId)).toBe(tags);
  });

  it('binds a set line to its own product set, not the source line\'s binding', () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), setTag('l2')];

    const next = applyDesignToAllTags(tags, requestTags, 'l1', newId);

    const group = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_set_id: 's-l2' } });
  });
});

// ---------------------------------------------------------------------------
// applyDesignToSiblings - "Update <template>" with the sibling checkbox on
// (S6, PLAN D6, AC-S6-4/5)
// ---------------------------------------------------------------------------

describe('applyDesignToSiblings', () => {
  function sourceTag(overrides: Partial<PlacedTag> = {}): PlacedTag {
    return {
      id: 'tag-src',
      template_id: 't-sink',
      request_tag_id: 'l1',
      x_mm: 0,
      y_mm: 0,
      width_mm: 95,
      height_mm: 44.5,
      layers: [
        { ...textLayer('code', 1), text_override: 'Hand typed' },
        groupLayer('group', ['code']),
      ],
      ...overrides,
    };
  }

  it('updates every OTHER line whose CURRENT tag matches the template being republished', () => {
    const tags = {
      l1: sourceTag(),
      l2: placed('old-l2', 'l2', 't-sink'),
      l3: placed('old-l3', 'l3', 't-sink'),
    };
    const requestTags = [productTag('l1'), productTag('l2'), productTag('l3')];

    const next = applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId);

    expect(next.l2.template_id).toBe('t-sink');
    expect(next.l2.width_mm).toBe(95);
    expect(next.l2.height_mm).toBe(44.5);
    const group2 = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group2?.props).toMatchObject({ binding: { product_id: 'p-l2' } });
    expect(next.l3.template_id).toBe('t-sink');
  });

  it('leaves a line on a DIFFERENT template untouched', () => {
    const other = placed('old-l2', 'l2', 't-wc');
    const tags = { l1: sourceTag(), l2: other };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId);

    expect(next.l2).toBe(other);
  });

  it('leaves a line with NO tag at all untouched - Update never gives a line its first tag', () => {
    const tags = { l1: sourceTag() };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId);

    expect(next.l2).toBeUndefined();
  });

  it("never touches the source line's own tag", () => {
    const source = sourceTag();
    const tags = { l1: source, l2: placed('old-l2', 'l2', 't-sink') };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId);

    expect(next.l1).toBe(source);
  });

  it("keeps a sibling tag at its own position - Update carries the design, not the layout (r10 S7: no `pinned` field any more)", () => {
    const tags = {
      l1: sourceTag(),
      l2: { ...placed('old-l2', 'l2', 't-sink'), x_mm: 12, y_mm: 34 },
    };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId);

    expect(next.l2).toMatchObject({ x_mm: 12, y_mm: 34 });
    expect(next.l2).not.toHaveProperty('pinned');
  });

  it('gives every updated sibling a fresh tag id, and fresh layer ids shared with nobody', () => {
    const tags = {
      l1: sourceTag(),
      l2: placed('old-l2', 'l2', 't-sink'),
    };
    const requestTags = [productTag('l1'), productTag('l2')];

    const next = applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId);

    expect(next.l2.id).not.toBe('old-l2');
    const l2Ids = next.l2.layers.map((l) => l.id);
    expect(l2Ids).not.toEqual(expect.arrayContaining(['code', 'group']));
  });

  it('binds a set-line sibling to its own set, not the source line\'s product', () => {
    const tags = {
      l1: sourceTag(),
      l2: placed('old-l2', 'l2', 't-sink'),
    };
    const requestTags = [productTag('l1'), setTag('l2')];

    const next = applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId);

    const group = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_set_id: 's-l2' } });
  });

  it('answers the map unchanged when the source line has no tag', () => {
    const tags = { l2: placed('old-l2', 'l2', 't-sink') };
    const requestTags = [productTag('l1'), productTag('l2')];

    expect(applyDesignToSiblings(tags, requestTags, 'l1', 't-sink', newId)).toBe(tags);
  });
});
