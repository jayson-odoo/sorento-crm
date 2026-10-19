/**
 * STOCK-GROUPBY S2 (red): the stock lines the table groups, the six dimensions, the measures and
 * the remembered choice. Contract `PLAN-stock-groupby-18oct.md` 5.3, UAC AC-1, AC-2, AC-3, AC-5,
 * AC-18, AC-19. Masked names only.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { StockStatus } from '@/components/stock-status/stockStatus.types';
import {
  DEFAULT_STOCK_GROUP_LEVELS,
  readStockGroupLevels,
  STOCK_GROUP_OPTIONS,
  STOCK_GROUP_STORAGE_KEY,
  STOCK_LINE_MEASURES,
  stockGroupDimensions,
  stockLinesOf,
  writeStockGroupLevels,
} from './stockGroupLines';

const ORDER = ['BRW-IB', 'MWH-IB', 'BRW-BB'];

function loc(code: string, on_hand: number, extra: Record<string, unknown> = {}) {
  return {
    warehouse_id: `wh-${code}`,
    warehouse_code: code,
    warehouse_name: code,
    is_active: true,
    on_hand,
    so_qty: 0,
    po_qty: 0,
    spo_qty: 0,
    forecast: 0,
    ...extra,
  };
}

function so(id: string, warehouse: string, qty: number, extra: Record<string, unknown> = {}) {
  return {
    line_id: `sol-${id}`,
    sales_order_id: `soid-${id}`,
    so_number: `SO-000${id}`,
    debtor_code: `DC-${id}`,
    debtor_name: 'Customer B',
    project_label: 'Project 2',
    salesperson: 'Agent 1',
    doc_date: '2026-09-01',
    due_date: '2026-11-01',
    qty,
    covered_in_crm: false,
    warehouse_id: `wh-${warehouse}`,
    ...extra,
  };
}

const STATUS = {
  product_id: 'prod-1',
  item_code: 'ITEM-1',
  description: null,
  as_of: null,
  so_due_by: null,
  locations: [
    loc('BRW-BB', 17, { so_qty: 396, po_qty: 144 }),
    loc('BRW-IB', 0.2),
    loc('MWH-IB', 0.1, { spo_qty: 50 }),
    loc('NIL-ZZ', 0, { so_qty: 1 }),
  ],
  totals: { on_hand: 17.3, so_qty: 397, po_qty: 144, spo_qty: 50, forecast: 0, incoming_pl: 20, forecast_incl_pl: 0 },
  incoming_pl: [
    { shipment_id: 'sh-1', shipment_number: 'PL-0001', container_number: null, eta: null, still_to_land: 20, on_spo: 0, counted: 20 },
  ],
  sales_orders: [
    so('1', 'BRW-BB', 144),
    so('2', 'BRW-BB', 0.1, { debtor_name: null, debtor_code: 'DC-2', project_label: '  Project 3  ', salesperson: null }),
    so('3', 'BRW-IB', 0.2, { debtor_name: '   ', debtor_code: null, project_label: '', due_date: null }),
    so('4', 'MWH-IB', 1, { project_label: null, salesperson: 'Agent 2' }),
  ],
  purchase_orders: [
    {
      line_id: 'pol-1',
      purchase_order_id: 'poid-1',
      po_number: 'PO-0001',
      supplier_code: 'SUP-1',
      supplier_name: 'Supplier 1',
      issue_date: '2026-09-01',
      expected_date: '2026-12-01',
      qty: 144,
      warehouse_id: 'wh-BRW-BB',
    },
    {
      line_id: 'pol-2',
      purchase_order_id: 'poid-2',
      po_number: 'PO-0002',
      supplier_code: 'SUP-2',
      supplier_name: null,
      issue_date: null,
      expected_date: null,
      qty: 3,
      warehouse_id: 'wh-BRW-IB',
    },
  ],
  spos: [
    {
      allocation_id: 'alloc-1',
      spo_number: 'SPO-2026/08-0001',
      spo_line_number: 1,
      supplier_code: 'SUP-3',
      supplier_name: 'Supplier 3',
      issue_date: null,
      arrival_date: '2026-12-15',
      container_number: null,
      qty: 50,
      warehouse_id: 'wh-MWH-IB',
    },
  ],
} as unknown as StockStatus;

const byKey = (lines: ReturnType<typeof stockLinesOf>, key: string) => {
  const hit = lines.find((l) => l.key === key);
  if (!hit) throw new Error(`no line ${key} in ${lines.map((l) => l.key).join(', ')}`);
  return hit;
};

describe('stockLinesOf (AC-1)', () => {
  const lines = stockLinesOf(STATUS, ORDER);

  it('AC-1 one line per S/O, PO, SPO row and per non-zero on hand location, nothing for Incoming PL', () => {
    expect(lines).toHaveLength(4 + 2 + 1 + 3);
    expect(lines.filter((l) => l.type === 'S/O')).toHaveLength(4);
    expect(lines.filter((l) => l.type === 'PO')).toHaveLength(2);
    expect(lines.filter((l) => l.type === 'SPO')).toHaveLength(1);
    expect(lines.filter((l) => l.type === 'On hand')).toHaveLength(3);
    expect(lines.some((l) => /pl|incoming/i.test(l.key))).toBe(false);
    expect(lines.some((l) => l.docNo === 'PL-0001')).toBe(false);
  });

  it('AC-1 a location whose on hand is zero gets no On hand line', () => {
    expect(lines.some((l) => l.key === 'on-hand:wh-NIL-ZZ')).toBe(false);
  });

  it('AC-1 a negative on hand is not zero, so it is a line', () => {
    const status = { ...STATUS, locations: [loc('BRW-BB', -2)], sales_orders: [], purchase_orders: [], spos: [] } as unknown as StockStatus;
    const [only] = stockLinesOf(status, ORDER);
    expect(only.key).toBe('on-hand:wh-BRW-BB');
    expect(only.onHand).toBe('-2');
  });

  it('AC-1 keys follow the contract', () => {
    expect(lines.map((l) => l.key).sort()).toEqual(
      [
        'on-hand:wh-BRW-BB',
        'on-hand:wh-BRW-IB',
        'on-hand:wh-MWH-IB',
        'so:sol-1',
        'so:sol-2',
        'so:sol-3',
        'so:sol-4',
        'po:pol-1',
        'po:pol-2',
        'spo:alloc-1',
      ].sort(),
    );
  });

  it('AC-1 each line states its quantity in its own column and 0 in the others', () => {
    expect(byKey(lines, 'so:sol-1')).toMatchObject({ so: '144', onHand: '0', spo: '0', po: '0' });
    expect(byKey(lines, 'po:pol-1')).toMatchObject({ po: '144', so: '0', onHand: '0', spo: '0' });
    expect(byKey(lines, 'spo:alloc-1')).toMatchObject({ spo: '50', so: '0', onHand: '0', po: '0' });
    expect(byKey(lines, 'on-hand:wh-BRW-BB')).toMatchObject({ onHand: '17', so: '0', spo: '0', po: '0' });
  });

  it('AC-6 decimal quantities stay exact strings', () => {
    expect(byKey(lines, 'so:sol-2').so).toBe('0.1');
    expect(byKey(lines, 'on-hand:wh-BRW-IB').onHand).toBe('0.2');
  });
});

describe('stockLinesOf values (AC-2, AC-3)', () => {
  const lines = stockLinesOf(STATUS, ORDER);

  it('AC-2 Location is the warehouse code of the line\'s warehouse_id; On hand its own location', () => {
    expect(byKey(lines, 'so:sol-1').location).toBe('BRW-BB');
    expect(byKey(lines, 'so:sol-3').location).toBe('BRW-IB');
    expect(byKey(lines, 'po:pol-2').location).toBe('BRW-IB');
    expect(byKey(lines, 'spo:alloc-1').location).toBe('MWH-IB');
    expect(byKey(lines, 'on-hand:wh-MWH-IB').location).toBe('MWH-IB');
  });

  it('AC-2 Customer is debtor_name, else debtor_code', () => {
    expect(byKey(lines, 'so:sol-1').customer).toBe('Customer B');
    expect(byKey(lines, 'so:sol-2').customer).toBe('DC-2');
  });

  it('AC-3 a blank debtor name with no code is no customer', () => {
    expect((byKey(lines, 'so:sol-3').customer ?? '').trim()).toBe('');
  });

  it('AC-2 Project is project_label trimmed; blank or null is none', () => {
    expect(byKey(lines, 'so:sol-1').project).toBe('Project 2');
    expect(byKey(lines, 'so:sol-2').project).toBe('Project 3');
    expect((byKey(lines, 'so:sol-3').project ?? '').trim()).toBe('');
    expect((byKey(lines, 'so:sol-4').project ?? '').trim()).toBe('');
  });

  it('AC-2 Agent is salesperson; a null salesperson is none', () => {
    expect(byKey(lines, 'so:sol-1').agent).toBe('Agent 1');
    expect(byKey(lines, 'so:sol-4').agent).toBe('Agent 2');
    expect(byKey(lines, 'so:sol-2').agent ?? '').toBe('');
  });

  it('AC-2 Supplier is supplier_name, else supplier_code, on PO and SPO lines', () => {
    expect(byKey(lines, 'po:pol-1').supplier).toBe('Supplier 1');
    expect(byKey(lines, 'po:pol-2').supplier).toBe('SUP-2');
    expect(byKey(lines, 'spo:alloc-1').supplier).toBe('Supplier 3');
  });

  it('AC-3 a type without a field has none: PO / SPO / On hand have no customer, project or agent; S/O and On hand no supplier', () => {
    for (const key of ['po:pol-1', 'spo:alloc-1', 'on-hand:wh-BRW-BB']) {
      const l = byKey(lines, key);
      expect(l.customer ?? '').toBe('');
      expect(l.project ?? '').toBe('');
      expect(l.agent ?? '').toBe('');
    }
    expect(byKey(lines, 'so:sol-1').supplier ?? '').toBe('');
    expect(byKey(lines, 'on-hand:wh-BRW-BB').supplier ?? '').toBe('');
  });

  it('AC-2 Type is On hand / S/O / PO / SPO', () => {
    expect(byKey(lines, 'so:sol-1').type).toBe('S/O');
    expect(byKey(lines, 'po:pol-1').type).toBe('PO');
    expect(byKey(lines, 'spo:alloc-1').type).toBe('SPO');
    expect(byKey(lines, 'on-hand:wh-BRW-BB').type).toBe('On hand');
  });

  it('AC-12 document numbers and links', () => {
    expect(byKey(lines, 'so:sol-1')).toMatchObject({ docNo: 'SO-0001', href: '/scm/sales-orders/soid-1' });
    expect(byKey(lines, 'po:pol-1')).toMatchObject({ docNo: 'PO-0001', href: '/scm/purchase-orders/poid-1' });
    expect(byKey(lines, 'spo:alloc-1')).toMatchObject({
      docNo: 'SPO-2026/08-0001',
      href: '/procurement-management/spo-allocations/SPO-2026%2F08-0001',
    });
    expect(byKey(lines, 'on-hand:wh-BRW-BB')).toMatchObject({ docNo: null, href: null, date: null });
  });

  it('AC-12 dates: S/O due_date, PO expected_date, SPO arrival_date; a missing one is null', () => {
    expect(byKey(lines, 'so:sol-1').date).toBe('2026-11-01');
    expect(byKey(lines, 'so:sol-3').date).toBeNull();
    expect(byKey(lines, 'po:pol-1').date).toBe('2026-12-01');
    expect(byKey(lines, 'po:pol-2').date).toBeNull();
    expect(byKey(lines, 'spo:alloc-1').date).toBe('2026-12-15');
  });
});

describe('stockLinesOf order (AC-5)', () => {
  it('AC-5 lines go by location (given order), then type On hand, S/O, SPO, PO, then the read\'s own order', () => {
    const lines = stockLinesOf(STATUS, ORDER);
    expect(lines.map((l) => l.key)).toEqual([
      'on-hand:wh-BRW-IB',
      'so:sol-3',
      'po:pol-2',
      'on-hand:wh-MWH-IB',
      'so:sol-4',
      'spo:alloc-1',
      'on-hand:wh-BRW-BB',
      'so:sol-1',
      'so:sol-2',
      'po:pol-1',
    ]);
  });

  it('AC-5 a different location order reorders the lines', () => {
    const lines = stockLinesOf(STATUS, ['BRW-BB', 'MWH-IB', 'BRW-IB']);
    expect(lines[0].location).toBe('BRW-BB');
    expect(lines[lines.length - 1].location).toBe('BRW-IB');
  });
});

describe('dimensions, options and measures', () => {
  const lines = stockLinesOf(STATUS, ORDER);
  const dims = stockGroupDimensions(ORDER);

  it('AC-15 the options are the six, in menu order', () => {
    expect(STOCK_GROUP_OPTIONS).toEqual([
      { id: 'location', label: 'Location' },
      { id: 'customer', label: 'Customer' },
      { id: 'project', label: 'Project' },
      { id: 'agent', label: 'Agent' },
      { id: 'supplier', label: 'Supplier' },
      { id: 'type', label: 'Type' },
    ]);
  });

  it('AC-3 each dimension has an id, a label and its "No ..." label', () => {
    expect(Object.keys(dims).sort()).toEqual(['agent', 'customer', 'location', 'project', 'supplier', 'type']);
    expect(dims.customer).toMatchObject({ id: 'customer', label: 'Customer', noneLabel: 'No customer' });
    expect(dims.project).toMatchObject({ id: 'project', label: 'Project', noneLabel: 'No project' });
    expect(dims.agent).toMatchObject({ id: 'agent', label: 'Agent', noneLabel: 'No agent' });
    expect(dims.supplier).toMatchObject({ id: 'supplier', label: 'Supplier', noneLabel: 'No supplier' });
    expect(dims.location).toMatchObject({ id: 'location', label: 'Location' });
    expect(dims.type).toMatchObject({ id: 'type', label: 'Type' });
  });

  it('AC-2 valueOf reads the line\'s own field; none is blank', () => {
    const l1 = byKey(lines, 'so:sol-1');
    expect(dims.location.valueOf(l1)).toBe('BRW-BB');
    expect(dims.customer.valueOf(l1)).toBe('Customer B');
    expect(dims.project.valueOf(l1)).toBe('Project 2');
    expect(dims.agent.valueOf(l1)).toBe('Agent 1');
    expect(dims.type.valueOf(l1)).toBe('S/O');
    expect((dims.supplier.valueOf(l1) ?? '').trim()).toBe('');
    expect((dims.customer.valueOf(byKey(lines, 'po:pol-1')) ?? '').trim()).toBe('');
    expect(dims.supplier.valueOf(byKey(lines, 'po:pol-1'))).toBe('Supplier 1');
  });

  it('AC-5 Location ranks by the given location order and Type by On hand, S/O, SPO, PO', () => {
    const rank = dims.location.rank;
    expect(rank).toBeTypeOf('function');
    expect(rank!('BRW-IB')).toBeLessThan(rank!('MWH-IB'));
    expect(rank!('MWH-IB')).toBeLessThan(rank!('BRW-BB'));
    const t = dims.type.rank;
    expect(t).toBeTypeOf('function');
    const ordered = ['On hand', 'S/O', 'SPO', 'PO'].map((x) => t!(x));
    expect([...ordered].sort((a, b) => a - b)).toEqual(ordered);
    expect(new Set(ordered).size).toBe(4);
  });

  it('AC-6 the measures read the four columns', () => {
    expect(Object.keys(STOCK_LINE_MEASURES).sort()).toEqual(['on-hand', 'po', 'so', 'spo']);
    const l = byKey(lines, 'so:sol-1');
    expect(STOCK_LINE_MEASURES.so(l)).toBe('144');
    expect(STOCK_LINE_MEASURES['on-hand'](l)).toBe('0');
    expect(STOCK_LINE_MEASURES.po(byKey(lines, 'po:pol-1'))).toBe('144');
    expect(STOCK_LINE_MEASURES.spo(byKey(lines, 'spo:alloc-1'))).toBe('50');
    expect(STOCK_LINE_MEASURES['on-hand'](byKey(lines, 'on-hand:wh-BRW-BB'))).toBe('17');
  });
});

function fakeStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: vi.fn((k: string) => (k in data ? data[k] : null)),
    setItem: vi.fn((k: string, v: string) => {
      data[k] = v;
    }),
    removeItem: vi.fn(),
  } as unknown as Storage & { data: Record<string, string> };
}

describe('remembered levels (AC-18, AC-19)', () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it('AC-18 the key and the default', () => {
    expect(STOCK_GROUP_STORAGE_KEY).toBe('cellStockTable.groupBy');
    expect([...DEFAULT_STOCK_GROUP_LEVELS]).toEqual(['location']);
  });

  it('AC-18 a saved list reads back in order', () => {
    const storage = fakeStorage({ [STOCK_GROUP_STORAGE_KEY]: JSON.stringify(['customer', 'project', 'location']) });
    expect(readStockGroupLevels(storage)).toEqual(['customer', 'project', 'location']);
  });

  it('AC-11 a saved empty list (no levels) reads back empty', () => {
    expect(readStockGroupLevels(fakeStorage({ [STOCK_GROUP_STORAGE_KEY]: '[]' }))).toEqual([]);
  });

  it('AC-18 write saves the JSON list under the key', () => {
    const storage = fakeStorage();
    writeStockGroupLevels(['agent', 'type'], storage);
    expect(storage.setItem).toHaveBeenCalledWith(STOCK_GROUP_STORAGE_KEY, JSON.stringify(['agent', 'type']));
    expect(readStockGroupLevels(storage)).toEqual(['agent', 'type']);
  });

  it('AC-18 with no storage given, the browser\'s localStorage is used both ways', () => {
    writeStockGroupLevels(['supplier']);
    expect(window.localStorage.getItem('cellStockTable.groupBy')).toBe(JSON.stringify(['supplier']));
    expect(readStockGroupLevels()).toEqual(['supplier']);
  });

  it('AC-19 a missing value falls back to Location', () => {
    expect(readStockGroupLevels(fakeStorage())).toEqual(['location']);
    expect(readStockGroupLevels()).toEqual(['location']);
  });

  it.each([
    ['invalid JSON', '{not json'],
    ['an unknown dimension', JSON.stringify(['customer', 'colour'])],
    ['a duplicate', JSON.stringify(['customer', 'customer'])],
    ['an object', JSON.stringify({ customer: 1 })],
    ['a string', JSON.stringify('customer')],
    ['a number', '3'],
    ['null', 'null'],
    ['a non-string entry', JSON.stringify(['customer', 2])],
  ])('AC-19 %s falls back to Location without throwing', (_name, raw) => {
    expect(readStockGroupLevels(fakeStorage({ [STOCK_GROUP_STORAGE_KEY]: raw }))).toEqual(['location']);
  });

  it('AC-19 a storage that throws on read falls back to Location', () => {
    const storage = { getItem: () => { throw new Error('denied'); }, setItem: () => {} } as unknown as Storage;
    expect(() => readStockGroupLevels(storage)).not.toThrow();
    expect(readStockGroupLevels(storage)).toEqual(['location']);
  });

  it('AC-19 a storage that throws on write does not throw', () => {
    const storage = { getItem: () => null, setItem: () => { throw new Error('full'); } } as unknown as Storage;
    expect(() => writeStockGroupLevels(['customer'], storage)).not.toThrow();
  });

  it('AC-19 a null storage reads Location and writes nothing', () => {
    expect(readStockGroupLevels(null)).toEqual(['location']);
    expect(() => writeStockGroupLevels(['customer'], null)).not.toThrow();
  });
});
