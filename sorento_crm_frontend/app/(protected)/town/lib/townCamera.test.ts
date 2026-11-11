import { describe, expect, it } from 'vitest';
import {
  DEFAULT_VIEW,
  TILT_MAX,
  TILT_MIN,
  ZOOM_MAX,
  ZOOM_MIN,
  cameraPosition,
  dragView,
  pinchZoom,
  stepZoom,
  wheelZoom,
} from './townCamera';
import { townTip } from './townTips';

const deg = (rad: number) => (rad * 180) / Math.PI;

describe('town camera', () => {
  it('starts north up over Shah Alam (TOWN-PROJECT-CITY): 142 degrees round, ~41 degrees up, the live scale', () => {
    expect(deg(DEFAULT_VIEW.yaw)).toBeCloseTo(142);
    expect(deg(DEFAULT_VIEW.tilt)).toBeCloseTo(deg(Math.atan2(70, 80)));
    expect(DEFAULT_VIEW.zoom).toBe(1);
    const [x, y, z] = cameraPosition(DEFAULT_VIEW, 3);
    expect([x, y, z].map((v) => Math.round(v))).toEqual([80 * Math.cos(142 * (Math.PI / 180)), 73, 80 * Math.sin(142 * (Math.PI / 180))].map(Math.round));
  });

  it('turns on a sideways drag and tilts on an up-down drag, within 20 and 80 degrees', () => {
    const turned = dragView(DEFAULT_VIEW, 100, 0);
    expect(turned.yaw).toBeCloseTo(DEFAULT_VIEW.yaw - 0.6);
    expect(turned.tilt).toBe(DEFAULT_VIEW.tilt);
    const down = dragView(DEFAULT_VIEW, 0, 60);
    expect(down.tilt).toBeGreaterThan(DEFAULT_VIEW.tilt);
    expect(down.yaw).toBe(DEFAULT_VIEW.yaw);
    expect(deg(dragView(DEFAULT_VIEW, 0, 5000).tilt)).toBeCloseTo(80);
    expect(deg(dragView(DEFAULT_VIEW, 0, -5000).tilt)).toBeCloseTo(20);
    expect(deg(TILT_MIN)).toBeCloseTo(20);
    expect(deg(TILT_MAX)).toBeCloseTo(80);
  });

  it('zooms by wheel, pinch and buttons, never outside 0.13x (all of Malaysia) to 2.2x', () => {
    expect(wheelZoom(1, -100)).toBeGreaterThan(1);
    expect(wheelZoom(1, 100)).toBeLessThan(1);
    expect(wheelZoom(2.1, -100000)).toBe(ZOOM_MAX);
    expect(wheelZoom(0.2, 100000)).toBe(ZOOM_MIN);
    expect(pinchZoom(1, 100, 200)).toBe(2);
    expect(pinchZoom(1, 100, 1000)).toBe(ZOOM_MAX);
    expect(pinchZoom(1, 100, 5)).toBe(ZOOM_MIN);
    expect(stepZoom(1, 1)).toBeCloseTo(1.25);
    expect(stepZoom(1, -1)).toBeCloseTo(0.8);
    expect(stepZoom(2.2, 1)).toBe(ZOOM_MAX);
    expect([ZOOM_MIN, ZOOM_MAX]).toEqual([0.13, 2.2]);
  });
});

const SNAPSHOT = {
  schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { amount: '12345.60', invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [], warehouses: [{ pool: 'WH01', on_hand: 1234, available: 1000, locations: 3 }],
  reorder: { below_count: 1527, set_count: 9000 }, deliveries: { to_deliver: 14 },
  approvals: { total: 1, purchase_requests: 1, quotation_documents: 0 },
  incoming: { incoming: 29, late: 70, next_eta: '2026-01-07', shipments: [] },
} as never;

describe('town tooltips', () => {
  it('names a shop and gives its one number, without amounts when hidden', () => {
    const named = { key: 'k', kind: 'shop', account_label: 'A/C I', today_docs: 2, name: 'ZZT Tiling SDN BHD [A/C I]', today_amount: '9589.40' };
    expect(townTip(SNAPSHOT, { kind: 'shop', shop: named as never })).toEqual({ title: 'ZZT Tiling [A/C I]', detail: 'RM 9,589 today' });
    const anon = { key: 's1', kind: 'shop', account_label: null, today_docs: 2 };
    expect(townTip(SNAPSHOT, { kind: 'shop', shop: anon as never })).toEqual({ title: 'Dealer', detail: '2 invoices today' });
    const quiet = { key: 's2', kind: 'shop', account_label: null, today_docs: 0, rank: 4 };
    expect(townTip(SNAPSHOT, { kind: 'shop', shop: quiet as never })).toEqual({ title: 'Shop #4', detail: 'No invoice today' });
  });

  it('gives every other building its name and key number', () => {
    expect(townTip(SNAPSHOT, { kind: 'sales' })).toEqual({ title: "Today's sales", detail: 'RM 12,346 · 3 invoices' });
    expect(townTip(SNAPSHOT, { kind: 'warehouse', index: 0 })).toEqual({ title: 'Warehouse WH01', detail: '1,234 on hand' });
    expect(townTip(SNAPSHOT, { kind: 'low' })).toEqual({ title: 'Low stock', detail: '1,527 products below reorder level' });
    expect(townTip(SNAPSHOT, { kind: 'deliver' })).toEqual({ title: 'Depot', detail: '14 sales orders to deliver' });
    expect(townTip(SNAPSHOT, { kind: 'approve' })).toEqual({ title: 'Approvals', detail: '1 waiting for a decision' });
    expect(townTip(SNAPSHOT, { kind: 'port' })).toEqual({ title: 'Port', detail: '29 incoming · 70 late' });
  });

  it('says so when there is nothing to show', () => {
    const quiet = { ...(SNAPSHOT as object), approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 }, incoming: { incoming: 0, late: 0, next_eta: null, shipments: [] } } as never;
    expect(townTip(quiet, { kind: 'approve' })).toEqual({ title: 'Approvals', detail: 'All clear' });
    expect(townTip(quiet, { kind: 'port' })).toEqual({ title: 'Port', detail: 'Nothing on the way' });
  });

  it('names where a lorry is going: a shop in the town, or a customer outside it (named on the personal view only)', () => {
    const withShop = { ...(SNAPSHOT as object), shops: [{ key: 'k1', kind: 'shop', account_label: 'A/C I', today_docs: 0, name: 'ZZT Tiling SDN BHD [A/C I]' }] } as never;
    expect(townTip(withShop, { kind: 'lorry', customer: { key: 'k1', orders: 3 } })).toEqual({ title: 'Lorry to ZZT Tiling [A/C I]', detail: '3 orders due today or overdue' });
    expect(townTip(withShop, { kind: 'lorry', customer: { key: null, name: 'ZZT Faraway SDN BHD', orders: 1 } })).toEqual({ title: 'Customer outside the town', detail: 'ZZT Faraway · 1 order due today or overdue' });
    expect(townTip(withShop, { kind: 'lorry', customer: { key: null, orders: 2 } })).toEqual({ title: 'Customer outside the town', detail: '2 orders due today or overdue' });
  });

  it('names a ship or a late container by its shipment, with the supplier only when the snapshot carries one', () => {
    const row = { shipment_number: 'SHP-1', container: 'C1', eta: null, products: 4, quantity: 10, late: false };
    expect(townTip(SNAPSHOT, { kind: 'shipment', row })).toEqual({ title: 'SHP-1 on the water', detail: 'No ETA · 4 products' });
    const late = { ...row, late: true, supplier: 'ZZT Supplier' };
    expect(townTip(SNAPSHOT, { kind: 'shipment', row: late })).toEqual({ title: 'SHP-1 · late', detail: 'No ETA · 4 products · ZZT Supplier' });
  });
});
