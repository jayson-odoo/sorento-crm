/**
 * S3-3: findings with the same code about the same subject collapse into one row with a
 * count. Subject key, first present wins: line_id, then detail_json.customer_code_raw,
 * then detail_json.product_code, then detail_json.line_no. A finding with none of these
 * keys never collapses.
 */
import { describe, expect, it } from 'vitest';
import { collapseFindings, FINDING_SEVERITY_LABEL } from './findings';
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
