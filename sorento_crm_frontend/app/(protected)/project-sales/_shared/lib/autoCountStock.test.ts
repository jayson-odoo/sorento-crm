/**
 * STOCK-STATUS round 6 (owner OK of mock v6, 18 Oct 07:56; UAC AC-31, AC-32): the stock table
 * keeps today's rows and sets, and its On hand / SO qty / PO qty / SPO qty read AutoCount's
 * figures; Available, Available for Project and each set's net follow from them; every location
 * AutoCount holds that the table does not list joins as an "Other group" row.
 */
import { describe, expect, it } from 'vitest';
import { withAutoCount } from './autoCountStock';
import type { BoardCellLocation } from '../types/fulfilmentPlanning.types';
import type { StockStatus } from '@/components/stock-status/stockStatus.types';

function row(location: string, extra: Partial<BoardCellLocation> = {}): BoardCellLocation {
  return {
    location,
    product_id: 'prod-1',
    warehouse_id: `wh-${location}`,
    qty: '0',
    qty_on_hand: '0',
    so_qty: '0',
    spo_qty: '0',
    available_qty: '0',
    po_open_qty: '0',
    ...extra,
  };
}

function loc(code: string, on_hand: number, so_qty: number, po_qty: number, spo_qty: number) {
  return {
    warehouse_id: `wh-${code}`,
    warehouse_code: code,
    warehouse_name: code,
    is_active: true,
    on_hand,
    so_qty,
    po_qty,
    spo_qty,
    forecast: on_hand - so_qty + po_qty + spo_qty,
  };
}

// SO422380 L80's own group (today: SO qty 2156 nets the line's own 2) and AutoCount's report.
const TODAY: BoardCellLocation[] = [
  row('BRW-IB', { where: 'own', net_of: 'IB', qty_on_hand: '6', so_qty: '2156', spo_qty: '24', available_qty: '-2126', po_open_qty: '338', net: '-1986' }),
  row('MWH-IB', { where: 'group', net_of: 'IB', qty_on_hand: '140', available_qty: '140', net: '-1986' }),
  row('RSW-IB', { where: 'group', net_of: 'IB', net: '-1986' }),
  row('BRW', { where: 'site_pool', net_of: 'pools', so_qty: '59', available_qty: '-59', po_open_qty: '318', available_for_project: '0', net: '-79' }),
  row('RESERVE', { where: 'site_pool', net_of: 'pools', so_qty: '20', available_qty: '-20', available_for_project: '0', net: '-79' }),
  row('MWH', { where: 'site_pool', net_of: 'pools', qty_on_hand: '0', available_for_project: '0', net: '-79' }),
];

const STATUS = {
  product_id: 'prod-1',
  locations: [
    loc('BRW-BB', 0, 7312, 1734, 50),
    loc('MWH-IB', 140, 0, 0, 0),
    loc('RESERVE', 0, 20, 0, 0),
    loc('BRW', 0, 59, 318, 0),
    loc('BRW-IB', 6, 2158, 338, 24),
    loc('MWH', 30, 0, 0, 0),
  ],
} as unknown as StockStatus;

const by = (rows: BoardCellLocation[], code: string) => rows.find((r) => r.location === code)!;

describe('withAutoCount', () => {
  it("fills On hand, SO qty, PO qty and SPO qty with AutoCount's figures, Available following", () => {
    const rows = withAutoCount(TODAY, STATUS, 50);
    const own = by(rows, 'BRW-IB');
    expect([own.qty_on_hand, own.so_qty, own.po_open_qty, own.spo_qty]).toEqual(['6', '2158', '338', '24']);
    expect(own.available_qty).toBe('-2128');
  });

  it('reads 0 at a listed location AutoCount holds nothing at', () => {
    const rsw = by(withAutoCount(TODAY, STATUS, 50), 'RSW-IB');
    expect([rsw.qty_on_hand, rsw.so_qty, rsw.po_open_qty, rsw.spo_qty, rsw.available_qty]).toEqual(['0', '0', '0', '0', '0']);
  });

  it("restates each set's net as the sum of its rows' Available", () => {
    const rows = withAutoCount(TODAY, STATUS, 50);
    expect(rows.filter((r) => r.net_of === 'IB').map((r) => r.net)).toEqual(['-1988', '-1988', '-1988']);
    expect(rows.filter((r) => r.net_of === 'pools').map((r) => r.net)).toEqual(['-49', '-49', '-49']);
  });

  it("gives a site pool row its project share of its own Available, capped by the pools' net", () => {
    const rows = withAutoCount(TODAY, STATUS, 50);
    expect(by(rows, 'MWH').available_for_project).toBe('0'); // 30 x 50% = 15, but the pools net -49
    expect(by(rows, 'BRW').available_for_project).toBe('0');
    const rich = withAutoCount(TODAY, { ...STATUS, locations: [...STATUS.locations.filter((l) => l.warehouse_code !== 'RESERVE' && l.warehouse_code !== 'BRW')] } as StockStatus, 50);
    expect(by(rich, 'MWH').available_for_project).toBe('15');
  });

  it('adds every location AutoCount holds and the table does not list, as an Other group row', () => {
    const rows = withAutoCount(TODAY, STATUS, 50);
    const extra = by(rows, 'BRW-BB');
    expect(rows.indexOf(extra)).toBe(TODAY.length); // after today's rows, in AutoCount's order
    expect(extra).toMatchObject({
      where: 'other_group',
      product_id: 'prod-1',
      warehouse_id: 'wh-BRW-BB',
      qty_on_hand: '0',
      so_qty: '7312',
      po_open_qty: '1734',
      spo_qty: '50',
      available_qty: '-7262',
    });
    expect(extra.net_of ?? null).toBeNull();
  });

  it("puts a location of a group the table nets into that group's set, and counts it in the net", () => {
    const status = { ...STATUS, locations: [...STATUS.locations, loc('DC1-IB', 5, 0, 0, 0)] } as StockStatus;
    const rows = withAutoCount(TODAY, status, 50);
    expect(rows.map((r) => r.location)).toEqual(['BRW-IB', 'MWH-IB', 'RSW-IB', 'DC1-IB', 'BRW', 'RESERVE', 'MWH', 'BRW-BB']);
    expect(by(rows, 'DC1-IB')).toMatchObject({ where: 'group', net_of: 'IB', available_qty: '5' });
    expect(rows.filter((r) => r.net_of === 'IB').map((r) => r.net)).toEqual(['-1983', '-1983', '-1983', '-1983']);
  });

  it('leaves a row with no location as it is (the line whose sales order names none)', () => {
    const blank = row('', { location: null, qty_on_hand: null, so_qty: null });
    expect(withAutoCount([blank], STATUS, 50)[0]).toEqual(blank);
  });

  it('builds the whole table from AutoCount alone when given no rows (the stand-alone page)', () => {
    const rows = withAutoCount([], STATUS, 50);
    expect(rows.map((r) => r.location)).toEqual(['BRW-BB', 'MWH-IB', 'RESERVE', 'BRW', 'BRW-IB', 'MWH']);
    expect(rows.every((r) => r.where === 'other_group' && (r.net ?? null) === null)).toBe(true); // no subtotal, as v6 draws it
  });
});
