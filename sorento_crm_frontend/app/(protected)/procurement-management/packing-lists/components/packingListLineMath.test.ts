import { describe, expect, it } from 'vitest';
import { deriveLineCells } from './packingListLineMath';

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
