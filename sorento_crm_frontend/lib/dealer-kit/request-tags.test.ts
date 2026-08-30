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
  PlacedTag,
  TagLayer,
  TagTemplate,
  TagTemplateFamily,
} from './tag-template-types';
import { IMPOSITION_PRESETS, defaultTextProps } from './tag-template-types';
import {
  autoArrange,
  copiesOf,
  defaultTemplateFor,
  impositionSlots,
  pinnedFromDoc,
  placementKey,
  tagForLine,
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

const A4_3UP: ImpositionConfig = { preset: 'a4_3up', ...IMPOSITION_PRESETS.a4_3up };
const A4_2X2: ImpositionConfig = { preset: 'a4_2x2', ...IMPOSITION_PRESETS.a4_2x2 };

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
// impositionSlots
// ---------------------------------------------------------------------------

describe('impositionSlots', () => {
  it('a4_3up is one column of three, centred', () => {
    const slots = impositionSlots(A4_3UP, 60, 40);
    expect(slots).toHaveLength(3);
    expect(slots.every((s) => s.x_mm === slots[0].x_mm)).toBe(true);
    expect(slots[1].y_mm - slots[0].y_mm).toBe(40 + A4_3UP.gap_mm);
    // Centred horizontally inside the bleed box.
    expect(slots[0].x_mm).toBeCloseTo(3 + (204 - 60) / 2, 6);
  });

  it('a4_2x2 is two columns of two', () => {
    const slots = impositionSlots(A4_2X2, 60, 40);
    expect(slots).toHaveLength(4);
    expect(slots[1].x_mm - slots[0].x_mm).toBe(60 + A4_2X2.gap_mm);
    expect(slots[2].y_mm - slots[0].y_mm).toBe(40 + A4_2X2.gap_mm);
  });

  it('custom is a single centred slot', () => {
    const custom: ImpositionConfig = { preset: 'custom', ...IMPOSITION_PRESETS.custom };
    expect(impositionSlots(custom, 60, 40)).toHaveLength(1);
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
    const sheets = autoArrange(
      [
        { tag: placed('a', 'l1'), quantity: 2 },
        { tag: placed('b', 'l2'), quantity: 3 },
      ],
      A4_3UP,
    );

    expect(sheets).toHaveLength(2);
    expect(sheets[0].id).toBe('sheet-1');
    expect(sheets[0].tags.map((t) => t.id)).toEqual(['a-c0', 'a-c1', 'b-c0']);
    expect(sheets[1].tags.map((t) => t.id)).toEqual(['b-c1', 'b-c2']);
  });

  it('puts each copy on its slot, so nothing overlaps', () => {
    const slots = impositionSlots(A4_3UP, 60, 40);
    const sheets = autoArrange([{ tag: placed('a', 'l1'), quantity: 3 }], A4_3UP);
    expect(sheets[0].tags.map((t) => ({ x: t.x_mm, y: t.y_mm }))).toEqual(
      slots.map((s) => ({ x: s.x_mm, y: s.y_mm })),
    );
  });

  it('is deterministic: the same input answers the same document', () => {
    const items = [
      { tag: placed('a', 'l1'), quantity: 2 },
      { tag: placed('b', 'l2'), quantity: 2 },
    ];
    expect(autoArrange(items, A4_3UP)).toEqual(autoArrange(items, A4_3UP));
  });

  it('sizes the slot grid off the largest tag, so a big tag still fits its slot', () => {
    const big = { ...placed('b', 'l2'), width_mm: 100, height_mm: 70 };
    const sheets = autoArrange(
      [
        { tag: placed('a', 'l1'), quantity: 1 },
        { tag: big, quantity: 1 },
      ],
      A4_3UP,
    );
    const slots = impositionSlots(A4_3UP, 100, 70);
    expect(sheets[0].tags[0].x_mm).toBe(slots[0].x_mm);
    expect(sheets[0].tags[1].y_mm).toBe(slots[1].y_mm);
  });

  it('every copy carries the tag layers, its template and its line', () => {
    const sheets = autoArrange([{ tag: placed('a', 'l1', 't-wc'), quantity: 2 }], A4_3UP);
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
      A4_3UP,
      pinned,
    );

    const slots = impositionSlots(A4_3UP, 60, 40);
    expect(sheets).toHaveLength(2);
    expect(sheets[0].tags.map((t) => t.id)).toEqual(['a-c0', 'b-c0']);
    // The pinned copy takes no slot, so the one behind it moves up into slot 2.
    expect(sheets[0].tags[1]).toMatchObject({ x_mm: slots[1].x_mm, y_mm: slots[1].y_mm });
    expect(sheets[1].tags).toHaveLength(1);
    expect(sheets[1].tags[0]).toMatchObject({ id: 'a-c1', x_mm: 12.5, y_mm: 33 });
  });

  it('answers one empty sheet when the request has nothing to place', () => {
    const sheets = autoArrange([], A4_3UP);
    expect(sheets).toEqual([{ id: 'sheet-1', tags: [] }]);
  });
});

// ---------------------------------------------------------------------------
// pinnedFromDoc
// ---------------------------------------------------------------------------

describe('pinnedFromDoc', () => {
  it('reads a saved arrangement back as pins, keyed by line and copy', () => {
    const pinned = pinnedFromDoc({
      kind: 'tag_sheet',
      imposition: A4_3UP,
      sheets: [
        { id: 'sheet-1', tags: [{ ...placed('a-c0', 'l1'), x_mm: 5, y_mm: 6 }] },
        { id: 'sheet-2', tags: [{ ...placed('a-c1', 'l1'), x_mm: 7, y_mm: 8 }] },
      ],
    });

    expect(pinned).toEqual({
      [placementKey('l1', 0)]: { sheet: 0, x_mm: 5, y_mm: 6 },
      [placementKey('l1', 1)]: { sheet: 1, x_mm: 7, y_mm: 8 },
    });
  });

  it('a document written before copy ids existed still pins its first copy', () => {
    const pinned = pinnedFromDoc({
      kind: 'tag_sheet',
      imposition: A4_3UP,
      sheets: [{ id: 's-old', tags: [{ ...placed('t-1756-3', 'l9'), x_mm: 1, y_mm: 2 }] }],
    });
    expect(pinned).toEqual({ [placementKey('l9', 0)]: { sheet: 0, x_mm: 1, y_mm: 2 } });
  });

  it('answers nothing for a document that does not exist yet', () => {
    expect(pinnedFromDoc(null)).toEqual({});
  });
});
