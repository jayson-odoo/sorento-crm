/**
 * One line per subject (S1-21; owner ruling 26 Sep 06:01 (Lavish), N3 and N4). The API returns
 * one row per target PERIOD; the screen folds each subject's rows into one line whose numeric
 * cells are the FIRST target's: amount before quantity, then the soonest end date, then the
 * lowest target number, so the order never changes between visits. `targets` holds every row
 * of the subject in that same order, for the Targets pill cell.
 *
 * `subject_key` is whatever the caller groups by; this only groups and orders.
 */
export interface FoldableTargetRow {
  subject_key: string;
  target_id: string | null;
  metric: 'amount' | 'quantity' | null;
  end_date: string | null;
  target_no: string | null;
}

export interface FoldedRow<T> {
  subject_key: string;
  primary: T;
  targets: T[];
}

function compare(a: FoldableTargetRow, b: FoldableTargetRow): number {
  const metric = (row: FoldableTargetRow) => (row.metric === 'amount' ? 0 : 1);
  if (metric(a) !== metric(b)) return metric(a) - metric(b);
  const endA = a.end_date ?? '9999-12-31';
  const endB = b.end_date ?? '9999-12-31';
  if (endA !== endB) return endA < endB ? -1 : 1;
  const noA = a.target_no ?? '';
  const noB = b.target_no ?? '';
  return noA < noB ? -1 : noA > noB ? 1 : 0;
}

export function foldBySubject<T extends FoldableTargetRow>(rows: T[]): FoldedRow<T>[] {
  const groups = new Map<string, T[]>();
  for (const row of rows) {
    const group = groups.get(row.subject_key);
    if (group) group.push(row);
    else groups.set(row.subject_key, [row]);
  }
  return Array.from(groups, ([subject_key, group]) => {
    const targets = [...group].sort(compare);
    return { subject_key, primary: targets[0], targets };
  });
}
