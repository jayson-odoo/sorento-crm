/**
 * The SPO planner's two schedule views (doctrine correction, captain's ask #3): "PO coverage
 * schedule" and "SO coverage schedule" - product rows x weekly buckets, the same visual shape
 * `containerRequestMatrix.ts` builds for the loading plan's Stage 1 request. One generic
 * builder here rather than two near-identical ones: both views are "a flat list of dated,
 * quantified entries, grouped by product row and by the week their own date falls in" - the
 * PO-coverage entries are `po_takes` (bucketed by the PO's `expected_date`), the SO-coverage
 * entries are the cascaded demand takes (bucketed by the SO line's `required_date`). The
 * caller supplies the flat entry list; this only buckets and sums.
 *
 * WEEK granularity only (no day/month toggle) - a deliberate scope cut from the loading plan's
 * own three-granularity picker, to keep the planner's already-wide table from growing a second
 * control surface for a first cut. Flagged in the plan doc as a follow-up if wanted.
 *
 * `cascadeTake` is the SAME earliest-first algorithm `spo_conversion_service._cascade_take`
 * runs server-side (`min(available, still needed)` off each candidate in the order given,
 * stopping once covered) - mirrored here so the schedule, and the "what SO am I covering"
 * drill, can re-slice `po_takes` / `demand_lines` against the CURRENTLY EDITED qty on screen
 * without a round-trip, and never disagree with what `create` would actually do with that qty.
 */

export interface Takeable {
  qty: number;
}

/** Earliest-first cascade take, client-side mirror of the backend's own `_cascade_take`.
 *  `rows` must already be in the order to take from (both `po_takes` and a location's
 *  `demand_lines` arrive earliest-first from the server). Returns each row actually drawn
 *  from, carrying HOW MUCH of it this take used (`takenQty`) - never mutates `qty`. */
export function cascadeTake<T extends Takeable>(rows: T[], need: number): (T & { takenQty: number })[] {
  let still = need;
  const out: (T & { takenQty: number })[] = [];
  for (const row of rows) {
    if (still <= 0) break;
    const take = Math.min(row.qty, still);
    if (take > 0) {
      out.push({ ...row, takenQty: take });
      still -= take;
    }
  }
  return out;
}

export interface SpoMatrixEntry<T> {
  row_key: string;
  row_label: string;
  row_description?: string | null;
  /** ISO date, or null for "No date". */
  date: string | null;
  qty: number;
  detail: T;
}

export interface SpoMatrixBucket {
  key: string;
  kind: 'dated' | 'no_date';
  label: string;
  start?: string | null;
}

export interface SpoMatrixRow {
  key: string;
  label: string;
  description?: string | null;
}

export interface SpoMatrixCell<T> {
  row_key: string;
  bucket_key: string;
  qty: number;
  entries: SpoMatrixEntry<T>[];
}

export interface SpoMatrix<T> {
  rows: SpoMatrixRow[];
  buckets: SpoMatrixBucket[];
  cells: SpoMatrixCell<T>[];
}

const NO_DATE_KEY = 'no_date';

function startOfWeekIso(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const day = d.getDay();
  // Monday-start week, matching `containerRequestMatrix.ts`'s own `startOfWeek(..., { weekStartsOn: 1 })`.
  const diff = (day === 0 ? -6 : 1) - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

function weekLabel(startIso: string): string {
  const d = new Date(`${startIso}T00:00:00`);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function bucketFor(date: string | null): SpoMatrixBucket {
  if (!date) return { key: NO_DATE_KEY, kind: 'no_date', label: 'No date' };
  const start = startOfWeekIso(date);
  return { key: start, kind: 'dated', label: weekLabel(start), start };
}

export function buildSpoScheduleMatrix<T>(entries: SpoMatrixEntry<T>[]): SpoMatrix<T> {
  const rowMap = new Map<string, SpoMatrixRow>();
  const bucketMap = new Map<string, SpoMatrixBucket>();
  const cellMap = new Map<string, SpoMatrixCell<T>>();

  for (const entry of entries) {
    if (!(entry.qty > 0)) continue;
    if (!rowMap.has(entry.row_key)) {
      rowMap.set(entry.row_key, {
        key: entry.row_key,
        label: entry.row_label,
        description: entry.row_description,
      });
    }
    const bucket = bucketFor(entry.date);
    if (!bucketMap.has(bucket.key)) bucketMap.set(bucket.key, bucket);

    const cellKey = `${entry.row_key}|${bucket.key}`;
    const existing = cellMap.get(cellKey);
    if (existing) {
      existing.qty += entry.qty;
      existing.entries.push(entry);
    } else {
      cellMap.set(cellKey, { row_key: entry.row_key, bucket_key: bucket.key, qty: entry.qty, entries: [entry] });
    }
  }

  const buckets = [...bucketMap.values()].sort((a, b) => {
    if (a.kind === 'no_date') return b.kind === 'no_date' ? 0 : -1;
    if (b.kind === 'no_date') return 1;
    return (a.start ?? '').localeCompare(b.start ?? '');
  });
  const rows = [...rowMap.values()].sort((a, b) => a.label.localeCompare(b.label));
  const cells = [...cellMap.values()];

  return { rows, buckets, cells };
}
