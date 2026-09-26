/**
 * S3-3: findings with the same code about the same subject collapse into one row with a
 * count. Subject key, first present wins: line_id, then detail_json.customer_code_raw,
 * then detail_json.product_code, then detail_json.line_no. A finding with none of these
 * keys never collapses.
 */
import { describe, expect, it } from 'vitest';
import {
  buildFlagItems,
  collapseFindings,
  FINDING_SEVERITY_LABEL,
  leadFlagItem,
  needsAttention,
  publishBlockers,
} from './findings';
import type { ProjectSalesOrderFinding } from '../types/projectSalesOrder.types';

function finding(overrides: Partial<ProjectSalesOrderFinding> & { id: string }): ProjectSalesOrderFinding {
  return {
    severity: 'warn',
    code: 'price_vs_quotation',
    detail: 'A finding.',
    line_id: null,
    line_no: null,
    ...overrides,
  };
}

describe('collapseFindings', () => {
  it('collapses same code + same line_id into one row with a count', () => {
    const rows = collapseFindings([
      finding({ id: 'f1', code: 'no_package_mapping', line_id: 'line-1' }),
      finding({ id: 'f2', code: 'no_package_mapping', line_id: 'line-1' }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].ids).toEqual(['f1', 'f2']);
    expect(rows[0].count).toBe(2);
  });

  it('does not collapse the same code across different line_ids', () => {
    const rows = collapseFindings([
      finding({ id: 'f1', code: 'no_package_mapping', line_id: 'line-1' }),
      finding({ id: 'f2', code: 'no_package_mapping', line_id: 'line-2' }),
    ]);
    expect(rows).toHaveLength(2);
  });

  it('does not collapse different codes about the same line', () => {
    const rows = collapseFindings([
      finding({ id: 'f1', code: 'no_package_mapping', line_id: 'line-1' }),
      finding({ id: 'f2', code: 'price_vs_quotation', line_id: 'line-1' }),
    ]);
    expect(rows).toHaveLength(2);
  });

  it('falls back to detail_json.customer_code_raw when line_id is absent (schedule column)', () => {
    const rows = collapseFindings([
      finding({
        id: 'f1',
        code: 'schedule_short',
        line_id: null,
        detail_json: { customer_code_raw: 'BUI-HB-C-FH12' },
      }),
      finding({
        id: 'f2',
        code: 'schedule_short',
        line_id: null,
        detail_json: { customer_code_raw: 'BUI-HB-C-FH12' },
      }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].ids).toEqual(['f1', 'f2']);
  });

  it('keeps one row per area: same code, different customer_code_raw never collapse', () => {
    const rows = collapseFindings([
      finding({
        id: 'f1',
        code: 'unresolved_product',
        line_id: null,
        detail_json: { customer_code_raw: 'BUI-HB-CB1178ASS' },
      }),
      finding({
        id: 'f2',
        code: 'unresolved_product',
        line_id: null,
        detail_json: { customer_code_raw: 'BUI-GF-CB1178ASS' },
      }),
    ]);
    expect(rows).toHaveLength(2);
  });

  it('falls back to detail_json.product_code when customer_code_raw is absent', () => {
    const rows = collapseFindings([
      finding({ id: 'f1', code: 'schedule_over', line_id: null, detail_json: { product_code: 'FH12' } }),
      finding({ id: 'f2', code: 'schedule_over', line_id: null, detail_json: { product_code: 'FH12' } }),
    ]);
    expect(rows).toHaveLength(1);
  });

  it('falls back to detail_json.line_no when everything else is absent', () => {
    const rows = collapseFindings([
      finding({ id: 'f1', code: 'code_vs_quotation', line_id: null, detail_json: { line_no: 6 } }),
      finding({ id: 'f2', code: 'code_vs_quotation', line_id: null, detail_json: { line_no: 6 } }),
    ]);
    expect(rows).toHaveLength(1);
  });

  it('never collapses a finding with none of the subject keys', () => {
    const rows = collapseFindings([
      finding({ id: 'f1', code: 'total_mismatch', line_id: null }),
      finding({ id: 'f2', code: 'total_mismatch', line_id: null }),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0].ids).toEqual(['f1']);
    expect(rows[1].ids).toEqual(['f2']);
  });

  it('carries the representative severity, code and detail of the first member', () => {
    const rows = collapseFindings([
      finding({ id: 'f1', severity: 'hard', code: 'schedule_short', detail: 'Only 0 placed.', line_id: 'line-9' }),
      finding({ id: 'f2', severity: 'hard', code: 'schedule_short', detail: 'Only 0 placed.', line_id: 'line-9' }),
    ]);
    expect(rows[0]).toMatchObject({ severity: 'hard', code: 'schedule_short', detail: 'Only 0 placed.' });
  });
});

describe('FINDING_SEVERITY_LABEL', () => {
  it('names the three severities per S3-1: Blocks publish, Needs acknowledgement, Info', () => {
    expect(FINDING_SEVERITY_LABEL.hard).toBe('Blocks publish');
    expect(FINDING_SEVERITY_LABEL.warn).toBe('Needs acknowledgement');
    expect(FINDING_SEVERITY_LABEL.info).toBe('Info');
  });
});

describe('publishBlockers (lesson (e): the one rule the server also applies)', () => {
  it('counts only this order\'s hard findings that have no acknowledged_at', () => {
    const blockers = publishBlockers([
      finding({ id: 'h1', severity: 'hard', code: 'line_arithmetic' }),
      finding({ id: 'h2', severity: 'hard', code: 'total_mismatch', acknowledged_at: '2026-09-01T00:00:00' }),
      finding({ id: 'w1', severity: 'warn' }),
      finding({ id: 'i1', severity: 'info' }),
    ]);
    expect(blockers.map((f) => f.id)).toEqual(['h1']);
  });

  it('keys on the timestamp, not the display name', () => {
    const blockers = publishBlockers([
      finding({ id: 'h1', severity: 'hard', acknowledged_at: '2026-09-01T00:00:00', acknowledged_by_name: null }),
    ]);
    expect(blockers).toHaveLength(0);
  });
});

describe('buildFlagItems (S7-3, R23)', () => {
  const SHORT = finding({
    id: 'so-short',
    severity: 'hard',
    code: 'schedule_short',
    detail: 'CB1178A: the PO orders 1830 but the schedule only places 0.',
    line_id: 'line-2',
    detail_json: { product_code: 'CB1178A' },
  });
  const COLUMN = finding({
    id: 'sch-col',
    severity: 'hard',
    code: 'unresolved_product',
    detail: "The schedule column 'BUI-HB-CB1178ASS' is not mapped to a product.",
    detail_json: { customer_code_raw: 'BUI-HB-CB1178ASS' },
  });

  it('names each item\'s source', () => {
    const items = buildFlagItems(
      [finding({ id: 'w1', line_id: 'line-1' })],
      [finding({ id: 's1', code: 'schedule_over', severity: 'hard', detail_json: { product_code: 'ZZ9' } })],
    );
    expect(items.map((item) => item.members.map((m) => m.source))).toEqual([['sales_order'], ['schedule']]);
    expect(items[0].lineId).toBe('line-1');
    expect(items[1].lineId).toBeNull();
  });

  it('R23: folds the unmapped column into the schedule_short finding it causes, one item', () => {
    const items = buildFlagItems([SHORT], [COLUMN]);
    expect(items).toHaveLength(1);
    expect(items[0].members.map((m) => m.finding.id)).toEqual(['so-short', 'sch-col']);
    expect(items[0].members.map((m) => m.source)).toEqual(['sales_order', 'schedule']);
    expect(items[0].lineId).toBe('line-2');
    expect(items[0].severity).toBe('hard');
  });

  it('R23: the longer product code wins a column two codes both fit', () => {
    const shorter = finding({
      ...SHORT,
      id: 'so-short-2',
      line_id: 'line-3',
      detail_json: { product_code: 'CB1178' },
    });
    const items = buildFlagItems([shorter, SHORT], [COLUMN]);
    const withColumn = items.find((item) => item.members.some((m) => m.finding.id === 'sch-col'));
    expect(withColumn?.lineId).toBe('line-2');
  });

  it('R23: a short product code never swallows an unrelated column (review SF1)', () => {
    const shortOf = (id: string, code: string) =>
      finding({ ...SHORT, id, line_id: `line-${id}`, detail_json: { product_code: code } });
    const column = finding({ ...COLUMN, detail_json: { customer_code_raw: 'BUI-HB-FH12SS' } });
    // HB is a whole segment of the column, H12 sits inside one: neither names the column.
    const items = buildFlagItems([shortOf('a', 'HB'), shortOf('b', 'SS'), shortOf('c', 'H12')], [column]);
    expect(items).toHaveLength(4);
    expect(items.every((item) => item.members.length === 1)).toBe(true);
  });

  it('R23: a code that starts a segment of the column still pairs, dashes and all', () => {
    const short = finding({ ...SHORT, detail_json: { product_code: 'SRT382-6' } });
    const column = finding({ ...COLUMN, detail_json: { customer_code_raw: 'BUI-HB-SRT382-6' } });
    expect(buildFlagItems([short], [column])).toHaveLength(1);
  });

  it('leaves a column that names no short product as its own schedule item', () => {
    const items = buildFlagItems(
      [SHORT],
      [finding({ ...COLUMN, id: 'other', detail_json: { customer_code_raw: 'BUI-XX-OTHER' } })],
    );
    expect(items).toHaveLength(2);
  });

  it('keeps a dismissed finding as a closed item of its own, never collapsed', () => {
    const items = buildFlagItems(
      [
        finding({ id: 'a', line_id: 'line-1', acknowledged_at: '2026-09-01T00:00:00' }),
        finding({ id: 'b', line_id: 'line-1', acknowledged_at: '2026-09-01T00:00:00' }),
      ],
      [],
    );
    expect(items).toHaveLength(2);
    expect(items.every((item) => !item.open)).toBe(true);
  });

  it('puts every publish blocker in an item that needs attention', () => {
    const orderFindings = [
      SHORT,
      finding({ id: 'h-noline', severity: 'hard', code: 'total_mismatch' }),
      finding({ id: 'w', severity: 'warn', line_id: 'line-5' }),
      finding({ id: 'i', severity: 'info', line_id: 'line-6' }),
    ];
    const items = buildFlagItems(orderFindings, [COLUMN]).filter(needsAttention);
    const covered = new Set(items.flatMap((item) => item.members.map((m) => m.finding.id)));
    for (const blocker of publishBlockers(orderFindings)) expect(covered.has(blocker.id)).toBe(true);
    expect(covered.has('i')).toBe(false);
  });
});

describe('leadFlagItem (review B1)', () => {
  it('leads with the most severe open item, not the first one', () => {
    const items = buildFlagItems(
      [
        finding({ id: 'w', severity: 'warn', code: 'price_vs_quotation', line_id: 'line-1' }),
        finding({ id: 'h', severity: 'hard', code: 'line_arithmetic', line_id: 'line-1' }),
      ],
      [],
    );
    expect(leadFlagItem(items)?.severity).toBe('hard');
  });

  it('skips dismissed items, and has no lead once all are dismissed', () => {
    const items = buildFlagItems(
      [
        finding({ id: 'h', severity: 'hard', line_id: 'line-1', acknowledged_at: '2026-09-01T00:00:00' }),
        finding({ id: 'w', severity: 'warn', code: 'x', line_id: 'line-1' }),
      ],
      [],
    );
    expect(leadFlagItem(items)?.severity).toBe('warn');
    expect(leadFlagItem(items.filter((item) => !item.open))).toBeUndefined();
  });
});
