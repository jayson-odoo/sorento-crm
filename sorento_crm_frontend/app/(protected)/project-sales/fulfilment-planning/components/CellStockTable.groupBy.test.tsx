/**
 * STOCK-GROUPBY S2 (red): the multi-level Group by on the stock table. UAC AC-6 to AC-14, AC-17
 * to AC-19, AC-21; contract `PLAN-stock-groupby-18oct.md` 5.3 and 5.4. Fixture is CKS4238-shaped
 * (BRW-BB on hand 17, Customer B 144 + 76 + 76 + 100), masked names only, with a 0.1 + 0.2 pair
 * on hand (set IB), one S/O line with a blank project and a null salesperson.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: vi.fn(() => new Promise(() => {})),
}));

import { CellStockTable } from './CellStockTable';
import type {
  BoardCellLocation,
  CellStockTableHandle,
} from '../../_shared/types/fulfilmentPlanning.types';
import type { StockStatus } from '@/components/stock-status/stockStatus.types';

const KEY = 'cellStockTable.groupBy';

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

/** Set IB (BRW-IB own, MWH-IB group); BRW-BB joins as "other group" from the read. */
const TODAY: BoardCellLocation[] = [
  row('BRW-IB', { where: 'own', net_of: 'IB', net: '-4.7' }),
  row('MWH-IB', { where: 'group', net_of: 'IB', net: '-4.7' }),
];

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

function so(n: string, warehouse: string, qty: number, extra: Record<string, unknown> = {}) {
  return {
    line_id: `sol-${n}`,
    sales_order_id: `soid-${n}`,
    so_number: `SO-000${n}`,
    debtor_code: `DC-${n}`,
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
    loc('BRW-IB', 0.2, { so_qty: 5 }),
    loc('MWH-IB', 0.1, { spo_qty: 50 }),
  ],
  totals: { on_hand: 17.3, so_qty: 401, po_qty: 144, spo_qty: 50, forecast: 0, incoming_pl: 20, forecast_incl_pl: 0 },
  incoming_pl: [
    { shipment_id: 'sh-1', shipment_number: 'PL-0001', container_number: null, eta: null, still_to_land: 20, on_spo: 0, counted: 20 },
  ],
  sales_orders: [
    so('1', 'BRW-BB', 144),
    // two lines of one SO, same group
    so('2', 'BRW-BB', 76, { line_id: 'sol-2', project_label: 'Project 3' }),
    so('2', 'BRW-BB', 76, { line_id: 'sol-3', project_label: 'Project 3' }),
    so('4', 'BRW-BB', 100, { line_id: 'sol-4', project_label: 'Project 3' }),
    // blank project, null salesperson, no due date
    so('5', 'BRW-IB', 5, { debtor_name: 'Customer A', project_label: '', salesperson: null, due_date: null }),
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

function renderTable(props: Partial<React.ComponentProps<typeof CellStockTable>> = {}, ref?: React.Ref<CellStockTableHandle>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <CellStockTable ref={ref} locations={TODAY} autoCount={STATUS} {...props} />
    </QueryClientProvider>,
  );
}

function levels(list: string[]) {
  window.localStorage.setItem(KEY, JSON.stringify(list));
}

const headers = () => [...screen.getByRole('table').querySelectorAll('thead th')].map((c) => c.textContent ?? '');
const rows = (re: RegExp) =>
  [...document.querySelectorAll('tr[data-testid]')].filter((tr) => re.test(tr.getAttribute('data-testid') ?? ''));
const ids = (list: Element[]) => list.map((el) => el.getAttribute('data-testid'));
const text = (id: string) => screen.queryByTestId(id)?.textContent ?? '';
const has = (id: string) => screen.queryByTestId(id) !== null;
const group = (key: string) => screen.getByTestId(`stock-group-${key}`);
const toggle = (key: string) => fireEvent.click(screen.getByTestId(`stock-group-toggle-${key}`));
const isOpen = (key: string) => screen.getByTestId(`stock-group-toggle-${key}`).getAttribute('aria-expanded') === 'true';
const lineRows = () => rows(/^stock-line-(on-hand|so|po|spo):/);
const lineKeys = () => lineRows().map((tr) => (tr.getAttribute('data-testid') ?? '').replace('stock-line-', ''));

function pick(optionId: string) {
  fireEvent.pointerDown(screen.getByTestId('group-by-trigger'), { button: 0 });
  return screen.findByTestId(`group-by-option-${optionId}`).then((el) => fireEvent.click(el));
}

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('AC-8 default: Location alone is today\'s table', () => {
  it('AC-8 / AC-15 shows the bar with a Location chip and no x, and no group rows', () => {
    renderTable();
    expect(screen.getByTestId('group-by-bar')).toBeInTheDocument();
    expect(screen.getByTestId('group-by-bar').className).toMatch(/flex-wrap/);
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Location');
    expect(has('group-by-chip-clear')).toBe(false);
    expect(rows(/^stock-group-/)).toHaveLength(0);
    expect(lineRows()).toHaveLength(0);
  });

  it('AC-8 keeps today\'s location rows, set subtotal, Total and Incoming PL row with today\'s figures', () => {
    renderTable();
    expect(ids(rows(/^cell-location-/))).toEqual(['cell-location-BRW-IB', 'cell-location-MWH-IB', 'cell-location-BRW-BB']);
    expect(has('stock-subtotal-IB')).toBe(true);
    expect(text('stock-so-BRW-BB')).toBe('396');
    expect(text('stock-on-hand-BRW-IB')).toBe('0.2');
    expect(text('stock-total-on-hand')).toBe('17.3');
    expect(text('stock-total-so')).toBe('401');
    expect(text('stock-total-po')).toBe('144');
    expect(text('stock-total-spo')).toBe('50');
    expect(screen.getByTestId('stock-incoming-pl')).toHaveTextContent('+20');
  });

  it('AC-8 a location row still opens the documents drill-down', () => {
    renderTable();
    expect(has('stock-expansion-BRW-BB')).toBe(false);
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    expect(has('stock-expansion-BRW-BB')).toBe(true);
  });

  it('AC-8 a set subtotal row still opens the set\'s documents drill-down', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-set-expand-IB'));
    expect(has('stock-set-expansion-IB')).toBe(true);
  });
});

describe('AC-9 Location first plus more levels', () => {
  beforeEach(() => levels(['location', 'customer', 'project']));

  it('AC-9 keeps today\'s rows, sets, subtotals, Total and Incoming PL with today\'s figures', () => {
    renderTable();
    expect(ids(rows(/^cell-location-/))).toEqual(['cell-location-BRW-IB', 'cell-location-MWH-IB', 'cell-location-BRW-BB']);
    expect(has('stock-subtotal-IB')).toBe(true);
    expect(text('stock-so-BRW-BB')).toBe('396');
    expect(text('stock-total-on-hand')).toBe('17.3');
    expect(text('stock-total-so')).toBe('401');
    expect(screen.getByTestId('stock-incoming-pl')).toHaveTextContent('+20');
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Location > Customer > Project');
    expect(has('group-by-chip-clear')).toBe(true);
  });

  it('AC-9 a location row opens its next-level groups, not the drill-down; groups start closed', () => {
    renderTable();
    expect(rows(/^stock-group-/)).toHaveLength(0);
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    expect(has('stock-expansion-BRW-BB')).toBe(false);
    expect(ids(rows(/^stock-group-location=BRW-BB\/[^/]*$/))).toEqual([
      'stock-group-location=BRW-BB/customer=Customer B',
      'stock-group-location=BRW-BB/customer=',
    ]);
    expect(isOpen('location=BRW-BB/customer=Customer B')).toBe(false);
    expect(has('stock-group-location=BRW-BB/customer=Customer B/project=Project 2')).toBe(false);
  });

  it('AC-6 group rows show the label, line count and the four sums', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    const b = group('location=BRW-BB/customer=Customer B');
    expect(b).toHaveTextContent('Customer B');
    expect(b).toHaveTextContent('4 lines');
    expect(text('stock-group-so-location=BRW-BB/customer=Customer B')).toBe('396');
    expect(text('stock-group-on-hand-location=BRW-BB/customer=Customer B')).toBe('0');
    const none = group('location=BRW-BB/customer=');
    expect(none).toHaveTextContent('No customer');
    expect(none).toHaveTextContent('2 lines');
    expect(text('stock-group-on-hand-location=BRW-BB/customer=')).toBe('17');
    expect(text('stock-group-po-location=BRW-BB/customer=')).toBe('144');
    expect(text('stock-group-spo-location=BRW-BB/customer=')).toBe('0');
  });

  it('AC-6 a group of one line says "1 line"', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    toggle('location=BRW-BB/customer=Customer B');
    const p2 = group('location=BRW-BB/customer=Customer B/project=Project 2');
    expect(p2.textContent).toMatch(/1 line(?!s)/);
    expect(text('stock-group-so-location=BRW-BB/customer=Customer B/project=Project 2')).toBe('144');
    expect(group('location=BRW-BB/customer=Customer B/project=Project 3')).toHaveTextContent('3 lines');
    expect(text('stock-group-so-location=BRW-BB/customer=Customer B/project=Project 3')).toBe('252');
  });

  it('AC-13 a group chevron opens and closes it and reports aria-expanded', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    const key = 'location=BRW-BB/customer=Customer B';
    expect(isOpen(key)).toBe(false);
    toggle(key);
    expect(isOpen(key)).toBe(true);
    expect(has(`stock-group-${key}/project=Project 2`)).toBe(true);
    toggle(key);
    expect(isOpen(key)).toBe(false);
    expect(has(`stock-group-${key}/project=Project 2`)).toBe(false);
  });

  it('AC-6 Available, Available for Project and Taken are blank on every group row', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    const cells = [...group('location=BRW-BB/customer=Customer B').querySelectorAll('td')];
    // chevron, label, On hand, SO qty, SPO qty, Available, Available for Project, PO qty, Taken
    expect(cells).toHaveLength(9);
    expect(cells[3].textContent).toBe('396');
    expect(cells[5].textContent).toBe('');
    expect(cells[6].textContent).toBe('');
    expect(cells[8].textContent).toBe('');
  });

  it('AC-9 a set subtotal row opens the next-level groups over every line of its set; no drill-down', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-set-expand-IB'));
    expect(has('stock-set-expansion-IB')).toBe(false);
    expect(ids(rows(/^stock-group-set=IB\/[^/]*$/))).toEqual([
      'stock-group-set=IB/customer=Customer A',
      'stock-group-set=IB/customer=',
    ]);
    expect(group('set=IB/customer=Customer A')).toHaveTextContent('1 line');
    expect(text('stock-group-so-set=IB/customer=Customer A')).toBe('5');
    expect(group('set=IB/customer=')).toHaveTextContent('3 lines');
    expect(text('stock-group-on-hand-set=IB/customer=')).toBe('0.3');
    expect(text('stock-group-spo-set=IB/customer=')).toBe('50');
  });

  it('AC-12 the last level opens its lines; quantity sits only in its own column', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    toggle('location=BRW-BB/customer=Customer B');
    toggle('location=BRW-BB/customer=Customer B/project=Project 3');
    expect(lineKeys()).toEqual(['so:sol-2', 'so:sol-3', 'so:sol-4']);
    expect(text('stock-line-so-so:sol-2')).toBe('76');
    expect(text('stock-line-so-so:sol-4')).toBe('100');
    expect(text('stock-line-on-hand-so:sol-2')).toBe('');
    expect(text('stock-line-spo-so:sol-2')).toBe('');
    expect(text('stock-line-po-so:sol-2')).toBe('');
  });

  it('AC-12 the muted line lists the values not already a level, and the due date', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    toggle('location=BRW-BB/customer=Customer B');
    toggle('location=BRW-BB/customer=Customer B/project=Project 2');
    const meta = screen.getByTestId('stock-line-meta-so:sol-1').textContent ?? '';
    expect(meta).toContain('Agent 1');
    expect(meta).toMatch(/due /);
    // Location, Customer and Project are levels already
    expect(meta).not.toContain('BRW-BB');
    expect(meta).not.toContain('Customer B');
    expect(meta).not.toContain('Project 2');
    expect(screen.getByRole('link', { name: 'SO-0001' })).toHaveAttribute('href', '/scm/sales-orders/soid-1');
  });
});

describe('AC-12 line links and meta, Type as the only level', () => {
  beforeEach(() => levels(['type']));

  it('AC-5 Type groups go On hand, S/O, SPO, PO, closed', () => {
    renderTable();
    expect(ids(rows(/^stock-group-type=/))).toEqual([
      'stock-group-type=On hand',
      'stock-group-type=S/O',
      'stock-group-type=SPO',
      'stock-group-type=PO',
    ]);
    expect(lineRows()).toHaveLength(0);
  });

  it('AC-12 S/O, PO and SPO document numbers link as the drill-down does', () => {
    renderTable();
    toggle('type=S/O');
    toggle('type=SPO');
    toggle('type=PO');
    expect(screen.getByRole('link', { name: 'SO-0001' })).toHaveAttribute('href', '/scm/sales-orders/soid-1');
    expect(screen.getByRole('link', { name: 'PO-0001' })).toHaveAttribute('href', '/scm/purchase-orders/poid-1');
    expect(screen.getByRole('link', { name: 'SPO-2026/08-0001' })).toHaveAttribute(
      'href',
      '/procurement-management/spo-allocations/SPO-2026%2F08-0001',
    );
  });

  it('AC-12 an On hand line shows its location code', () => {
    renderTable();
    toggle('type=On hand');
    expect(lineKeys()).toEqual(['on-hand:wh-BRW-IB', 'on-hand:wh-MWH-IB', 'on-hand:wh-BRW-BB']);
    expect(screen.getByTestId('stock-line-on-hand:wh-BRW-BB')).toHaveTextContent('BRW-BB');
    expect(text('stock-line-on-hand-on-hand:wh-BRW-BB')).toBe('17');
    expect(text('stock-line-so-on-hand:wh-BRW-BB')).toBe('');
  });

  it('AC-12 the muted line carries Location, Customer, Project, Agent and due; absent values are left out', () => {
    renderTable();
    toggle('type=S/O');
    const full = screen.getByTestId('stock-line-meta-so:sol-1').textContent ?? '';
    for (const v of ['BRW-BB', 'Customer B', 'Project 2', 'Agent 1']) expect(full).toContain(v);
    expect(full).toMatch(/due /);
    // blank project, null salesperson, no due date
    const sparse = screen.getByTestId('stock-line-meta-so:sol-5').textContent ?? '';
    expect(sparse).toContain('BRW-IB');
    expect(sparse).toContain('Customer A');
    expect(sparse).not.toMatch(/null|undefined|Agent|due/);
  });

  it('AC-12 a PO line carries its supplier and "expected <date>"; an SPO line likewise', () => {
    renderTable();
    toggle('type=SPO');
    toggle('type=PO');
    const po = screen.getByTestId('stock-line-meta-po:pol-1').textContent ?? '';
    expect(po).toContain('Supplier 1');
    expect(po).toContain('BRW-BB');
    expect(po).toMatch(/expected /);
    const spo = screen.getByTestId('stock-line-meta-spo:alloc-1').textContent ?? '';
    expect(spo).toContain('Supplier 3');
    expect(spo).toContain('MWH-IB');
    expect(spo).toMatch(/expected /);
    expect(text('stock-line-po-po:pol-1')).toBe('144');
    expect(text('stock-line-spo-spo:alloc-1')).toBe('50');
  });
});

describe('AC-10 Location not first', () => {
  beforeEach(() => levels(['customer', 'project']));

  it('AC-10 the body is the first level\'s groups; the first column is headed Customer', () => {
    renderTable();
    expect(headers()).toContain('Customer');
    expect(headers()).not.toContain('Location');
    expect(ids(rows(/^stock-group-customer=[^/]*$/))).toEqual([
      'stock-group-customer=Customer A',
      'stock-group-customer=Customer B',
      'stock-group-customer=',
    ]);
    expect(group('customer=')).toHaveTextContent('No customer');
    expect(rows(/^cell-location-/)).toHaveLength(0);
    expect(rows(/^stock-subtotal-/)).toHaveLength(0);
    expect(has('stock-set-expand-IB')).toBe(false);
  });

  it('AC-10 the Total row and the Incoming PL row stay with today\'s figures', () => {
    renderTable();
    expect(text('stock-total-on-hand')).toBe('17.3');
    expect(text('stock-total-so')).toBe('401');
    expect(text('stock-total-po')).toBe('144');
    expect(text('stock-total-spo')).toBe('50');
    expect(screen.getByTestId('stock-incoming-pl')).toHaveTextContent('+20');
  });

  it('AC-7 the top-level group sums equal the Total row', () => {
    renderTable();
    const top = rows(/^stock-group-customer=[^/]*$/).map((tr) => tr.getAttribute('data-testid')!.replace('stock-group-', ''));
    const sum = (col: string) => top.reduce((t, k) => t + Number(text(`stock-group-${col}-${k}`)), 0);
    expect(sum('so')).toBe(Number(text('stock-total-so')));
    expect(sum('po')).toBe(Number(text('stock-total-po')));
    expect(sum('spo')).toBe(Number(text('stock-total-spo')));
    expect(sum('on-hand')).toBeCloseTo(Number(text('stock-total-on-hand')), 6);
    expect(text('stock-group-on-hand-customer=')).toBe('17.3');
  });

  it('AC-10 the second level hangs off the first with the engine\'s own keys', () => {
    renderTable();
    toggle('customer=Customer B');
    expect(ids(rows(/^stock-group-customer=Customer B\/[^/]*$/))).toEqual([
      'stock-group-customer=Customer B/project=Project 2',
      'stock-group-customer=Customer B/project=Project 3',
    ]);
  });

  it('AC-10 Location further down gives plain location groups', () => {
    levels(['customer', 'location']);
    renderTable();
    toggle('customer=Customer B');
    expect(ids(rows(/^stock-group-customer=Customer B\/[^/]*$/))).toEqual(['stock-group-customer=Customer B/location=BRW-BB']);
    expect(group('customer=Customer B/location=BRW-BB')).toHaveTextContent('4 lines');
  });

  it('AC-3 a blank project goes to No project, last', () => {
    renderTable();
    toggle('customer=Customer A');
    expect(group('customer=Customer A/project=')).toHaveTextContent('No project');
  });
});

describe('AC-11 no levels', () => {
  beforeEach(() => levels([]));

  it('AC-11 lists every line flat in order, with Total and Incoming PL; the chip reads none', () => {
    renderTable();
    expect(rows(/^stock-group-/)).toHaveLength(0);
    expect(lineKeys()).toEqual([
      'on-hand:wh-BRW-IB',
      'so:sol-5',
      'on-hand:wh-MWH-IB',
      'spo:alloc-1',
      'on-hand:wh-BRW-BB',
      'so:sol-1',
      'so:sol-2',
      'so:sol-3',
      'so:sol-4',
      'po:pol-1',
    ]);
    expect(text('stock-total-on-hand')).toBe('17.3');
    expect(screen.getByTestId('stock-incoming-pl')).toHaveTextContent('+20');
    expect(screen.getByTestId('group-by-chip').textContent).toMatch(/none/);
    expect(rows(/^cell-location-/)).toHaveLength(0);
  });

  it('AC-12 a flat line carries every value in its muted line', () => {
    renderTable();
    const meta = screen.getByTestId('stock-line-meta-so:sol-1').textContent ?? '';
    for (const v of ['BRW-BB', 'Customer B', 'Project 2', 'Agent 1']) expect(meta).toContain(v);
  });
});

describe('AC-13 Expand all / Collapse all', () => {
  it('AC-13 Expand all opens every group at every level, down to the lines; Collapse all closes them', () => {
    levels(['customer', 'project']);
    renderTable();
    expect(lineRows()).toHaveLength(0);
    fireEvent.click(screen.getByTestId('group-by-expand-all'));
    expect(lineRows()).toHaveLength(10);
    expect(isOpen('customer=Customer B')).toBe(true);
    expect(isOpen('customer=Customer B/project=Project 3')).toBe(true);
    fireEvent.click(screen.getByTestId('group-by-collapse-all'));
    expect(lineRows()).toHaveLength(0);
    expect(has('stock-group-customer=Customer B/project=Project 3')).toBe(false);
    expect(isOpen('customer=Customer B')).toBe(false);
  });

  it('AC-13 Location first: Expand all also opens every location row into its groups', () => {
    levels(['location', 'customer']);
    renderTable();
    fireEvent.click(screen.getByTestId('group-by-expand-all'));
    expect(has('stock-group-location=BRW-BB/customer=Customer B')).toBe(true);
    expect(has('stock-group-location=BRW-IB/customer=Customer A')).toBe(true);
    expect(lineKeys()).toContain('so:sol-1');
    expect(has('stock-expansion-BRW-BB')).toBe(false);
    fireEvent.click(screen.getByTestId('group-by-collapse-all'));
    expect(rows(/^stock-group-/)).toHaveLength(0);
    expect(lineRows()).toHaveLength(0);
  });
});

describe('AC-14 negative sums', () => {
  it('AC-14 a negative group sum is signed and carries the class a negative Available has today', () => {
    levels(['location', 'type']);
    const neg = { ...STATUS, locations: [loc('NEG-1', -3)], totals: { ...STATUS.totals }, sales_orders: [], purchase_orders: [], spos: [] } as unknown as StockStatus;
    renderTable({ locations: [row('NEG-1')], autoCount: neg });
    fireEvent.click(screen.getByTestId('stock-expand-NEG-1'));
    const sum = screen.getByTestId('stock-group-on-hand-location=NEG-1/type=On hand');
    expect(sum.textContent).toBe('-3');
    // today's negative style: CellStockTable puts text-destructive on a negative Available
    expect(screen.getByTestId('stock-available-NEG-1')).toHaveClass('text-destructive');
    expect(sum).toHaveClass('text-destructive');
  });
});

describe('AC-17 no bar without the read', () => {
  it('AC-17 without autoCount there is no bar and today\'s table, whatever is saved', () => {
    levels(['customer']);
    renderTable({ autoCount: null });
    expect(has('group-by-bar')).toBe(false);
    expect(rows(/^stock-group-/)).toHaveLength(0);
    expect(ids(rows(/^cell-location-/))).toEqual(['cell-location-BRW-IB', 'cell-location-MWH-IB']);
  });
});

describe('AC-16 / AC-18 / AC-19 the menu drives and remembers the levels', () => {
  it('AC-18 saved levels are read on mount', () => {
    levels(['agent', 'customer']);
    renderTable();
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Agent > Customer');
    expect(headers()).toContain('Agent');
  });

  it('AC-16 / AC-18 picking a dimension appends a level and saves the list', async () => {
    renderTable();
    await pick('customer');
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Location > Customer');
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? 'null')).toEqual(['location', 'customer']);
    // Location first plus a level: the location row opens groups now
    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    expect(has('stock-group-location=BRW-BB/customer=Customer B')).toBe(true);
  });

  it('AC-16 unticking Location makes the body the first remaining level', async () => {
    levels(['location', 'customer']);
    renderTable();
    await pick('location');
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? 'null')).toEqual(['customer']);
    expect(headers()).toContain('Customer');
    expect(rows(/^cell-location-/)).toHaveLength(0);
  });

  it('AC-16 the chip x sets the levels back to Location and saves it', () => {
    levels(['customer', 'project']);
    renderTable();
    fireEvent.click(screen.getByTestId('group-by-chip-clear'));
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? 'null')).toEqual(['location']);
    expect(rows(/^cell-location-/)).toHaveLength(3);
    expect(has('group-by-chip-clear')).toBe(false);
  });

  it('AC-19 a saved value that is invalid falls back to Location with no error on screen', () => {
    for (const raw of ['{not json', JSON.stringify(['customer', 'customer']), JSON.stringify(['colour']), '{"a":1}']) {
      window.localStorage.setItem(KEY, raw);
      const { unmount } = renderTable();
      expect(rows(/^cell-location-/)).toHaveLength(3);
      expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Location');
      expect(has('group-by-chip-clear')).toBe(false);
      unmount();
    }
  });

  it('AC-19 a storage that throws falls back to Location and still renders', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('full');
    });
    renderTable();
    expect(rows(/^cell-location-/)).toHaveLength(3);
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Location');
  });

  it('AC-18 a second table with the read starts from the saved choice', async () => {
    const first = renderTable();
    await pick('project');
    first.unmount();
    renderTable();
    expect(screen.getByTestId('group-by-chip')).toHaveTextContent('Location > Project');
  });
});

describe('AC-21 the dialog search over grouped lines', () => {
  beforeEach(() => levels(['customer', 'project']));

  it('AC-21 a document number narrows the lines (case-insensitive) and opens the groups holding a match; sums stay', () => {
    renderTable({ filterText: 'so-0002' });
    expect(isOpen('customer=Customer B')).toBe(true);
    expect(isOpen('customer=Customer B/project=Project 3')).toBe(true);
    expect(lineKeys()).toEqual(['so:sol-2', 'so:sol-3']);
    // figures and counts do not follow the search
    expect(group('customer=Customer B/project=Project 3')).toHaveTextContent('3 lines');
    expect(text('stock-group-so-customer=Customer B/project=Project 3')).toBe('252');
    expect(text('stock-group-so-customer=Customer B')).toBe('396');
    expect(isOpen('customer=Customer A')).toBe(false);
  });

  it('AC-21 the agent matches too', () => {
    renderTable({ filterText: 'AGENT 1' });
    expect(lineKeys()).toEqual(['so:sol-1', 'so:sol-2', 'so:sol-3', 'so:sol-4']);
    expect(isOpen('customer=Customer A')).toBe(false);
  });

  it('AC-21 the customer matches (Customer A\'s line only)', () => {
    renderTable({ filterText: 'customer a' });
    expect(lineKeys()).toEqual(['so:sol-5']);
    expect(isOpen('customer=Customer A')).toBe(true);
    expect(isOpen('customer=Customer B')).toBe(false);
  });

  it('AC-21 the supplier matches', () => {
    levels(['supplier']);
    renderTable({ filterText: 'supplier 1' });
    expect(lineKeys()).toEqual(['po:pol-1']);
    expect(isOpen('supplier=Supplier 1')).toBe(true);
    expect(isOpen('supplier=Supplier 3')).toBe(false);
  });

  it('AC-21 Location first: the location row holding a match opens', () => {
    levels(['location', 'customer']);
    renderTable({ filterText: 'SO-0001' });
    expect(has('stock-group-location=BRW-BB/customer=Customer B')).toBe(true);
    expect(isOpen('location=BRW-BB/customer=Customer B')).toBe(true);
    expect(lineKeys()).toEqual(['so:sol-1']);
  });

  it('AC-21 no search leaves every group closed', () => {
    renderTable({ filterText: '' });
    expect(lineRows()).toHaveLength(0);
    expect(isOpen('customer=Customer B')).toBe(false);
  });
});

describe('AC-21 jumps open the groups holding the target location\'s lines', () => {
  it('AC-21 Location first: a donor jump opens the location row, its groups and its lines', () => {
    levels(['location', 'customer', 'project']);
    const ref = React.createRef<CellStockTableHandle>();
    renderTable({}, ref);
    expect(lineRows()).toHaveLength(0);
    act(() => ref.current!.jumpToDonor({ soNumber: 'SO-0001', location: 'BRW-BB' }));
    expect(lineKeys()).toEqual(expect.arrayContaining(['so:sol-1', 'so:sol-2', 'so:sol-3', 'so:sol-4', 'on-hand:wh-BRW-BB', 'po:pol-1']));
    expect(lineKeys()).not.toContain('so:sol-5');
    expect(has('stock-expansion-BRW-BB')).toBe(false);
  });

  it('AC-21 a document jump to MWH-IB opens its lines', () => {
    levels(['location', 'customer']);
    const ref = React.createRef<CellStockTableHandle>();
    renderTable({}, ref);
    act(() => ref.current!.jumpToDocument({ spoNumber: 'SPO-2026/08-0001', location: 'MWH-IB' }));
    expect(lineKeys()).toEqual(expect.arrayContaining(['spo:alloc-1', 'on-hand:wh-MWH-IB']));
  });

  it('AC-21 "My line" opens the own location\'s lines', () => {
    levels(['location', 'customer']);
    const ref = React.createRef<CellStockTableHandle>();
    renderTable({}, ref);
    act(() => ref.current!.jumpToThisLine());
    expect(lineKeys()).toEqual(expect.arrayContaining(['so:sol-5', 'on-hand:wh-BRW-IB']));
  });

  it('AC-21 Location not first: a jump opens every group holding a line of the target location', () => {
    levels(['customer', 'project']);
    const ref = React.createRef<CellStockTableHandle>();
    renderTable({}, ref);
    act(() => ref.current!.jumpToDonor({ soNumber: 'SO-0001', location: 'BRW-BB' }));
    expect(isOpen('customer=Customer B')).toBe(true);
    expect(isOpen('customer=Customer B/project=Project 2')).toBe(true);
    expect(isOpen('customer=Customer B/project=Project 3')).toBe(true);
    expect(isOpen('customer=')).toBe(true);
    expect(lineKeys()).toEqual(expect.arrayContaining(['so:sol-1', 'so:sol-4', 'on-hand:wh-BRW-BB', 'po:pol-1']));
    expect(lineKeys()).not.toContain('so:sol-5');
    expect(isOpen('customer=Customer A')).toBe(false);
  });

  it('AC-8 with Location alone a jump still opens the documents drill-down', () => {
    const ref = React.createRef<CellStockTableHandle>();
    renderTable({}, ref);
    act(() => ref.current!.jumpToDonor({ soNumber: 'SO-0001', location: 'BRW-BB' }));
    expect(has('stock-expansion-BRW-BB')).toBe(true);
    expect(lineRows()).toHaveLength(0);
  });
});

