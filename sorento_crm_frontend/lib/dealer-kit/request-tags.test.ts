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
  applyDesignToAllLines,
  autoArrange,
  copiesOf,
  defaultTemplateFor,
  impositionFit,
  impositionSlots,
  normaliseImpositionPreset,
  pinKeyForPlacement,
  pinnedFromDoc,
  placementKey,
  resizeAllTags,
  resizeTag,
  resolveTagSize,
  starterTemplateFor,
  tagForLine,
  tagSizeBounds,
  tagSizePresets,
  templateFromTag,
} from './request-tags';

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

// A4, 3mm bleed, 2mm gap - the everyday page geometry most of this file's
// fixtures arrange onto. Named PAGE_A4 rather than after a preset because S6
// removed the presets: every `ImpositionConfig` now lays out the same way,
// auto-fit off the tag's own size (see `impositionSlots`/`impositionFit`
// below).
const PAGE_A4: ImpositionConfig = { preset: 'auto', ...IMPOSITION_PRESETS.auto };
// Same page, a much wider gap - genuinely different geometry, for the test
// that reopens a saved sheet under a changed page.
const PAGE_A4_WIDE_GAP: ImpositionConfig = { ...PAGE_A4, gap_mm: 10 };

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
    line_id: 'l1',
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
// tagForLine
// ---------------------------------------------------------------------------

describe('tagForLine', () => {
  it('clones the template layers and binds the group to the line item', () => {
    const source = TEMPLATES[0];
    const tag = tagForLine(productLine('l1'), source, 'tag-1');

    expect(tag).toMatchObject({
      id: 'tag-1',
      template_id: 't-sink',
      request_line_id: 'l1',
      x_mm: 0,
      y_mm: 0,
      width_mm: 60,
      height_mm: 40,
    });
    const group = tag.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_id: 'p-l1' } });
  });

  it('binds a set line to the product set', () => {
    const tag = tagForLine(setLine('l2'), TEMPLATES[2], 'tag-2');
    const group = tag.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_set_id: 's-l2' } });
  });

  it('never writes back into the template it was cloned from', () => {
    const source = template('t-copy', 'wc');
    const before = JSON.stringify(source.doc.layers);
    const tag = tagForLine(productLine('l3'), source, 'tag-3');

    tag.layers[0].x_mm = 99;
    tag.layers[0].text_override = 'typed over';

    expect(JSON.stringify(source.doc.layers)).toBe(before);
  });

  it('takes its size from the template print size, not from the doc', () => {
    const source = template('t-big', 'mirror', { width_mm: 100, height_mm: 70 });
    source.doc.width_mm = 10;
    source.doc.height_mm = 10;
    const tag = tagForLine(productLine('l4'), source, 'tag-4');
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
// impositionSlots
// ---------------------------------------------------------------------------

describe('impositionSlots', () => {
  it('fills a grid sized by impositionFit, centred in the bleed box, row-major', () => {
    const slots = impositionSlots(PAGE_A4, 60, 40);
    const { cols, rows, perSheet } = impositionFit(210, 297, 3, 2, 60, 40);
    expect(slots).toHaveLength(perSheet);
    expect(rows).toBeGreaterThan(1);
    // Row-major: the first `cols` slots share one y; column and row spacing
    // are the tag size plus the gap.
    expect(slots.slice(0, cols).every((s) => s.y_mm === slots[0].y_mm)).toBe(true);
    expect(slots[1].x_mm - slots[0].x_mm).toBe(60 + PAGE_A4.gap_mm);
    expect(slots[cols].y_mm - slots[0].y_mm).toBe(40 + PAGE_A4.gap_mm);
    // Centred horizontally inside the bleed box.
    const totalW = cols * 60 + (cols - 1) * PAGE_A4.gap_mm;
    expect(slots[0].x_mm).toBeCloseTo(3 + (204 - totalW) / 2, 6);
  });

  it('falls back to a single centred slot when the tag does not fit the page at all, so a copy still has somewhere to go', () => {
    // impositionFit is what tells the designer "0 per sheet" (AC-S6-3); this
    // function still has to seat a copy SOMEWHERE, or autoArrange places
    // nothing and a saved line's design vanishes on the next reload.
    const tiny: ImpositionConfig = { ...PAGE_A4, page_width_mm: 50 };
    expect(impositionFit(50, 297, 3, 2, 95, 44.5).perSheet).toBe(0);
    const slots = impositionSlots(tiny, 95, 44.5);
    expect(slots).toHaveLength(1);
    expect(slots[0]).toEqual({ x_mm: 3 + (44 - 95) / 2, y_mm: 3 + (291 - 44.5) / 2 });
  });

  it('a NaN fit still falls back to a single centred slot, never an empty grid (S2)', () => {
    // A NaN cols/rows used to slip past the `perSheet === 0` check (NaN !==
    // 0) while the row/col loops still never ran (any comparison against NaN
    // is false), leaving `slots` empty and `autoArrange` crashing on
    // `slots[0]`.
    const nanPage: ImpositionConfig = { ...PAGE_A4, page_width_mm: NaN };
    const slots = impositionSlots(nanPage, 95, 44.5);
    expect(slots).toHaveLength(1);
  });

  it('the preset value no longer changes the layout - an old a4_3up/a4_2x2 doc lays out identically (AC-S6-4)', () => {
    const auto = impositionSlots({ ...PAGE_A4, preset: 'auto' }, 60, 40);
    expect(impositionSlots({ ...PAGE_A4, preset: 'a4_3up' }, 60, 40)).toEqual(auto);
    expect(impositionSlots({ ...PAGE_A4, preset: 'a4_2x2' }, 60, 40)).toEqual(auto);
    expect(impositionSlots({ ...PAGE_A4, preset: 'custom' }, 60, 40)).toEqual(auto);
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
// copiesOf and autoArrange
// ---------------------------------------------------------------------------

function placed(id: string, lineId: string, templateId = 't-sink'): PlacedTag {
  return {
    id,
    template_id: templateId,
    request_line_id: lineId,
    x_mm: 0,
    y_mm: 0,
    width_mm: 60,
    height_mm: 40,
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
});

describe('autoArrange', () => {
  it('lays quantity copies out in line order across as many sheets as it needs', () => {
    // A page that fits exactly 3 of the fixture's 60x40 tag (1 col x 3 rows),
    // so 5 copies genuinely need a second sheet.
    const narrowPage: ImpositionConfig = {
      preset: 'auto',
      page_width_mm: 70,
      page_height_mm: 136,
      bleed_mm: 3,
      gap_mm: 2,
    };
    expect(impositionFit(70, 136, 3, 2, 60, 40).perSheet).toBe(3);

    const sheets = autoArrange(
      [
        { tag: placed('a', 'l1'), quantity: 2 },
        { tag: placed('b', 'l2'), quantity: 3 },
      ],
      narrowPage,
    );

    expect(sheets).toHaveLength(2);
    expect(sheets[0].id).toBe('sheet-1');
    expect(sheets[0].tags.map((t) => t.id)).toEqual(['a-c0', 'a-c1', 'b-c0']);
    expect(sheets[1].tags.map((t) => t.id)).toEqual(['b-c1', 'b-c2']);
  });

  it('puts each copy on its slot, so nothing overlaps', () => {
    const slots = impositionSlots(PAGE_A4, 60, 40);
    const sheets = autoArrange([{ tag: placed('a', 'l1'), quantity: 3 }], PAGE_A4);
    expect(sheets[0].tags.map((t) => ({ x: t.x_mm, y: t.y_mm }))).toEqual(
      slots.slice(0, 3).map((s) => ({ x: s.x_mm, y: s.y_mm })),
    );
  });

  it('is deterministic: the same input answers the same document', () => {
    const items = [
      { tag: placed('a', 'l1'), quantity: 2 },
      { tag: placed('b', 'l2'), quantity: 2 },
    ];
    expect(autoArrange(items, PAGE_A4)).toEqual(autoArrange(items, PAGE_A4));
  });

  it('sizes the slot grid off the largest tag, so a big tag still fits its slot', () => {
    const big = { ...placed('b', 'l2'), width_mm: 100, height_mm: 70 };
    const sheets = autoArrange(
      [
        { tag: placed('a', 'l1'), quantity: 1 },
        { tag: big, quantity: 1 },
      ],
      PAGE_A4,
    );
    const slots = impositionSlots(PAGE_A4, 100, 70);
    expect(sheets[0].tags[0].x_mm).toBe(slots[0].x_mm);
    expect(sheets[0].tags[1].y_mm).toBe(slots[1].y_mm);
  });

  it('every copy carries the tag layers, its template and its line', () => {
    const sheets = autoArrange([{ tag: placed('a', 'l1', 't-wc'), quantity: 2 }], PAGE_A4);
    for (const tag of sheets[0].tags) {
      expect(tag.template_id).toBe('t-wc');
      expect(tag.request_line_id).toBe('l1');
      expect(tag.layers).toHaveLength(1);
    }
  });

  it('keeps a manual drag and flows everything else around it', () => {
    const pinned = { [placementKey('l1', 1)]: { sheet: 1, x_mm: 12.5, y_mm: 33 } };
    const sheets = autoArrange(
      [
        { tag: placed('a', 'l1'), quantity: 2 },
        { tag: placed('b', 'l2'), quantity: 1 },
      ],
      PAGE_A4,
      pinned,
    );

    const slots = impositionSlots(PAGE_A4, 60, 40);
    expect(sheets).toHaveLength(2);
    expect(sheets[0].tags.map((t) => t.id)).toEqual(['a-c0', 'b-c0']);
    // The pinned copy takes no slot, so the one behind it moves up into slot 2.
    expect(sheets[0].tags[1]).toMatchObject({ x_mm: slots[1].x_mm, y_mm: slots[1].y_mm });
    expect(sheets[1].tags).toHaveLength(1);
    expect(sheets[1].tags[0]).toMatchObject({ id: 'a-c1', x_mm: 12.5, y_mm: 33 });
  });

  it('answers one empty sheet when the request has nothing to place', () => {
    const sheets = autoArrange([], PAGE_A4);
    expect(sheets).toEqual([{ id: 'sheet-1', tags: [] }]);
  });

  it('still places every line when the page is too small for the tag, so no design is lost on reload', () => {
    // A page smaller than the tag - impositionFit reads 0 per sheet, but
    // every copy still has to land SOMEWHERE: `tagsFromDoc` reads a line's
    // design off `sheets`, so an empty sheet here would make every line look
    // never-designed the next time this request is opened.
    const tiny: ImpositionConfig = { ...PAGE_A4, page_width_mm: 50 };
    const sheets = autoArrange(
      [
        { tag: placed('a', 'l1'), quantity: 1 },
        { tag: placed('b', 'l2'), quantity: 1 },
      ],
      tiny,
    );
    expect(sheets.flatMap((s) => s.tags).map((t) => t.request_line_id)).toEqual(['l1', 'l2']);
  });
});

// ---------------------------------------------------------------------------
// pinKeyForPlacement and pinnedFromDoc
// ---------------------------------------------------------------------------

describe('pinKeyForPlacement', () => {
  it('reads the copy index off the placement id', () => {
    expect(pinKeyForPlacement({ id: 'tag-9-c2', request_line_id: 'l1' })).toBe(
      placementKey('l1', 2),
    );
  });

  it('treats a placement written before copy ids as the first copy', () => {
    expect(pinKeyForPlacement({ id: 't-1756-3', request_line_id: 'l1' })).toBe(
      placementKey('l1', 0),
    );
  });
});

describe('pinnedFromDoc', () => {
  /**
   * A pin is a DRAG, not a position.
   *
   * Every placed tag in a saved document carries a position, because
   * arrangement is what a document IS. Reading each of those back as a pin
   * meant that after one save-and-reopen the whole sheet was pinned: switching
   * the imposition preset re-imposed nothing, and bumping a line's quantity
   * dropped the new copy on top of copy 0 rather than into the next free slot.
   * Only a copy somebody dragged carries `pinned: true`.
   */
  it('reads only the copies somebody actually dragged', () => {
    const pinned = pinnedFromDoc({
      kind: 'tag_sheet',
      imposition: PAGE_A4,
      sheets: [
        { id: 'sheet-1', tags: [{ ...placed('a-c0', 'l1'), x_mm: 5, y_mm: 6 }] },
        {
          id: 'sheet-2',
          tags: [{ ...placed('a-c1', 'l1'), x_mm: 7, y_mm: 8, pinned: true }],
        },
      ],
    });

    expect(pinned).toEqual({
      [placementKey('l1', 1)]: { sheet: 1, x_mm: 7, y_mm: 8 },
    });
  });

  it('a document saved before the flag existed opens unpinned', () => {
    // Auto-arrange re-imposes it on open. That is the deliberate trade: those
    // documents cannot say which of their positions was a drag, and re-imposing
    // is the answer that leaves the sheet correct rather than frozen.
    const pinned = pinnedFromDoc({
      kind: 'tag_sheet',
      imposition: PAGE_A4,
      sheets: [{ id: 's-old', tags: [{ ...placed('t-1756-3', 'l9'), x_mm: 1, y_mm: 2 }] }],
    });
    expect(pinned).toEqual({});
  });

  it('answers nothing for a document that does not exist yet', () => {
    expect(pinnedFromDoc(null)).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// Save, reopen, and keep arranging
// ---------------------------------------------------------------------------

describe('a saved sheet reopens still arrangeable', () => {
  const items = [
    { tag: placed('a', 'l1'), quantity: 2 },
    { tag: placed('b', 'l2'), quantity: 1 },
  ];

  it('an auto-placed copy is not marked as dragged', () => {
    const sheets = autoArrange(items, PAGE_A4);
    for (const sheet of sheets) {
      for (const tag of sheet.tags) expect(tag.pinned).not.toBe(true);
    }
  });

  it('a dragged copy is marked, and only that one comes back as a pin', () => {
    const pinned = { [placementKey('l1', 1)]: { sheet: 1, x_mm: 12.5, y_mm: 33 } };
    const saved = { kind: 'tag_sheet' as const, imposition: PAGE_A4, sheets: autoArrange(items, PAGE_A4, pinned) };

    const dragged = saved.sheets[1].tags[0];
    expect(dragged.id).toBe('a-c1');
    expect(dragged.pinned).toBe(true);
    expect(pinnedFromDoc(saved)).toEqual(pinned);
  });

  it('reopening under a different page geometry re-imposes everything that was not dragged', () => {
    const saved = { kind: 'tag_sheet' as const, imposition: PAGE_A4, sheets: autoArrange(items, PAGE_A4) };

    const reopened = autoArrange(items, PAGE_A4_WIDE_GAP, pinnedFromDoc(saved));

    const slots = impositionSlots(PAGE_A4_WIDE_GAP, 60, 40);
    expect(reopened[0].tags.map((t) => ({ x: t.x_mm, y: t.y_mm }))).toEqual(
      slots.slice(0, 3).map((s) => ({ x: s.x_mm, y: s.y_mm })),
    );
  });

  it('a quantity bump lands in the next free slot, not on top of copy 0', () => {
    const saved = { kind: 'tag_sheet' as const, imposition: PAGE_A4, sheets: autoArrange(items, PAGE_A4) };

    const bumped = autoArrange(
      [
        { tag: placed('a', 'l1'), quantity: 3 },
        { tag: placed('b', 'l2'), quantity: 1 },
      ],
      PAGE_A4,
      pinnedFromDoc(saved),
    );

    const positions = bumped
      .flatMap((sheet, index) => sheet.tags.map((t) => `${index}:${t.x_mm},${t.y_mm}`));
    expect(new Set(positions).size).toBe(positions.length);
  });
});

// ---------------------------------------------------------------------------
// Tag size control (D24, S9, AC-S9-3)
// ---------------------------------------------------------------------------

describe('resizeTag', () => {
  it('sets the tag footprint used by the sheet layout, leaving everything else alone', () => {
    const tag = placed('a', 'l1');
    const resized = resizeTag(tag, 95, 44.5);

    expect(resized).toMatchObject({ width_mm: 95, height_mm: 44.5 });
    expect(resized.id).toBe(tag.id);
    expect(resized.layers).toBe(tag.layers);
  });
});

describe('resizeAllTags', () => {
  it('applies one size to every line, in "Apply to all lines" (AC-S9-3)', () => {
    const tags = {
      l1: placed('a', 'l1'),
      l2: placed('b', 'l2'),
    };

    const resized = resizeAllTags(tags, 95, 44.5);

    expect(resized.l1).toMatchObject({ width_mm: 95, height_mm: 44.5 });
    expect(resized.l2).toMatchObject({ width_mm: 95, height_mm: 44.5 });
  });

  it('leaves an empty map empty', () => {
    expect(resizeAllTags({}, 95, 44.5)).toEqual({});
  });
});

describe('tagSizePresets', () => {
  it('offers every published template print size, deduped, plus the starter size', () => {
    const presets = tagSizePresets(TEMPLATES);

    // TEMPLATES fixture: t-sink/t-wc/t-set all 60x40, t-plain also 60x40 -
    // one preset for that size, not four.
    expect(presets.filter((p) => p.width_mm === 60 && p.height_mm === 40)).toHaveLength(1);
    expect(presets).toContainEqual(
      expect.objectContaining({ width_mm: PRODUCT_BLOCK_SIZE.width_mm, height_mm: PRODUCT_BLOCK_SIZE.height_mm }),
    );
  });

  it('still offers the starter size when there are no templates at all', () => {
    const presets = tagSizePresets([]);
    expect(presets).toEqual([
      expect.objectContaining({ width_mm: PRODUCT_BLOCK_SIZE.width_mm, height_mm: PRODUCT_BLOCK_SIZE.height_mm }),
    ]);
  });
});

describe('autoArrange with resized tags (AC-S9-3)', () => {
  it('re-lays out unpinned copies at the new size, and leaves a pinned copy exactly where it was dragged', () => {
    const items = [
      { tag: placed('a', 'l1'), quantity: 1 },
      { tag: resizeTag(placed('b', 'l2'), 95, 44.5), quantity: 1 },
    ];

    const dragged = { [placementKey('l2', 0)]: { sheet: 0, x_mm: 12, y_mm: 34 } };
    const sheets = autoArrange(items, PAGE_A4, dragged);

    const line2Tag = sheets[0].tags.find((t) => t.request_line_id === 'l2');
    expect(line2Tag).toMatchObject({ x_mm: 12, y_mm: 34, width_mm: 95, height_mm: 44.5 });

    // The unpinned line still flows through the slot grid, unaffected by the
    // other line's resize.
    const line1Tag = sheets[0].tags.find((t) => t.request_line_id === 'l1');
    expect(line1Tag?.pinned).not.toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Tag size bounds + refusal (S9 review S3): a size has to fit the CURRENT
// imposition sheet, refused with a reason rather than silently redrawn.
// ---------------------------------------------------------------------------

describe('tagSizeBounds', () => {
  it('is the usable page area after bleed, on both axes', () => {
    // PAGE_A4: 210x297mm page, 3mm bleed each side.
    expect(tagSizeBounds(PAGE_A4)).toEqual({
      min_mm: 10,
      max_width_mm: 204,
      max_height_mm: 291,
    });
  });
});

describe('resolveTagSize', () => {
  const bounds = tagSizeBounds(PAGE_A4);

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
      request_line_id: 'l1',
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
// applyDesignToAllLines - "Apply this design to all lines" (S5, D3, AC-S5-2/5/6)
// ---------------------------------------------------------------------------

describe('applyDesignToAllLines', () => {
  function sourceTag(overrides: Partial<PlacedTag> = {}): PlacedTag {
    return {
      id: 'tag-src',
      template_id: 't-sink',
      request_line_id: 'l1',
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
    const lines = [productLine('l1'), productLine('l2'), productLine('l3')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    expect(next.l2).toBeDefined();
    expect(next.l3).toBeDefined();
    const group2 = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group2?.props).toMatchObject({ binding: { product_id: 'p-l2' } });
    const group3 = next.l3.layers.find((l) => l.props.kind === 'group');
    expect(group3?.props).toMatchObject({ binding: { product_id: 'p-l3' } });
  });

  it('copies template_id and size from the source onto every other line', () => {
    const tags = { l1: sourceTag() };
    const lines = [productLine('l1'), productLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    expect(next.l2).toMatchObject({
      template_id: 't-sink',
      width_mm: 95,
      height_mm: 44.5,
    });
  });

  it('copies a hand-typed text_override VERBATIM (D3) - no stripping, unlike templateFromTag', () => {
    const tags = { l1: sourceTag() };
    const lines = [productLine('l1'), productLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    const codeLayer = next.l2.layers.find((l) => l.slot_binding === 'code');
    expect(codeLayer?.text_override).toBe('Hand typed');
  });

  it('gives every clone fresh layer ids, sharing none with the source or with each other', () => {
    const tags = { l1: sourceTag() };
    const lines = [productLine('l1'), productLine('l2'), productLine('l3')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    const l2Ids = next.l2.layers.map((l) => l.id);
    const l3Ids = next.l3.layers.map((l) => l.id);
    expect(l2Ids).not.toEqual(expect.arrayContaining(['code', 'group']));
    expect(l3Ids).not.toEqual(expect.arrayContaining(['code', 'group']));
    expect(new Set([...l2Ids, ...l3Ids]).size).toBe(l2Ids.length + l3Ids.length);
  });

  it("remaps a group's children to the same fresh ids their layers got", () => {
    const tags = { l1: sourceTag() };
    const lines = [productLine('l1'), productLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    const remappedCodeId = next.l2.layers.find((l) => l.slot_binding === 'code')?.id;
    const group = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ children: [remappedCodeId] });
  });

  it('keeps a target line\'s existing pinned copy/position rather than resetting it', () => {
    const tags = {
      l1: sourceTag(),
      l2: { ...placed('old-l2', 'l2'), x_mm: 12, y_mm: 34, pinned: true },
    };
    const lines = [productLine('l1'), productLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    expect(next.l2).toMatchObject({ x_mm: 12, y_mm: 34, pinned: true });
  });

  it('gives a target line a fresh tag id even when it already had one, so Undo is not silently defeated (B1)', () => {
    const tags = {
      l1: sourceTag(),
      l2: { ...placed('old-l2', 'l2'), x_mm: 12, y_mm: 34, pinned: true },
    };
    const lines = [productLine('l1'), productLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    expect(next.l2.id).not.toBe('old-l2');
  });

  it('a line with no tag yet gets one too, so it never re-clones from the default template later (AC-S5-5)', () => {
    const tags = { l1: sourceTag() };
    const lines = [productLine('l1'), productLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    expect(next.l2).toBeDefined();
    expect(next.l2.layers.length).toBeGreaterThan(0);
  });

  it('never touches the source line\'s own tag', () => {
    const source = sourceTag();
    const tags = { l1: source };
    const lines = [productLine('l1'), productLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    expect(next.l1).toBe(source);
  });

  it('answers the map unchanged when the source line has no tag', () => {
    const tags = {};
    const lines = [productLine('l1'), productLine('l2')];

    expect(applyDesignToAllLines(tags, lines, 'l1', newId)).toBe(tags);
  });

  it('binds a set line to its own product set, not the source line\'s binding', () => {
    const tags = { l1: sourceTag() };
    const lines = [productLine('l1'), setLine('l2')];

    const next = applyDesignToAllLines(tags, lines, 'l1', newId);

    const group = next.l2.layers.find((l) => l.props.kind === 'group');
    expect(group?.props).toMatchObject({ binding: { product_set_id: 's-l2' } });
  });
});
