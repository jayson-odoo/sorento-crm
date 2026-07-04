/**
 * Minimal client-side line-level diff (LCS). No external dep — raw-text
 * storage (PLAN §9b Q1/Q2) makes a simple line diff accurate. Returns an
 * ordered list of rows tagged equal | added | removed for side-by-side or
 * unified rendering.
 */
export type DiffOp = 'equal' | 'added' | 'removed';

export interface DiffRow {
  op: DiffOp;
  aLine: number | null; // 1-based line number in `a`, null for added
  bLine: number | null; // 1-based line number in `b`, null for removed
  text: string;
}

export function lineDiff(a: string, b: string): DiffRow[] {
  const aLines = a.split('\n');
  const bLines = b.split('\n');
  const n = aLines.length;
  const m = bLines.length;

  // LCS length table
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = aLines[i] === bLines[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }

  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (aLines[i] === bLines[j]) {
      rows.push({ op: 'equal', aLine: i + 1, bLine: j + 1, text: aLines[i] });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      rows.push({ op: 'removed', aLine: i + 1, bLine: null, text: aLines[i] });
      i++;
    } else {
      rows.push({ op: 'added', aLine: null, bLine: j + 1, text: bLines[j] });
      j++;
    }
  }
  while (i < n) {
    rows.push({ op: 'removed', aLine: i + 1, bLine: null, text: aLines[i] });
    i++;
  }
  while (j < m) {
    rows.push({ op: 'added', aLine: null, bLine: j + 1, text: bLines[j] });
    j++;
  }
  return rows;
}

export function diffStats(rows: DiffRow[]): { added: number; removed: number } {
  return rows.reduce(
    (acc, r) => {
      if (r.op === 'added') acc.added++;
      if (r.op === 'removed') acc.removed++;
      return acc;
    },
    { added: 0, removed: 0 },
  );
}
