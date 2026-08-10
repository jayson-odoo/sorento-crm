/**
 * Is this demand going to last? The wording layer.
 *
 * > "Just give me a judgment that whether this demand is going to sustain or is going to
 * >  die off. So I can decide should I order more or should I order just enough or should
 * >  I order less."
 *
 * Mirrors `app/services/scm/trajectory.py`, which decides the verdicts; this file only
 * turns them into words. Every sentence is a fact about OUR OWN order book - like the
 * price advice, nothing here claims to see the market.
 */

export type TrajectoryVerdict = 'rising' | 'holding' | 'falling' | 'quiet' | 'no_history';

export interface TrajectoryEntry {
  verdict: TrajectoryVerdict;
  recent_qty: number;
  previous_qty: number;
  change_pct: number | null;
  year_ago_qty: number | null;
  year_change_pct: number | null;
  window_months: number;
  months: { month: string; qty: number }[];
  customers: { customer_name: string; qty: number }[];
  agents: { name: string; qty: number }[];
  agents_available: boolean;
}

export interface TrajectoryPayload {
  windows: { retail_months: number; project_months: number };
  movement_threshold_pct: number;
  series: Record<string, TrajectoryEntry>;
}

/** The Trend line on the row: the verdict AND what to do about it, in plain words. */
export const TRAJECTORY_ROW_LABEL: Record<TrajectoryVerdict, string> = {
  rising: 'Orders rising - consider more',
  holding: 'Orders steady',
  falling: 'Orders falling - consider less',
  quiet: 'No recent orders - buy just enough',
  no_history: 'Never ordered before',
};

export const TRAJECTORY_TONE: Record<TrajectoryVerdict, 'ok' | 'neutral' | 'warning'> = {
  rising: 'ok',
  holding: 'neutral',
  falling: 'warning',
  quiet: 'warning',
  no_history: 'neutral',
};

/**
 * The verdict with its evidence, for the popup headline.
 *
 * Numbers carry their meaning: "120 in the last 12 months, 90 in the 12 before" reads;
 * a bare +33% does not (AC-S13d.3: never a bare percentage as the headline).
 */
export function describeTrajectory(t: TrajectoryEntry | undefined): string {
  if (!t) return 'No order information for this product.';
  const w = t.window_months;
  const windowWord = `${w} month${w === 1 ? '' : 's'}`;
  const base = `${fmtQty(t.recent_qty)} ordered in the last ${windowWord}, ${fmtQty(t.previous_qty)} in the ${windowWord} before`;

  switch (t.verdict) {
    case 'rising':
      return `Orders are rising: ${base}. Worth considering more than the bare need.`;
    case 'falling':
      return `Orders are falling: ${base}. Consider buying less than the suggestion.`;
    case 'quiet':
      return `Orders stopped: nothing in the last ${windowWord}, after ${fmtQty(t.previous_qty)} in the ${windowWord} before. Buy just enough.`;
    case 'no_history':
      return `No orders on record in the last ${w * 2} months.`;
    case 'holding':
    default:
      return `Orders are steady: ${base}.`;
  }
}

/** The year-ago comparison, beside the verdict - named absent when the book is younger. */
export function describeYearAgo(t: TrajectoryEntry | undefined): string | null {
  if (!t) return null;
  if (t.year_ago_qty === null) return 'No figure for the same window last year.';
  if (t.year_change_pct === null) {
    return `Same window last year: ${fmtQty(t.year_ago_qty)}.`;
  }
  const dir = t.year_change_pct >= 0 ? 'up' : 'down';
  return `Against the same window last year (${fmtQty(t.year_ago_qty)}): ${dir} ${Math.abs(t.year_change_pct).toFixed(0)}%.`;
}

function fmtQty(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** The key both the plan row and the trajectory map agree on. */
export function trajectoryKey(
  productId: string | null,
  segment: string | null | undefined,
): string | null {
  if (!productId) return null;
  // The service defaults an unsegmented warehouse to 'project', and so must the reader.
  return `${productId}:${segment || 'project'}`;
}

/**
 * The two chart series: this year's months, and the same months a year earlier.
 *
 * > "i need this kind of trend to be in a line graph so it is easier to relate"
 *
 * Both series share the recent 12 months' labels; the year-ago line is the SAME month one
 * year back, so the eye compares seasons vertically.
 */
export function chartSeries(t: TrajectoryEntry): {
  labels: string[];
  thisYear: number[];
  lastYear: (number | null)[];
} {
  const byMonth = new Map(t.months.map((m) => [m.month, m.qty]));
  const labels: string[] = [];
  const now = new Date();
  const months: { y: number; m: number }[] = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - 1 - i, 1);
    months.push({ y: d.getFullYear(), m: d.getMonth() + 1 });
  }
  const key = (y: number, m: number) => `${y.toString().padStart(4, '0')}-${m.toString().padStart(2, '0')}`;
  const thisYear = months.map(({ y, m }) => byMonth.get(key(y, m)) ?? 0);
  const lastYear = months.map(({ y, m }) => {
    const k = key(y - 1, m);
    return byMonth.has(k) ? (byMonth.get(k) as number) : null;
  });
  for (const { y, m } of months) {
    labels.push(`${String(m).padStart(2, '0')}/${String(y).slice(2)}`);
  }
  return { labels, thisYear, lastYear };
}
