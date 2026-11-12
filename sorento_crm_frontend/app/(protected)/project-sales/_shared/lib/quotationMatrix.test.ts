/**
 * PS-QUOTE-MATRIX: the grid's numbers, the paste parser and the header edits. Examples E1 / E2 /
 * E3 are the card's (`CARD-ps-quote-matrix-02nov.md`), made-up rates in the workbook's shapes.
 */
import { describe, expect, it } from 'vitest';
import {
  addCol,
  addHeader,
  appendCopy,
  cellsUnder,
  duplicateHeader,
  hasPair,
  KEY_PATTERN,
  leafKeys,
  leaves,
  moveCol,
  moveHeader,
  newKey,
  parsePaste,
  removeKey,
  renameKey,
  reshapeCells,
  sumCells,
  summary,
  type MatrixHeader,
} from './quotationMatrix';

function typeHeader(key: string, label: string, bh: string): MatrixHeader {
  return {
    key,
    label,
    cols: [
      { key: `${key}-bh`, label: bh },
      { key: `${key}-kit`, label: 'Kitchen' },
      { key: `${key}-yard`, label: 'Yard' },
      { key: `${key}-bal`, label: 'Balcony' },
    ],
  };
}

function col(key: string, label: string) {
  return { key, label };
}

const UNIT: MatrixHeader[] = [
  typeHeader('a', 'Type A - 1 BH', '1 BH'),
  typeHeader('b', 'Type B - 2 BH', '2 BH'),
  typeHeader('c', 'Type C - 3 BH', '3 BH'),
];

const LEVEL9: MatrixHeader[] = [
  {
    key: 'l9',
    label: 'Level 9',
    cols: Array.from({ length: 11 }, (_, index) => ({ key: `l9-${index}`, label: `Room ${index}` })),
  },
  { key: 'la', label: 'Lobby A (Level 1)', cols: ['m', 'f', 'w', 'o'].map((k) => ({ key: `la-${k}`, label: k })) },
  { key: 'lb', label: 'Lobby B (Level 2)', cols: ['m', 'f', 'w', 'o'].map((k) => ({ key: `lb-${k}`, label: k })) },
  { key: 'bt', label: 'Break tank', cols: [] },
];

describe('leaves and pairs', () => {
  it('lists each header\'s columns, or the header itself when it has none', () => {
    expect(leafKeys(LEVEL9)).toHaveLength(11 + 4 + 4 + 1);
    expect(leafKeys(LEVEL9).at(-1)).toBe('bt');
    expect(leaves(LEVEL9).at(-1)).toMatchObject({ isHeader: true, headerLabel: 'Break tank' });
    expect(leafKeys(null)).toEqual([]);
    expect(leafKeys([])).toEqual([]);
  });

  it('gives a pair only to a header with 2+ columns in a scope with 2+ headers', () => {
    expect(LEVEL9.map((_, index) => hasPair(LEVEL9, index))).toEqual([true, true, true, false]);
    expect(hasPair([UNIT[0]], 0)).toBe(false);
    expect(hasPair([UNIT[0], { key: 'x', label: 'X', cols: [{ key: 'x1', label: 'one' }] }], 1)).toBe(false);
    expect(hasPair(null, 0)).toBe(false);
  });
});

describe('summary', () => {
  it('E1: floor trap at 45.00 sums per type and per row', () => {
    const result = summary(UNIT, [
      {
        unit_price: '45.00',
        qty_cells: { 'a-bh': '120', 'a-bal': '120', 'b-bh': '500', 'b-bal': '250', 'c-bh': '399', 'c-bal': '133' },
      },
    ]);
    const row = result.rows[0];
    expect(row.pairs.a).toEqual({ qty: '240.00', amount: '10800.00', blank: false });
    expect(row.pairs.b).toEqual({ qty: '750.00', amount: '33750.00', blank: false });
    expect(row.pairs.c).toEqual({ qty: '532.00', amount: '23940.00', blank: false });
    expect(row.totalQty).toBe('1522.00');
    expect(row.amount).toBe('68490.00');
  });

  it('E2: a type with every cell blank is a blank pair', () => {
    const result = summary(UNIT, [
      { unit_price: '180.00', qty_cells: { 'b-bh': '250', 'c-bh': '266' } },
    ]);
    expect(result.rows[0].pairs.a.blank).toBe(true);
    expect(result.rows[0].totalQty).toBe('516.00');
    expect(result.rows[0].amount).toBe('92880.00');
  });

  it('E3: Level 9 pairs, no pair for Break tank, and the footer per leaf, per pair and overall', () => {
    const cells = {
      'l9-3': '2', 'l9-4': '2', 'l9-7': '1', 'l9-9': '1', 'l9-10': '1',
      'la-f': '2', 'la-o': '1', 'lb-f': '2', 'lb-o': '1',
    };
    const result = summary(LEVEL9, [
      { unit_price: '600.00', qty_cells: cells },
      { unit_price: '95.00', qty_cells: { bt: '2' } },
    ]);
    expect(result.rows[0].pairs.l9).toEqual({ qty: '7.00', amount: '4200.00', blank: false });
    expect(result.rows[0].pairs.la).toEqual({ qty: '3.00', amount: '1800.00', blank: false });
    expect(result.rows[0].pairs.lb).toEqual({ qty: '3.00', amount: '1800.00', blank: false });
    expect(result.rows[0].pairs.bt).toBeUndefined();
    expect(result.rows[0].totalQty).toBe('13.00');
    expect(result.rows[0].amount).toBe('7800.00');

    expect(result.footer.leafQty['l9-3']).toBe('2.00');
    expect(result.footer.leafQty.bt).toBe('2.00');
    expect(result.footer.pairQty.l9).toBe('7.00');
    expect(result.footer.pairAmount.la).toBe('1800.00');
    expect(result.footer.totalQty).toBe('15.00');
    expect(result.footer.amount).toBe('7990.00');
  });

  it('a rate-only line prints its own figures with amount 0 and adds to no footer total', () => {
    const result = summary(UNIT, [
      { unit_price: '10.00', qty_cells: { 'a-bh': '5', 'a-kit': '5' }, is_rate_only: true },
      { unit_price: '10.00', qty_cells: { 'a-bh': '1' } },
    ]);
    expect(result.rows[0].totalQty).toBe('10.00');
    expect(result.rows[0].amount).toBe('0.00');
    expect(result.rows[0].pairs.a.amount).toBe('0.00');
    expect(result.footer.leafQty['a-bh']).toBe('1.00');
    expect(result.footer.totalQty).toBe('1.00');
    expect(result.footer.amount).toBe('10.00');
  });

  it('sums only valid, non-negative cells', () => {
    expect(sumCells({ a: '1.5', b: '', c: 'x', d: '-3', e: '2' })).toBe('3.50');
    expect(sumCells(null)).toBe('0.00');
    expect(sumCells({ a: '4', b: '6' }, ['b'])).toBe('6.00');
  });
});

describe('parsePaste', () => {
  it('fills right and down from the start cell; - and blanks paste as blank', () => {
    const result = parsePaste('120\t-\t\n1,250\t3.5\n', 2, 4);
    expect(result).toEqual({
      ok: true,
      cells: [
        { rowIndex: 4, leafIndex: 2, value: '120' },
        { rowIndex: 4, leafIndex: 3, value: '' },
        { rowIndex: 4, leafIndex: 4, value: '' },
        { rowIndex: 5, leafIndex: 2, value: '1250' },
        { rowIndex: 5, leafIndex: 3, value: '3.5' },
      ],
    });
  });

  it('refuses the whole paste and names the first bad cell', () => {
    const result = parsePaste('1\t2\n3\tabc\tdef', 0, 0);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain('"abc"');
      expect(result.error).toContain('row 2, column 2');
    }
  });

  it('refuses a negative number', () => {
    expect(parsePaste('-4', 0, 0).ok).toBe(false);
  });

  it('takes Windows line endings', () => {
    const result = parsePaste('1\r\n2\r\n', 0, 0);
    expect(result.ok && result.cells.map((cell) => cell.value)).toEqual(['1', '2']);
  });
});

describe('header edits', () => {
  it('mints keys the backend accepts, unique against the version', () => {
    const taken = new Set(['a', 'b']);
    for (let i = 0; i < 50; i += 1) {
      const key = newKey(taken);
      expect(key).toMatch(KEY_PATTERN);
      expect(taken.has(key)).toBe(false);
      taken.add(key);
    }
  });

  it('adds, renames, moves and removes headers and columns', () => {
    let headers = addHeader([], 'Level 9');
    const level = headers[0].key;
    headers = addCol(headers, level, 'Surau M');
    headers = addCol(headers, level, 'Surau F');
    headers = addHeader(headers, 'Break tank');
    expect(headers.map((header) => header.label)).toEqual(['Level 9', 'Break tank']);
    expect(headers[0].cols.map((col) => col.label)).toEqual(['Surau M', 'Surau F']);

    const [m, f] = headers[0].cols.map((col) => col.key);
    headers = renameKey(headers, m, '  Surau Men ');
    expect(headers[0].cols[0]).toEqual({ key: m, label: 'Surau Men' });
    expect(renameKey(headers, m, '   ')).toBe(headers);

    headers = moveCol(headers, f, m);
    expect(headers[0].cols.map((col) => col.key)).toEqual([f, m]);
    headers = moveHeader(headers, headers[1].key, level);
    expect(headers.map((header) => header.label)).toEqual(['Break tank', 'Level 9']);

    headers = removeKey(headers, f);
    expect(headers[1].cols.map((col) => col.key)).toEqual([m]);
    headers = removeKey(headers, level);
    expect(headers.map((header) => header.label)).toEqual(['Break tank']);
  });

  it('copies another scope\'s headers and columns with fresh keys, after its own', () => {
    const copied = appendCopy([{ key: 'own', label: 'Own', cols: [] }], UNIT);
    expect(copied.map((header) => header.label)).toEqual([
      'Own',
      'Type A - 1 BH',
      'Type B - 2 BH',
      'Type C - 3 BH',
    ]);
    const keys = leafKeys(copied);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys.some((key) => leafKeys(UNIT).includes(key))).toBe(false);
  });

  it('counts the lines a removal takes quantities from', () => {
    const lines: Array<Record<string, string> | null> = [{ 'a-bh': '1' }, { 'a-kit': '2' }, { 'b-bh': '3' }, null];
    expect(cellsUnder(UNIT, 'a', lines)).toBe(2);
    expect(cellsUnder(UNIT, 'b-bh', lines)).toBe(1);
  });
});

describe('reshapeCells (R12)', () => {
  it('moves the quantity into the first column ever added', () => {
    expect(reshapeCells([], UNIT, null, '12')).toEqual({ cells: { 'a-bh': '12' }, quantity: '12.00' });
  });

  it('puts the sum back when the last column goes', () => {
    expect(reshapeCells(UNIT, [], { 'a-bh': '2', 'c-bal': '3' }, '5.00')).toEqual({
      cells: null,
      quantity: '5.00',
    });
  });

  it('drops cells under removed columns and re-sums', () => {
    const after = removeKey(UNIT, 'a');
    expect(reshapeCells(UNIT, after, { 'a-bh': '2', 'c-bal': '3' }, '5.00')).toEqual({
      cells: { 'c-bal': '3' },
      quantity: '3.00',
    });
  });

  it('B1: a header that gains its first column moves its own quantity into it', () => {
    const before: MatrixHeader[] = [
      { key: 'bt', label: 'Break tank', cols: [] },
      { key: 'a', label: 'Type A', cols: [col('a1', 'Kitchen')] },
    ];
    const after: MatrixHeader[] = [
      { key: 'bt', label: 'Break tank', cols: [col('bt1', 'Column 1')] },
      { key: 'a', label: 'Type A', cols: [col('a1', 'Kitchen')] },
    ];
    expect(reshapeCells(before, after, { bt: '995', a1: '5' }, '1000.00')).toEqual({
      cells: { bt1: '995', a1: '5' },
      quantity: '1000.00',
    });
  });

  it('B1: the move never overwrites a value already in that first column', () => {
    const before: MatrixHeader[] = [
      { key: 'bt', label: 'Break tank', cols: [] },
      { key: 'a', label: 'Type A', cols: [] },
    ];
    const after: MatrixHeader[] = [
      { key: 'bt', label: 'Break tank', cols: [col('bt1', 'One')] },
      { key: 'a', label: 'Type A', cols: [] },
    ];
    expect(reshapeCells(before, after, { bt: '7', bt1: '3' }, '10.00').cells).toEqual({ bt1: '3' });
  });

  it('leaves a scope with no columns alone', () => {
    expect(reshapeCells(null, [], null, '7')).toEqual({ cells: null, quantity: '7' });
  });
});

describe('duplicateHeader (PROPOSAL-FORM-COLLAPSE, owner 10 Nov)', () => {
  const source: MatrixHeader[] = [
    { key: 'a', label: 'Type A - 1 BH', cols: [{ key: 'a1', label: '1 BH' }, { key: 'a2', label: 'KITCH' }] },
    { key: 'b', label: 'Type B', cols: [] },
  ];

  it('inserts a copy right after the group: same column names, fresh keys', () => {
    const next = duplicateHeader(source, 'a', 'Type A - 1 BH (copy)');
    expect(next.map((header) => header.label)).toEqual(['Type A - 1 BH', 'Type A - 1 BH (copy)', 'Type B']);
    const copy = next[1];
    expect(copy.cols.map((col) => col.label)).toEqual(['1 BH', 'KITCH']);
    const old = new Set(['a', 'a1', 'a2', 'b']);
    for (const key of [copy.key, ...copy.cols.map((col) => col.key)]) {
      expect(old.has(key)).toBe(false);
      expect(key).toMatch(KEY_PATTERN);
    }
    expect(new Set([copy.key, ...copy.cols.map((col) => col.key)]).size).toBe(3);
    // The source is untouched.
    expect(next[0]).toEqual(source[0]);
  });

  it('copies a header with no columns, and ignores an unknown key', () => {
    expect(duplicateHeader(source, 'b', 'Type B (copy)')[2]).toMatchObject({ label: 'Type B (copy)', cols: [] });
    expect(duplicateHeader(source, 'zz', 'x')).toBe(source);
  });
});
