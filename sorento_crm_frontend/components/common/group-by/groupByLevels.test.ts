/**
 * STOCK-GROUPBY S1 (red): the pure grouping. Contract `PLAN-stock-groupby-18oct.md` 5.1,
 * UAC `stock-groupby-18oct-acceptance-criteria.md` AC-3 to AC-7, AC-11. Masked names only.
 */
import { describe, expect, it } from 'vitest';

import {
  groupByLevels,
  type GroupDimension,
  type GroupNode,
  type Measure,
} from './groupByLevels';

interface Row {
  id: string;
  location: string;
  customer: string | null;
  project: string | null;
  type: 'On hand' | 'S/O' | 'SPO' | 'PO';
  so: string | number | null;
  onHand?: string | number | null;
}

/** Unknown values rank last (ties fall back to A to Z). */
const rankIn = (order: string[]) => (v: string) => (order.includes(v) ? order.indexOf(v) : Number.POSITIVE_INFINITY);
const TYPE_ORDER = ['On hand', 'S/O', 'SPO', 'PO'];
const LOCATION_ORDER = ['BRW-IB', 'MWH-IB', 'BRW-BB'];

const location: GroupDimension<Row> = {
  id: 'location',
  label: 'Location',
  noneLabel: 'No location',
  valueOf: (r) => r.location,
  rank: rankIn(LOCATION_ORDER),
};
const customer: GroupDimension<Row> = {
  id: 'customer',
  label: 'Customer',
  noneLabel: 'No customer',
  valueOf: (r) => r.customer,
};
const project: GroupDimension<Row> = {
  id: 'project',
  label: 'Project',
  noneLabel: 'No project',
  valueOf: (r) => r.project,
};
const type: GroupDimension<Row> = {
  id: 'type',
  label: 'Type',
  noneLabel: 'No type',
  valueOf: (r) => r.type,
  rank: rankIn(TYPE_ORDER),
};

const MEASURES: Record<string, Measure<Row>> = {
  so: (r) => r.so,
  onHand: (r) => r.onHand,
};

let n = 0;
function line(extra: Partial<Row> & Pick<Row, 'location' | 'customer' | 'project'>): Row {
  n += 1;
  return { id: `l${n}`, type: 'S/O', so: 0, onHand: 0, ...extra };
}

/** CKS4238-shaped: BRW-BB holds Customer B 144 + 76 + 76 + 100 = 396, plus on hand 17 and a PO. */
function cks(): Row[] {
  return [
    line({ location: 'BRW-BB', customer: 'Customer B', project: 'Project 2', so: 144 }),
    line({ location: 'BRW-BB', customer: 'Customer B', project: 'Project 3', so: 76 }),
    line({ location: 'BRW-BB', customer: 'Customer B', project: 'Project 3', so: 76 }),
    line({ location: 'BRW-BB', customer: 'Customer B', project: 'Project 3', so: 100 }),
    line({ location: 'BRW-BB', customer: null, project: null, type: 'On hand', so: 0, onHand: 17 }),
    line({ location: 'BRW-BB', customer: null, project: null, type: 'PO', so: 0, onHand: 0 }),
    line({ location: 'BRW-IB', customer: 'Customer A', project: 'Project 1', so: 2 }),
    line({ location: 'BRW-IB', customer: 'Customer C', project: '   ', so: 330 }),
    line({ location: 'BRW-IB', customer: 'Customer D', project: '', so: 1 }),
  ];
}

const labels = (nodes: GroupNode<Row>[]) => nodes.map((x) => x.label);
const find = (nodes: GroupNode<Row>[], label: string) => {
  const hit = nodes.find((x) => x.label === label);
  if (!hit) throw new Error(`no group ${label} in ${labels(nodes).join(', ')}`);
  return hit;
};

describe('groupByLevels (AC-4, AC-11)', () => {
  it('AC-11 no levels gives no groups', () => {
    expect(groupByLevels(cks(), [], MEASURES)).toEqual([]);
  });

  it('AC-4 one level splits the lines and a group exists only when it holds a line', () => {
    const tree = groupByLevels(cks(), [location], MEASURES);
    expect(labels(tree)).toEqual(['BRW-IB', 'BRW-BB']);
    for (const g of tree) {
      expect(g.children).toEqual([]);
      expect(g.depth).toBe(0);
      expect(g.dimension).toBe('location');
      expect(g.isNone).toBe(false);
    }
    expect(tree[1].key).toBe('location=BRW-BB');
    expect(tree[1].lines).toHaveLength(6);
  });

  it('AC-4 three levels: Location > Customer > Project carries path keys and depth', () => {
    const tree = groupByLevels(cks(), [location, customer, project], MEASURES);
    const bb = find(tree, 'BRW-BB');
    expect(labels(bb.children)).toEqual(['Customer B', 'No customer']);
    const custB = find(bb.children, 'Customer B');
    expect(custB.key).toBe('location=BRW-BB/customer=Customer B');
    expect(custB.depth).toBe(1);
    expect(custB.dimension).toBe('customer');
    expect(labels(custB.children)).toEqual(['Project 2', 'Project 3']);
    const p3 = find(custB.children, 'Project 3');
    expect(p3.key).toBe('location=BRW-BB/customer=Customer B/project=Project 3');
    expect(p3.depth).toBe(2);
    expect(p3.count).toBe(3);
    expect(p3.sums.so).toBe('252');
    expect(p3.children).toEqual([]);
    expect(p3.lines).toHaveLength(3);
    expect(find(custB.children, 'Project 2').sums.so).toBe('144');
  });

  it('AC-3 empty, whitespace and null values go to the none group, last, with an empty-value key', () => {
    const tree = groupByLevels(cks(), [customer], MEASURES);
    expect(labels(tree)).toEqual(['Customer A', 'Customer B', 'Customer C', 'Customer D', 'No customer']);
    const none = tree[tree.length - 1];
    expect(none.isNone).toBe(true);
    expect(none.key).toBe('customer=');
    expect(none.count).toBe(2);
    const byProject = groupByLevels(cks(), [project], MEASURES);
    const noProject = byProject[byProject.length - 1];
    expect(noProject.label).toBe('No project');
    expect(noProject.key).toBe('project=');
    expect(noProject.count).toBe(4);
  });

  it('AC-3 a value is trimmed, so padded spellings share one group', () => {
    const rows = [
      line({ location: 'BRW-BB', customer: ' Customer B ', project: null }),
      line({ location: 'BRW-BB', customer: 'Customer B', project: null }),
    ];
    const tree = groupByLevels(rows, [customer], MEASURES);
    expect(tree).toHaveLength(1);
    expect(tree[0].label).toBe('Customer B');
    expect(tree[0].count).toBe(2);
  });

  it('AC-5 unranked dimensions go A to Z case-insensitive, none last', () => {
    const rows = ['cherry', 'Banana', 'apple', null, 'Avocado'].map((c) =>
      line({ location: 'BRW-BB', customer: c, project: null }),
    );
    expect(labels(groupByLevels(rows, [customer], MEASURES))).toEqual([
      'apple',
      'Avocado',
      'Banana',
      'cherry',
      'No customer',
    ]);
  });

  it('AC-5 a ranked dimension follows its rank: Type is On hand, S/O, SPO, PO', () => {
    const rows = (['PO', 'SPO', 'S/O', 'On hand'] as const).map((t) =>
      line({ location: 'BRW-BB', customer: null, project: null, type: t }),
    );
    expect(labels(groupByLevels(rows, [type], MEASURES))).toEqual(['On hand', 'S/O', 'SPO', 'PO']);
  });

  it('AC-5 Location follows the given location order, not A to Z', () => {
    const tree = groupByLevels(cks(), [location], MEASURES);
    expect(labels(tree)).toEqual(['BRW-IB', 'BRW-BB']);
    const flipped = groupByLevels(cks(), [{ ...location, rank: rankIn(['BRW-BB', 'BRW-IB']) }], MEASURES);
    expect(labels(flipped)).toEqual(['BRW-BB', 'BRW-IB']);
  });

  it('AC-5 unranked values come after ranked ones, A to Z, before none', () => {
    const rows = [
      line({ location: 'ZZZ-1', customer: null, project: null }),
      line({ location: 'AAA-1', customer: null, project: null }),
      line({ location: 'MWH-IB', customer: null, project: null }),
      line({ location: '', customer: null, project: null }),
    ];
    expect(labels(groupByLevels(rows, [location], MEASURES))).toEqual(['MWH-IB', 'AAA-1', 'ZZZ-1', 'No location']);
  });

  it('AC-6 the count is the number of lines beneath, at every level', () => {
    const tree = groupByLevels(cks(), [customer, project], MEASURES);
    const b = find(tree, 'Customer B');
    expect(b.count).toBe(4);
    expect(b.children.reduce((total, c) => total + c.count, 0)).toBe(4);
    expect(find(tree, 'No customer').count).toBe(2);
  });

  it('AC-6 sums are exact decimals, no float drift', () => {
    const rows = [
      line({ location: 'BRW-BB', customer: 'Customer A', project: null, so: 0.1, onHand: 0.1 }),
      line({ location: 'BRW-BB', customer: 'Customer A', project: null, so: 0.2, onHand: '0.2' }),
    ];
    const [g] = groupByLevels(rows, [customer], MEASURES);
    expect(0.1 + 0.2).not.toBe(0.3);
    expect(g.sums.so).toBe('0.3');
    expect(g.sums.onHand).toBe('0.3');
  });

  it('AC-14 negative sums are signed strings', () => {
    const rows = [
      line({ location: 'BRW-BB', customer: 'Customer A', project: null, so: -5 }),
      line({ location: 'BRW-BB', customer: 'Customer A', project: null, so: 3 }),
    ];
    expect(groupByLevels(rows, [customer], MEASURES)[0].sums.so).toBe('-2');
  });

  it('AC-6 a null, undefined or blank measure counts as zero and every measure id is present', () => {
    const rows = [
      line({ location: 'BRW-BB', customer: 'Customer A', project: null, so: null, onHand: undefined }),
      line({ location: 'BRW-BB', customer: 'Customer A', project: null, so: '', onHand: 4 }),
    ];
    const [g] = groupByLevels(rows, [customer], MEASURES);
    expect(g.sums).toEqual({ so: '0', onHand: '4' });
  });

  it('AC-4 lines inside a group keep input order', () => {
    const rows = cks();
    const tree = groupByLevels(rows, [customer], MEASURES);
    const b = find(tree, 'Customer B');
    expect(b.lines.map((l) => l.id)).toEqual(rows.filter((r) => r.customer === 'Customer B').map((r) => r.id));
  });

  it('AC-7 for every ordering of the levels, top-level sums equal the totals', () => {
    const rows = cks();
    const total = (key: 'so' | 'onHand') => rows.reduce((t, r) => t + Number(r[key] ?? 0), 0);
    const all = [location, customer, project, type];
    const orders: GroupDimension<Row>[][] = [
      [location],
      [customer],
      [project],
      [type],
      [location, customer, project],
      [customer, project],
      [project, customer, location],
      [type, location],
      all,
    ];
    for (const levels of orders) {
      const tree = groupByLevels(rows, levels, MEASURES);
      const sum = (key: string) => tree.reduce((t, g) => t + Number(g.sums[key]), 0);
      expect(sum('so'), levels.map((l) => l.id).join('>')).toBe(total('so'));
      expect(sum('onHand'), levels.map((l) => l.id).join('>')).toBe(total('onHand'));
      expect(tree.reduce((t, g) => t + g.count, 0)).toBe(rows.length);
    }
  });

  it('AC-7 a parent sum equals the sum of its children', () => {
    const tree = groupByLevels(cks(), [location, customer, project], MEASURES);
    const walk = (nodes: GroupNode<Row>[]) => {
      for (const g of nodes) {
        if (g.children.length === 0) continue;
        expect(g.children.reduce((t, c) => t + Number(c.sums.so), 0)).toBe(Number(g.sums.so));
        walk(g.children);
      }
    };
    walk(tree);
  });
});
