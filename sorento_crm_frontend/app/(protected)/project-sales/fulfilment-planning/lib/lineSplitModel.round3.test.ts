/**
 * OI-LINE-SPLIT round 3 (AC-G2, AC-G3, AC-G5): fromPayload carries the new wire fields.
 */
import { describe, expect, it } from 'vitest';
import { fromPayload } from './lineSplitModel';
import type { LineSplitsPayload } from '../../_shared/types/lineSplit.types';
import { wireLine, wireSplit } from '@/test-mocks/lineSplitSheetKit';

function payload(lines: unknown[]): LineSplitsPayload {
  return {
    pso_id: 'p',
    so_number: 'SO1',
    customer: 'PLACEHOLDER CUSTOMER',
    project: 'PLACEHOLDER PROJECT',
    confirmed_at: '2026-10-18T09:00:00Z',
    lines,
  } as unknown as LineSplitsPayload;
}

describe('fromPayload round 3 fields', () => {
  it('maps extra_qty, extra_remark and remark_generated', () => {
    const [line] = fromPayload(
      payload([
        wireLine(752, 'CSK14B', 504, '2026-12-20', {
          extra_qty: 182,
          extra_remark: 'ORDER 182',
          splits: [
            wireSplit('s1', 37, '2026-11-20', 'L608', {
              remark_generated: 'Advanced to 20/11/2026',
            }),
          ],
        }),
      ]),
    );
    expect(line.extraQty).toBe(182);
    expect(line.extraRemark).toBe('ORDER 182');
    expect(line.splits[0].remarkGenerated).toBe('Advanced to 20/11/2026');
  });

  it('keeps nulls and an empty generated remark', () => {
    const [line] = fromPayload(
      payload([
        wireLine(480, 'CSK14B', 417, '2026-10-20', {
          splits: [wireSplit('s1', 417, '2026-10-20', 'L480')],
        }),
      ]),
    );
    expect(line.extraQty).toBeNull();
    expect(line.extraRemark).toBeNull();
    expect(line.splits[0].remarkGenerated).toBe('');
  });

  it('maps a line remark_generated to remarkGenerated', () => {
    const [line] = fromPayload(
      payload([wireLine(608, 'CSK14B', 192, '2026-11-20', { remark_generated: 'REMAIN' })]),
    );
    expect((line as unknown as { remarkGenerated: string }).remarkGenerated).toBe('REMAIN');
  });
});
