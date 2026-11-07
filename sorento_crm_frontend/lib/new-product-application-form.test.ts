/**
 * NEW-PRODUCT-APP v4 (AC-NPA-70, 71, 79): the write payload carries only the paper form's keys,
 * saved products keep their id, and an emptied quantity is null. Red until the v4 form state lands.
 */
import { describe, it, expect } from 'vitest';
import {
  EMPTY_FORM,
  blankLine,
  numberErrors,
  payloadFromState,
  stateFromDetail,
  stateFromPrefill,
} from '@/lib/new-product-application-form';

const HEADER_KEYS = [
  'current_product_ids',
  'customer_id',
  'customer_name',
  'lines',
  'needed_by',
  'project_name',
  'remark',
  'stock_inquiry_id',
];
const LINE_KEYS = [
  'description',
  'dimension',
  'expected_qty',
  'id',
  'material',
  'packing',
  'proposed_code',
  'thickness',
];
const REMOVED = [
  'category_id',
  'base_uom_id',
  'item_type_id',
  'supplier_id',
  'supplier_item_code',
  'cost_price',
  'selling_price',
  'further_description',
  'lead_time',
];

describe('payloadFromState (v4)', () => {
  it('sends only the v4 header and line keys, and keeps id on a saved line', () => {
    const saved = {
      ...blankLine(),
      id: 'l-7',
      proposed_code: 'XY-1',
      description: 'Example sink',
      dimension: '600x400',
      material: 'Steel',
      thickness: '1.2mm',
      packing: 'Carton',
      brand_id: 'b-1',
      expected_qty: '55',
      // purchasing's figure lives in state for display but is never written here
      cost_price: '12.50',
    };
    const fresh = { ...blankLine(), description: 'Another sink' };
    const body = payloadFromState({
      ...EMPTY_FORM,
      stock_inquiry_id: 'si-1',
      customer_name: 'EXAMPLE DEVELOPER SDN BHD',
      current_products: [
        { id: 'p-2', product_code: 'B-2' },
        { id: 'p-1', product_code: 'A-1' },
      ],
      lines: [saved, fresh],
    }) as unknown as Record<string, unknown> & {
      lines: Record<string, unknown>[];
    };

    expect(Object.keys(body).sort()).toEqual(HEADER_KEYS);
    for (const l of body.lines) {
      for (const k of Object.keys(l)) expect(LINE_KEYS).toContain(k);
      for (const k of REMOVED) expect(l).not.toHaveProperty(k);
    }
    for (const k of REMOVED) expect(body).not.toHaveProperty(k);
    expect(body.lines[0]).toMatchObject({
      id: 'l-7',
      proposed_code: 'XY-1',
      description: 'Example sink',
      dimension: '600x400',
      material: 'Steel',
      thickness: '1.2mm',
      packing: 'Carton',
      expected_qty: '55',
    });
    expect(body.lines[1].id ?? null).toBeNull();
    // header codes: ids only, picked order, always sent
    expect(body.current_product_ids).toEqual(['p-2', 'p-1']);
    for (const l of body.lines) expect(l).not.toHaveProperty('current_product_ids');
  });

  it('always sends the header codes so clearing the pick clears them', () => {
    const body = payloadFromState({ ...EMPTY_FORM, lines: [blankLine()] });
    expect(body.current_product_ids).toEqual([]);
  });

  it('sends null for an emptied quantity and for empty text', () => {
    const body = payloadFromState({
      ...EMPTY_FORM,
      lines: [{ ...blankLine(), expected_qty: '', dimension: '  ' }],
    });
    const line = body.lines?.[0] as unknown as Record<string, unknown>;
    expect(line.expected_qty).toBeNull();
    expect(line.dimension).toBeNull();
    expect(line).not.toHaveProperty('brand_id');
  });

  it('never sends brand_id on a line, even when the draft still carries one (Brand column removed)', () => {
    const body = payloadFromState({
      ...EMPTY_FORM,
      lines: [{ ...blankLine(), description: 'Sink', brand_id: 'b-1', brand_label: 'Example Brand' }],
    });
    expect(body.lines?.[0]).not.toHaveProperty('brand_id');
  });
});

describe('stateFromDetail (v4)', () => {
  it('reads the paper fields and purchasing feedback, no images', () => {
    const state = stateFromDetail({
      id: 'a-1',
      stock_inquiry_id: null,
      lead_time: '3 weeks',
      lines: [
        {
          id: 'l-1',
          line_no: 1,
          proposed_code: 'XY-1',
          description: 'Example sink',
          dimension: '600x400',
          material: 'Steel',
          thickness: '1.2mm',
          packing: 'Carton',
          brand_id: 'b-1',
          brand_name: 'Example Brand',
          expected_qty: '55',
          cost_price: '12.50',
        },
      ],
    } as never);
    expect(state.lead_time).toBe('3 weeks');
    const l = state.lines[0];
    expect(l.id).toBe('l-1');
    expect(l.dimension).toBe('600x400');
    expect(l.packing).toBe('Carton');
    expect(l.brand_label).toBe('Example Brand');
    expect(l.cost_price).toBe('12.50');
    // v5: no per-product images or staged files
    expect(l).not.toHaveProperty('images');
    expect(l).not.toHaveProperty('staged_images');
    expect(l).not.toHaveProperty('removed_link_ids');
  });
});

describe('header product codes (NPA-FROM-SI)', () => {
  it('detail maps current_products and the suggestions', () => {
    const state = stateFromDetail({
      id: 'a-1',
      stock_inquiry_id: null,
      current_products: [
        { id: 'p-1', product_code: 'A-1', product_name: 'A', is_active: true },
      ],
      suggestions: [{ product_id: 'p-9', product_code: 'A-1-69' }],
      lines: [],
    } as never);
    expect(state.current_products).toEqual([{ id: 'p-1', product_code: 'A-1' }]);
    expect(state.suggestions).toHaveLength(1);
    expect(state.suggestions_for).toBe('p-1');
  });

  it('prefill with a matched code starts picked and has no hint', () => {
    const state = stateFromPrefill({
      stock_inquiry_id: 'si-1',
      stock_inquiry_number: 'SI26-1',
      current_products: [{ id: 'p-1', product_code: 'A-1' }],
      lines: [{ proposed_code: 'A-1' }],
    } as never);
    expect(state.current_products).toEqual([{ id: 'p-1', product_code: 'A-1' }]);
    expect(state.inquiry_code_hint).toBe('');
  });

  it('prefill with unmatched text starts empty and keeps the text as the hint', () => {
    const state = stateFromPrefill({
      stock_inquiry_id: 'si-1',
      stock_inquiry_number: 'SI26-1',
      current_products: [],
      lines: [{ proposed_code: 'A-1 & B-2' }],
    } as never);
    expect(state.current_products).toEqual([]);
    expect(state.inquiry_code_hint).toBe('A-1 & B-2');
  });
});

describe('numberErrors (v4)', () => {
  it('checks the quantity only; cost is purchasing feedback, not a write field', () => {
    const line = { ...blankLine(), expected_qty: '-3' };
    const found = numberErrors({ lines: [line] });
    expect(found[`expected_qty_${line.key}`]).toBeTruthy();
    expect(Object.keys(found).some((k) => k.startsWith('selling_price'))).toBe(
      false,
    );
  });
});
