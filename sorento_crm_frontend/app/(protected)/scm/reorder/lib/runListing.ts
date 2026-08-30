/**
 * How a plan reads on the plans list: when it ran, and where it is up to.
 *
 * The status is DERIVED, not stored. `reorder_run.status` only knows whether the engine
 * finished; whether the buyer has finished with it is a fact about the decisions on it, and
 * the two are different questions the same word used to answer.
 */
import { DATE_LOCALE, DATE_PARTS, EM_DASH } from '../../lib/format';
import type { ReorderRunHistoryItem } from '../services/reorderRunService';

export type RunListStatus = 'running' | 'planning' | 'confirmed' | 'failed';

export interface RunStatusReading {
  status: RunListStatus;
  label: string;
  variant: 'success' | 'info' | 'destructive' | 'secondary';
}

/**
 * Running / Planning / Confirmed / Failed (plan 4.1).
 *
 * Confirmed needs BOTH counts, and the denominator is the products the plan actually WROTE
 * ROWS for (`planned_product_count`) rather than the scope it was launched with - the daily
 * run narrows to nothing, so its scope is null and every daily plan would read Planning
 * forever. Counts absent altogether still read Planning, which stays the honest answer:
 * nobody has told us every product is confirmed.
 */
export function runStatusReading(run: {
  status: ReorderRunHistoryItem['status'];
  product_count?: number | null;
  planned_product_count?: number | null;
  confirmed_product_count?: number | null;
}): RunStatusReading {
  if (run.status === 'failed') {
    return { status: 'failed', label: 'Failed', variant: 'destructive' };
  }
  if (run.status !== 'completed') {
    return { status: 'running', label: 'Running', variant: 'info' };
  }
  const total = run.planned_product_count ?? run.product_count;
  const confirmed = run.confirmed_product_count;
  if (
    total !== null && total !== undefined && total > 0 &&
    confirmed !== null && confirmed !== undefined &&
    confirmed >= total
  ) {
    return { status: 'confirmed', label: 'Confirmed', variant: 'success' };
  }
  return { status: 'planning', label: 'Planning', variant: 'secondary' };
}

/**
 * A naive-UTC ISO timestamp as `dd/mm/yyyy HH:mm` in Malaysia.
 *
 * Date parts come from `lib/format` rather than being restated, so the plans list cannot
 * drift from the dd/mm/yyyy every other screen uses.
 */
export function runStartedLabel(startedAt: string | null | undefined): string {
  if (!startedAt) return EM_DASH;
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(startedAt);
  const d = new Date(hasTz ? startedAt : `${startedAt}Z`);
  if (Number.isNaN(d.getTime())) return startedAt;
  const date = new Intl.DateTimeFormat(DATE_LOCALE, {
    ...DATE_PARTS,
    timeZone: 'Asia/Kuala_Lumpur',
  }).format(d);
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kuala_Lumpur',
  }).format(d);
  return `${date} ${time}`;
}
