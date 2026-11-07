/**
 * PRICETAG-COMBO-RENDER K5 / AC-C3 to C6, AC-D2: several picks from one group on a draft line.
 *
 * Written test-FIRST. `DraftPart.product_ids`, `linePickProblems` and `trimPicksToTemplate`
 * do not exist yet.
 *
 * Decisions where the plan is open:
 * - `DraftPart.product_ids` is the ordered picks of a group the template needs k >= 2 from;
 *   the payload sends one resolved part per id (same role, in order, `candidates: []`).
 * - Loading folds two or more resolved parts that share a non-empty role into ONE DraftPart in
 *   the position of the first of them; a lone resolved part stays a plain `product_id` row.
 * - AC-C4 helper: `trimPicksToTemplate(line)` reads the line's chosen template (`tag_template_id`
 *   or the lone link) from `line.tag_templates[].needs` and the combo shape from `line.combos`;
 *   a group is cut to max(k, 1) picks; at 1 the row goes back to a single `product_id` and
 *   `product_ids` is dropped.
 * - `linePickProblems(lines, pricingByKey, priceMode = 'list')` -> string[] in line order;
 *   `priceMode` is the request's mode, used when a line has no own `price_type` (the plan's
 *   two-argument signature cannot tell an LP line from an SP line).
 * - Reason words, exact: "Line i: <group>: pick n more.", "<code> is discontinued. Pick another
 *   or escalate it to marketing.", "No combo list price for line i. Escalate it to marketing."
 * - Only a group the template needs k >= 2 from can be short; an open k <= 1 group is not a
 *   problem (it is today's "any of" row).
 */
import { describe, expect, it } from 'vitest';

import * as draft from './price-tag-draft-lines';
import { draftLinesPayload, emptyDraftLine, lineToDraft, type DraftLine } from './price-tag-draft-lines';

const api = draft as unknown as {
  linePickProblems: (
    lines: DraftLine[],
    pricingByKey: Record<string, { list_price?: number | null; sell_price?: number | null } | null | undefined>,
    priceMode?: 'list' | 'selling',
  ) => string[];
  trimPicksToTemplate: (line: DraftLine) => DraftLine;
};

const OPTIONS = ['SRTKT1862SS', 'SRTKT1863SS', 'SRTKT1871SS', 'SRTKT1880SS', 'SRTKT1892SS'];
const id = (code: string) => `id-${code}`;

const S1_COMBO = {
  combo_id: 'c1',
  name: 'Sink combo',
  parts: [
    ...OPTIONS.map((code) => ({
      product_id: id(code),
      code,
      name: code,
      choice_group: 'Kitchen tap',
      is_discontinued: false,
    })),
    {
      product_id: id('SRTKT71SS'),
      code: 'SRTKT71SS',
      name: 'Upgrade tap',
      choice_group: null,
      is_upgrade: true,
      topup_amount: 150,
      is_discontinued: false,
    },
  ],
};

const tpl = (tid: string, groups: number[], extra: Record<string, unknown> = {}) => ({
  id: tid,
  name: `Template ${tid}`,
  family: 'ala_carte',
  published: true,
  width_mm: 105,
  height_mm: 148,
  needs: { fixed: 0, groups, upgrades: 0 },
  ...extra,
});

const candidates = OPTIONS.map((code) => ({ product_id: id(code), code, name: code }));

function picksPart(ids: string[], extra: Record<string, unknown> = {}) {
  return {
    key: 'g1',
    product_id: null,
    code: '',
    name: '',
    role: 'Kitchen tap',
    candidates,
    product_ids: ids,
    ...extra,
  };
}

function line(overrides: Record<string, unknown> = {}): DraftLine {
  return {
    ...emptyDraftLine(),
    key: 'l1',
    product_id: 'host',
    name: 'Host',
    code: 'SRTKS7061',
    combo_id: 'c1',
    combos: [S1_COMBO],
    combos_loaded: true,
    tag_templates_for: 'host',
    tag_templates_combo: 'c1',
    tag_templates: [tpl('t3', [3]), tpl('t1', [1])],
    tag_template_id: 't3',
    parts: [picksPart([id(OPTIONS[1]), id(OPTIONS[0]), id(OPTIONS[2])])],
    ...overrides,
  } as unknown as DraftLine;
}

describe('payload', () => {
  it('expands product_ids into one resolved part per id, in pick order, same role', () => {
    const [out] = draftLinesPayload([line()], 'list');
    expect(out.parts).toEqual([
      { product_id: id(OPTIONS[1]), role: 'Kitchen tap', candidates: [] },
      { product_id: id(OPTIONS[0]), role: 'Kitchen tap', candidates: [] },
      { product_id: id(OPTIONS[2]), role: 'Kitchen tap', candidates: [] },
    ]);
  });

  it('keeps the other parts around the group in order', () => {
    const fixed = { key: 'f', product_id: 'fx', code: 'F', name: 'F', role: null, candidates: [] };
    const upgrade = { key: 'u', product_id: id('SRTKT71SS'), code: 'U', name: 'U', role: 'Upgrade', candidates: [] };
    const [out] = draftLinesPayload([line({ parts: [fixed, picksPart([id(OPTIONS[3]), id(OPTIONS[4])]), upgrade] })], 'list');
    expect(out.parts?.map((p) => p.product_id)).toEqual(['fx', id(OPTIONS[3]), id(OPTIONS[4]), id('SRTKT71SS')]);
  });

  it('a row with no picks stays an open row with its candidates', () => {
    const [out] = draftLinesPayload([line({ parts: [picksPart([])] })], 'list');
    expect(out.parts).toEqual([
      { product_id: null, role: 'Kitchen tap', candidates: OPTIONS.map(id) },
    ]);
  });

  it('a single product_id row is sent as today', () => {
    const single = { key: 's', product_id: id(OPTIONS[0]), code: OPTIONS[0], name: OPTIONS[0], role: 'Kitchen tap', candidates };
    const [out] = draftLinesPayload([line({ parts: [single] })], 'list');
    expect(out.parts).toEqual([{ product_id: id(OPTIONS[0]), role: 'Kitchen tap', candidates: [] }]);
  });
});

describe('reopening a saved line', () => {
  const saved = (parts: unknown[]) =>
    ({
      id: 'line-1',
      line_type: 'product',
      product_id: 'host',
      product_set_id: null,
      name: 'Host',
      code: 'SRTKS7061',
      quantity: 1,
      combo_id: 'c1',
      parts,
    }) as never;
  const resolved = (code: string, role: string | null, pid = 'part') => ({
    id: `${pid}-${code}`,
    product_id: id(code),
    code,
    name: code,
    role,
    candidates: [],
  });

  it('folds resolved parts sharing a role back into one row, in pick order', () => {
    const out = lineToDraft(
      saved([
        resolved('SRTMCB8083-BL', null),
        resolved(OPTIONS[1], 'Kitchen tap'),
        resolved(OPTIONS[0], 'Kitchen tap'),
        resolved(OPTIONS[2], 'Kitchen tap'),
      ]),
    );
    expect(out.parts).toHaveLength(2);
    expect(out.parts[0].role).toBeNull();
    const group = out.parts[1] as unknown as { role: string; product_ids: string[] };
    expect(group.role).toBe('Kitchen tap');
    expect(group.product_ids).toEqual([id(OPTIONS[1]), id(OPTIONS[0]), id(OPTIONS[2])]);
  });

  it('the fold sits where the first pick was', () => {
    const out = lineToDraft(
      saved([
        resolved(OPTIONS[0], 'Kitchen tap'),
        resolved('SRTMCB8083-BL', null),
        resolved(OPTIONS[1], 'Kitchen tap'),
      ]),
    );
    expect(out.parts.map((p) => p.role)).toEqual(['Kitchen tap', null]);
  });

  it('a lone resolved part stays a plain row', () => {
    const out = lineToDraft(saved([resolved(OPTIONS[0], 'Kitchen tap')]));
    expect(out.parts).toHaveLength(1);
    expect(out.parts[0].product_id).toBe(id(OPTIONS[0]));
    expect((out.parts[0] as unknown as { product_ids?: string[] }).product_ids ?? []).toHaveLength(0);
  });

  it('save then reopen gives the same picks in the same order', () => {
    const [payload] = draftLinesPayload([line()], 'list');
    const reopened = lineToDraft(
      saved((payload.parts ?? []).map((p, i) => ({ id: `r${i}`, code: '', name: '', candidates: [], ...p }))),
    );
    expect((reopened.parts[0] as unknown as { product_ids: string[] }).product_ids).toEqual([
      id(OPTIONS[1]),
      id(OPTIONS[0]),
      id(OPTIONS[2]),
    ]);
  });
});

describe('switching to a template that needs fewer', () => {
  const ids = (l: DraftLine) => (l.parts[0] as unknown as { product_ids?: string[] }).product_ids;

  it('keeps the first picks and drops the rest', () => {
    const two = api.trimPicksToTemplate(
      line({ tag_templates: [tpl('t3', [3]), tpl('t2', [2])], tag_template_id: 't2' }),
    );
    expect(ids(two)).toEqual([id(OPTIONS[1]), id(OPTIONS[0])]);
  });

  it('a template needing one turns the row back into a single pick of the first', () => {
    const one = api.trimPicksToTemplate(line({ tag_template_id: 't1' }));
    expect(one.parts[0].product_id).toBe(id(OPTIONS[1]));
    expect(ids(one) ?? []).toHaveLength(0);
  });

  it('a template that does not read the group still keeps one pick', () => {
    const none = api.trimPicksToTemplate(
      line({ tag_templates: [tpl('t3', [3]), tpl('t0', [])], tag_template_id: 't0' }),
    );
    expect(none.parts[0].product_id).toBe(id(OPTIONS[1]));
  });

  it('never adds picks, and leaves a template that needs as many untouched', () => {
    const same = api.trimPicksToTemplate(line());
    expect(ids(same)).toEqual([id(OPTIONS[1]), id(OPTIONS[0]), id(OPTIONS[2])]);
    const more = api.trimPicksToTemplate(
      line({ tag_templates: [tpl('t5', [5]), tpl('t1', [1])], tag_template_id: 't5' }),
    );
    expect(ids(more)).toHaveLength(3);
  });
});

describe('linePickProblems', () => {
  it('a group short of picks says how many more', () => {
    const l = line({ parts: [picksPart([id(OPTIONS[0])])] });
    expect(api.linePickProblems([l], {})).toEqual(['Kitchen tap: pick 2 more.']);
  });

  it('no picks at all asks for all k', () => {
    const l = line({ parts: [picksPart([])] });
    expect(api.linePickProblems([l], {})).toEqual(['Kitchen tap: pick 3 more.']);
  });

  it('N1: a deleted group row still owes the template its picks', () => {
    const l = line({ parts: [] });
    expect(api.linePickProblems([l], {})).toEqual(['Kitchen tap: pick 3 more.']);
  });

  it('N1: a deleted group row owes one pick to a template that reads one', () => {
    const l = line({ tag_template_id: 't1', parts: [] });
    expect(api.linePickProblems([l], {})).toEqual(['Kitchen tap: pick 1 more.']);
  });

  it('N1: a fixed part the template reads and the line no longer has is named', () => {
    const withFixed = {
      ...S1_COMBO,
      parts: [{ product_id: 'fx', code: 'SRTFIX', name: 'Fixed', choice_group: null, is_discontinued: false }, ...S1_COMBO.parts],
    };
    const needs = { fixed: 1, groups: [3], upgrades: 0 };
    const full = [picksPart([id(OPTIONS[0]), id(OPTIONS[1]), id(OPTIONS[2])])];
    const base = { combos: [withFixed], tag_templates: [tpl('t3', [3], { needs })] };
    expect(api.linePickProblems([line({ ...base, parts: full })], {})).toEqual(['Template needs SRTFIX.']);
    const fixed = { key: 'f', product_id: 'fx', code: 'SRTFIX', name: 'Fixed', role: null, candidates: [] };
    expect(api.linePickProblems([line({ ...base, parts: [fixed, ...full] })], {})).toEqual([]);
  });

  it('N1: a line whose template reads no group is not refused for lacking one', () => {
    const l = line({ tag_templates: [tpl('t0', [0])], tag_template_id: 't0', parts: [] });
    expect(api.linePickProblems([l], {})).toEqual([]);
  });

  it('a full group is fine', () => {
    expect(api.linePickProblems([line()], {})).toEqual([]);
  });

  it('a group the template needs one from is not a problem while open', () => {
    const l = line({ tag_template_id: 't1', parts: [picksPart([])] });
    expect(api.linePickProblems([l], {})).toEqual([]);
  });

  it('works off the lone template when the line has only one', () => {
    const l = line({ tag_templates: [tpl('t3', [3])], tag_template_id: null, parts: [picksPart([id(OPTIONS[0])])] });
    expect(api.linePickProblems([l], {})).toEqual(['Kitchen tap: pick 2 more.']);
  });

  it('keeps line order', () => {
    const ok = line({ key: 'a' });
    const short = line({ key: 'b', parts: [picksPart([id(OPTIONS[0]), id(OPTIONS[1])])] });
    const none = line({ key: 'c', parts: [picksPart([])] });
    expect(api.linePickProblems([ok, short, none], {})).toEqual([
      'Kitchen tap: pick 1 more.',
      'Kitchen tap: pick 3 more.',
    ]);
  });

  // PRICETAG-DISCONTINUED-PICK (owner, 7 Nov): a discontinued option is a valid choice.
  it('a discontinued multi pick does not block', () => {
    const combo = {
      ...S1_COMBO,
      parts: S1_COMBO.parts.map((p) => (p.code === OPTIONS[2] ? { ...p, is_discontinued: true } : p)),
    };
    const l = line({ combos: [combo] });
    expect(api.linePickProblems([l], {})).toEqual([]);
  });

  // Owner ruling, 7 Nov ~21:50: a discontinued fixed part is a warning (its row badge), not an
  // Approve block either.
  it('neither a discontinued single pick nor a discontinued fixed part blocks', () => {
    const combo = {
      ...S1_COMBO,
      parts: [
        ...S1_COMBO.parts.map((p) => (p.code === OPTIONS[0] ? { ...p, is_discontinued: true } : p)),
        { product_id: 'fx', code: 'SRTMCB8083-BL', name: 'Mirror', choice_group: null, is_discontinued: true },
      ],
    };
    const single = { key: 's', product_id: id(OPTIONS[0]), code: OPTIONS[0], name: OPTIONS[0], role: 'Kitchen tap', candidates };
    const fixed = { key: 'f', product_id: 'fx', code: 'SRTMCB8083-BL', name: 'Mirror', role: null, candidates: [] };
    const l = line({ combos: [combo], tag_template_id: 't1', parts: [fixed, single] });
    expect(api.linePickProblems([l], {})).toEqual([]);
  });

  it('a discontinued Upgrade pick and a discontinued one-option group do not block', () => {
    const combo = {
      ...S1_COMBO,
      parts: [
        { product_id: 'solo', code: 'SRTSOLO', name: 'Solo', choice_group: 'Waste', is_discontinued: true },
        { product_id: 'up', code: 'SRTUP', name: 'Up', choice_group: null, is_upgrade: true, is_discontinued: true },
        ...S1_COMBO.parts,
      ],
    };
    const solo = { key: 'w', product_id: 'solo', code: 'SRTSOLO', name: 'Solo', role: 'Waste', candidates: [] };
    const upgrade = { key: 'u', product_id: 'up', code: 'SRTUP', name: 'Up', role: 'Upgrade', candidates: [] };
    const l = line({ combos: [combo], parts: [...line().parts, solo, upgrade] });
    expect(api.linePickProblems([l], {})).toEqual([]);
  });

  it('an LP combo line with no combo list price blocks', () => {
    const l = line({ price_type: 'list' });
    expect(api.linePickProblems([l], { l1: { list_price: null, sell_price: null } })).toEqual([
      'No combo list price.',
    ]);
  });

  it('follows the request mode when the line has no price type of its own', () => {
    const l = line();
    expect(api.linePickProblems([l], { l1: { list_price: null } }, 'list')).toHaveLength(1);
    expect(api.linePickProblems([l], { l1: { list_price: null } }, 'selling')).toEqual([]);
  });

  it('an LP line that has a combo list price is fine, and so is a line not yet priced', () => {
    const l = line({ price_type: 'list' });
    expect(api.linePickProblems([l], { l1: { list_price: 2500 } })).toEqual([]);
    expect(api.linePickProblems([l], {})).toEqual([]);
  });

  it('an SP combo line with no selling price blocks, the typed price being the way out (round 3)', () => {
    const l = line({ price_type: 'selling' });
    const reason = 'No combo selling price.';
    expect(api.linePickProblems([l], { l1: { list_price: null, sell_price: null } })).toEqual([reason]);
    expect(api.linePickProblems([l], { l1: { list_price: 2500, sell_price: null } })).toEqual([reason]);
    expect(api.linePickProblems([line({ price_type: 'selling', manual_sell_price: 1234 })], { l1: { sell_price: null } })).toEqual([]);
    expect(api.linePickProblems([l], { l1: { list_price: null, sell_price: 1800 } })).toEqual([]);
    expect(api.linePickProblems([l], {})).toEqual([]);
  });

  it('M2: with a promotion picked the reason is the same fact (the cell carries the hint)', () => {
    const l = line({ price_type: 'selling', promotion_id: 'promo-1' });
    expect(api.linePickProblems([l], { l1: { list_price: 2500, sell_price: null } })).toEqual([
      'No combo selling price.',
    ]);
  });

  it('follows the request mode for SP too, and a line with no combo is never blocked', () => {
    const l = line();
    expect(api.linePickProblems([l], { l1: { sell_price: null } }, 'selling')).toHaveLength(1);
    expect(api.linePickProblems([l], { l1: { list_price: 2500, sell_price: null } }, 'list')).toEqual([]);
    const plain = line({ combo_id: null, combos: [], parts: [], price_type: 'selling' });
    expect(api.linePickProblems([plain], { l1: { sell_price: null } })).toEqual([]);
  });

  it('a line with no combo is never blocked for a combo list price', () => {
    const l = line({ combo_id: null, combos: [], parts: [], price_type: 'list' });
    expect(api.linePickProblems([l], { l1: { list_price: null } })).toEqual([]);
  });
});


describe('a fixed part that arrives from the combo with its discontinued flag', () => {
  it('partsFromCombo carries is_discontinued onto the fixed row', () => {
    const rows = draft.partsFromCombo({
      combo_id: 'c',
      name: 'C',
      parts: [
        { product_id: 'a', code: 'A', name: 'A', choice_group: null, is_discontinued: true },
        { product_id: 'b', code: 'B', name: 'B', choice_group: null },
      ],
    } as never);
    expect(rows.map((r) => (r as { is_discontinued?: boolean }).is_discontinued)).toEqual([true, false]);
  });
});
