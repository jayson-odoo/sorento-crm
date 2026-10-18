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
} from '@/lib/new-product-application-form';

const HEADER_KEYS = [
  'customer_id',
  'customer_name',
  'lines',
  'needed_by',
  'project_name',
  'remark',
  'stock_inquiry_id',
];
const LINE_KEYS = [
  'brand_id',
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
      brand_id: 'b-1',
      expected_qty: '55',
    });
    expect(body.lines[1].id ?? null).toBeNull();
  });

  it('sends null for an emptied quantity and for empty text', () => {
    const body = payloadFromState({
      ...EMPTY_FORM,
      lines: [{ ...blankLine(), expected_qty: '', dimension: '  ' }],
    });
    const line = body.lines?.[0] as unknown as Record<string, unknown>;
    expect(line.expected_qty).toBeNull();
    expect(line.dimension).toBeNull();
    expect(line.brand_id).toBeNull();
  });
});

describe('stateFromDetail (v4)', () => {
  it('reads the paper fields, the product images and purchasing feedback', () => {
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
          images: [
            {
              link_id: 'k-1',
              attachment_id: 'at-1',
              filename: 'sample-front.png',
              url: '/files/1',
              content_type: 'image/png',
            },
          ],
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
    expect(l.images.map((i) => i.filename)).toEqual(['sample-front.png']);
    expect(l.staged_images).toEqual([]);
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
