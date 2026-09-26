/**
 * `foldBySubject` (S1-21, N3/N4): the DataGrid still gets one row per target PERIOD from the
 * API; the screen folds every subject's rows into ONE line. The numeric cells (Target,
 * Achieved, %) are the FIRST target's by this order: amount before quantity, then soonest
 * `end_date`, then lowest `target_no`. The Targets cell is a `PillOverflow` of every target's
 * name on that subject, in the same order, each linking to its own page.
 *
 * Exported name/signature the coder must match:
 *   `foldBySubject<T extends FoldableTargetRow>(rows: T[]): FoldedRow<T>[]`
 *   `FoldableTargetRow = { subject_key: string; target_id: string | null; metric: 'amount' | 'quantity' | null; end_date: string | null; target_no: string | null }`
 *   `FoldedRow<T> = { subject_key: string; primary: T; targets: T[] }`
 * `subject_key` is whatever the caller derives to group by (a team id, an agent id, or a
 * synthetic key for "no team" / "unassigned") - `foldBySubject` itself only groups and orders,
 * it never looks at `sales_agent_id` / `sales_team_id` directly.
 */
import { describe, expect, it } from 'vitest';
import { foldBySubject } from './fold';

interface Row {
  subject_key: string;
  target_id: string | null;
  metric: 'amount' | 'quantity' | null;
  end_date: string | null;
  target_no: string | null;
  name?: string;
}

function row(over: Partial<Row>): Row {
  return {
    subject_key: 'ali',
    target_id: 't1',
    metric: 'amount',
    end_date: '2026-12-31',
    target_no: 'TGT-000001',
    ...over,
  };
}

describe('foldBySubject', () => {
  it('picks amount before quantity, even when the quantity target ends sooner', () => {
    const amount = row({ target_id: 'amt', metric: 'amount', end_date: '2027-06-30', target_no: 'TGT-000002' });
    const quantity = row({ target_id: 'qty', metric: 'quantity', end_date: '2026-11-30', target_no: 'TGT-000001' });
    const [folded] = foldBySubject([quantity, amount]);
    expect(folded.primary.target_id).toBe('amt');
    expect(folded.targets.map((t) => t.target_id)).toEqual(['amt', 'qty']);
  });

  it('same metric: the soonest end date wins', () => {
    const later = row({ target_id: 'later', end_date: '2027-03-31', target_no: 'TGT-000001' });
    const sooner = row({ target_id: 'sooner', end_date: '2026-11-30', target_no: 'TGT-000002' });
    const [folded] = foldBySubject([later, sooner]);
    expect(folded.primary.target_id).toBe('sooner');
  });

  it('same metric and end date: the lowest target_no wins', () => {
    const high = row({ target_id: 'high', end_date: '2026-12-31', target_no: 'TGT-000009' });
    const low = row({ target_id: 'low', end_date: '2026-12-31', target_no: 'TGT-000002' });
    const [folded] = foldBySubject([high, low]);
    expect(folded.primary.target_id).toBe('low');
  });

  it('keeps a "No target" row (target_id null) as its own single-row group', () => {
    const noTarget = row({ subject_key: 'raj', target_id: null, metric: null, end_date: null, target_no: null });
    const [folded] = foldBySubject([noTarget]);
    expect(folded.subject_key).toBe('raj');
    expect(folded.primary.target_id).toBeNull();
    expect(folded.targets).toEqual([noTarget]);
  });

  it('never mixes two different subjects into one group', () => {
    const ali = row({ subject_key: 'ali', target_id: 'a1' });
    const mei = row({ subject_key: 'mei', target_id: 'm1' });
    const folded = foldBySubject([ali, mei]);
    expect(folded.map((f) => f.subject_key).sort()).toEqual(['ali', 'mei']);
    expect(folded.every((f) => f.targets.length === 1)).toBe(true);
  });
});
