import { getMalaysiaDateKey } from '@/lib/helpers';

export type PeriodKind = 'this_month' | 'last_month' | 'this_quarter' | 'ytd' | 'custom';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const pad = (n: number) => String(n).padStart(2, '0');
const iso = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;
const lastDay = (y: number, m: number) => new Date(Date.UTC(y, m, 0)).getUTCDate();

/**
 * date_from / date_to (YYYY-MM-DD) for a chip, with "today" taken in Asia/Kuala_Lumpur, and the
 * window the change is read against (this month: the same days of last month; last month: the
 * month before; this quarter: the same days of the previous quarter; YTD: the same dates last year).
 */
export function periodRange(kind: Exclude<PeriodKind, 'custom'>, now: Date = new Date()) {
  const [y, m, d] = getMalaysiaDateKey(now).split('-').map(Number);
  const today = iso(y, m, d);
  /** The month `back` months before (y, mo), as [year, month]. */
  const monthBack = (yy: number, mo: number, back: number): [number, number] => {
    const index = yy * 12 + (mo - 1) - back;
    return [Math.floor(index / 12), (index % 12) + 1];
  };
  const sameDay = (yy: number, mo: number, back: number) => {
    const [py, pm] = monthBack(yy, mo, back);
    return iso(py, pm, Math.min(d, lastDay(py, pm)));
  };

  if (kind === 'this_month') {
    const [py, pm] = monthBack(y, m, 1);
    return { from: iso(y, m, 1), to: today, previousFrom: iso(py, pm, 1), previousTo: sameDay(y, m, 1) };
  }
  if (kind === 'ytd') {
    return {
      from: iso(y, 1, 1),
      to: today,
      previousFrom: iso(y - 1, 1, 1),
      previousTo: iso(y - 1, m, Math.min(d, lastDay(y - 1, m))),
    };
  }
  if (kind === 'this_quarter') {
    const startMonth = Math.floor((m - 1) / 3) * 3 + 1;
    const [py, pm] = monthBack(y, startMonth, 3);
    return { from: iso(y, startMonth, 1), to: today, previousFrom: iso(py, pm, 1), previousTo: sameDay(y, m, 3) };
  }
  const [py, pm] = monthBack(y, m, 1);
  const [qy, qm] = monthBack(y, m, 2);
  return {
    from: iso(py, pm, 1),
    to: iso(py, pm, lastDay(py, pm)),
    previousFrom: iso(qy, qm, 1),
    previousTo: iso(qy, qm, lastDay(qy, qm)),
  };
}

const nf = new Intl.NumberFormat('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** `RM 1,856,856.61` */
export function formatRm(amount: number): string {
  return `RM ${nf.format(amount)}`;
}

/** `1,856,856.61` (the grid column header already says RM). */
export function formatAmount(amount: number): string {
  return nf.format(amount);
}

/** `1.86m`, `291k`: the phone podium. */
export function formatCompactRm(amount: number): string {
  const abs = Math.abs(amount);
  if (abs >= 1_000_000) return `${(amount / 1_000_000).toFixed(2)}m`;
  if (abs >= 1_000) return `${Math.round(amount / 1_000)}k`;
  return amount.toFixed(0);
}

/** `+63.6%` / `-10.4%`, `-` when there is no figure. */
export function formatChange(pct: number | null): string {
  if (pct === null || pct === undefined) return '-';
  return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

export function changeTone(pct: number | null): string {
  if (pct === null || pct === undefined || pct === 0) return 'text-muted-foreground';
  return pct > 0 ? 'text-emerald-600' : 'text-destructive';
}

/** `Sep` when the previous window is one whole calendar month (first day to last day), else `previous period`. */
export function previousLabel(previousFrom: string, previousTo: string): string {
  const [fy, fm, fd] = previousFrom.split('-').map(Number);
  const [ty, tm, td] = previousTo.split('-').map(Number);
  if (fy === ty && fm === tm && fd === 1 && td === lastDay(ty, tm)) {
    return MONTH_NAMES[fm - 1] ?? 'previous period';
  }
  return 'previous period';
}

/** Column sizes (px) of the ranking grid; they sum to what fits at 1280px with the sidebar open (about 940). */
export const COLUMN_SIZES = { rank: 60, person: 170, codes: 250, amount: 170, change: 140, customers: 110 } as const;

/** The codes line, only where it says something the name does not: two or more codes, or one that differs. */
export function codesText(person: string, codes: string[]): string {
  if (codes.length === 0) return '';
  if (codes.length === 1 && codes[0] === person) return '';
  return codes.join(', ');
}
