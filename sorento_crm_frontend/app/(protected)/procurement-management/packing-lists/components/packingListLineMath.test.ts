import { describe, expect, it } from 'vitest';
import type { ConsolidatedPackingList } from '@/app/(protected)/scm/services/fulfilmentService';
import { computeCompanySplit, deriveLineCells } from './packingListLineMath';

/**
 * Numbers read straight off `documentation/plans/scm/fixtures/FSCU8103365.xlsx`, tab RMB -
 * the reference `tests/test_consolidated_packing_list_fidelity.py` pins the backend against.
 * Row 18 (AFFANNI, SORENTO): qty 216, pcs/ctn 24, 50x41.5x46cm, NW 0, GW 15.4, price 83.5.
 * Row 26 (AFFANNI, MOCHA): qty 200, pcs/ctn 10, 62x53.5x30.5cm, NW 0, GW 19, price 100.
 */
describe('deriveLineCells - the workbook cells nobody types (AC-G2)', () => {
  it('derives ctn qty, cbm/ctn, total cbm, total gw and amount off row 18', () => {
    const cells = deriveLineCells({
      quantity_shipped: 216,
      pcs_per_carton: 24,
      carton_length_cm: 50,
      carton_width_cm: 41.5,
      carton_height_cm: 46,
      net_weight_per_carton: 0,
      gross_weight_per_carton: 15.4,
      unit_cost: 83.5,
    });

    expect(cells.ctnQty).toBe(9);
    expect(Number(cells.cbmPerCtn!.toFixed(5))).toBe(0.09545);
    expect(Number(cells.totalCbm!.toFixed(3))).toBe(0.859);
    expect(cells.totalNw).toBe(0);
    expect(Number(cells.totalGw!.toFixed(1))).toBe(138.6);
    expect(cells.amount).toBe(18036);
  });

  it('falls back to the stored ctn count when no pack size is stated', () => {
    // HONGJIE-style row: no PCS/CTN, so CTN QTY is whatever was stored, and with no size
    // the total cbm is the flat stated cbm rather than a formula with no inputs.
    const cells = deriveLineCells({
      quantity_shipped: 73,
      cartons_count: 73,
      cbm: 12.5,
    });

    expect(cells.ctnQty).toBe(73);
    expect(cells.cbmPerCtn).toBeNull();
    expect(cells.totalCbm).toBe(12.5);
  });

  it('reads the legacy single weight as the gross one where the split column is blank', () => {
    const cells = deriveLineCells({
      quantity_shipped: 100,
      cartons_count: 30,
      weight_per_carton: 4.5,
    });
    expect(cells.totalGw).toBe(135);
  });

  it('states nothing rather than 0 for a line nobody measured', () => {
    const cells = deriveLineCells({ quantity_shipped: 10 });
    expect(cells.ctnQty).toBeNull();
    expect(cells.totalCbm).toBeNull();
    expect(cells.totalNw).toBeNull();
    expect(cells.totalGw).toBeNull();
    expect(cells.amount).toBeNull();
  });
});

describe('computeCompanySplit - the footer beneath the grid (AC-G4)', () => {
  function buildPayload(): ConsolidatedPackingList {
    return {
      shipment_id: 'ship-1',
      shipment_number: 'SH-1',
      container_no: 'FSCU8103365',
      bl_no: null,
      status: 'in_transit',
      factories: [
        {
          supplier_id: 'sup-affanni',
          supplier_code: 'AFF',
          supplier_name: 'AFFANNI 阿凡尼',
          lines: [
            {
              line_id: 'l-18',
              product_id: 'p-18',
              product_code: 'SRT79-SS-GM',
              product_name: '三叉水咀+喷枪（枪灰）',
              brand: 'SORENTO',
              company: 'SORENTO',
              qty: 216,
              cartons: 9,
              cbm: 0.859,
              remarks: null,
              unit_cost: 83.5,
              currency: 'CNY',
            },
            {
              line_id: 'l-26',
              product_id: 'p-26',
              product_code: 'MKT7820SS-DIY',
              product_name: '45*110单冷抽拉菜盆龙头',
              brand: 'MOCHA',
              company: 'MOCHA',
              qty: 200,
              cartons: 20,
              cbm: 2.0,
              remarks: null,
              unit_cost: 100,
              currency: 'CNY',
            },
          ],
          subtotal: { lines: 2, qty: 416, cartons: 29, cbm: 2.859 },
        },
      ],
      total: { lines: 2, qty: 416, cartons: 29, cbm: 2.859 },
      split: [
        { company: 'SORENTO', lines: 1, qty: 216, cartons: 9, cbm: 0.859 },
        { company: 'MOCHA', lines: 1, qty: 200, cartons: 20, cbm: 2.0 },
      ],
      costs: { clearance_cost: 2700, china_freight_cost: 13950, insurance_rate: 1 },
    };
  }

  it('apportions clearance and china freight by cbm share, insurance by amount share', () => {
    const result = computeCompanySplit(buildPayload());
    const sorento = result.rows.find((r) => r.company === 'SORENTO')!;
    const mocha = result.rows.find((r) => r.company === 'MOCHA')!;

    // Amount: 216*83.5 = 18036 (SORENTO), 200*100 = 20000 (MOCHA).
    expect(sorento.amount).toBe(18036);
    expect(mocha.amount).toBe(20000);

    const totalCbm = 2.859;
    const totalAmount = 38036;
    expect(sorento.clearance).toBeCloseTo((0.859 / totalCbm) * 2700, 6);
    expect(mocha.clearance).toBeCloseTo((2.0 / totalCbm) * 2700, 6);
    expect(sorento.chinaFreight).toBeCloseTo((0.859 / totalCbm) * 13950, 6);
    expect(sorento.insurance).toBeCloseTo((18036 / totalAmount) * 1, 6);
    expect(mocha.insurance).toBeCloseTo((20000 / totalAmount) * 1, 6);

    // The two company rows always total the container figure - the same identity the
    // export's own `=M83+M84` / `=U83+U84` footer rows rely on.
    expect(result.totalClearance).toBeCloseTo(2700, 6);
    expect(result.totalChinaFreight).toBeCloseTo(13950, 6);
    expect(result.totalInsurance).toBeCloseTo(1, 6);
    expect(result.totalAmount).toBe(totalAmount);
  });

  it('prints both companies with zero figures rather than dropping an absent one', () => {
    const payload = buildPayload();
    payload.factories[0].lines = [payload.factories[0].lines[0]];
    payload.split = [
      { company: 'SORENTO', lines: 1, qty: 216, cartons: 9, cbm: 0.859 },
      { company: 'MOCHA', lines: 0, qty: 0, cartons: 0, cbm: 0 },
    ];
    payload.total = { lines: 1, qty: 216, cartons: 9, cbm: 0.859 };

    const result = computeCompanySplit(payload);
    const mocha = result.rows.find((r) => r.company === 'MOCHA')!;
    expect(mocha.cbm).toBe(0);
    expect(mocha.amount).toBe(0);
    expect(mocha.clearance).toBe(0);
  });

  it('leaves the cost columns null when nothing has been typed yet', () => {
    const payload = buildPayload();
    payload.costs = { clearance_cost: null, china_freight_cost: null, insurance_rate: null };

    const result = computeCompanySplit(payload);
    for (const row of result.rows) {
      expect(row.clearance).toBeNull();
      expect(row.insurance).toBeNull();
      expect(row.chinaFreight).toBeNull();
    }
    expect(result.totalClearance).toBeNull();
  });
});
