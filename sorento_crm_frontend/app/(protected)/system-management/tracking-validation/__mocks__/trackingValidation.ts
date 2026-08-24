/**
 * PHASE 1 MOCK - delete in Phase 2 (issue #67 / S8).
 *
 * The validation report is the whole justification for the integrations: it answers
 * "would the liner and CIDB feeds have told us sooner than the human did?".
 *
 * Verdicts:
 *   agree          - feed matches what was typed
 *   disagree       - one of them is wrong, investigate
 *   integration_led - the feed knew FIRST; `lag_days` is the time recovered
 *
 * `observed_at` is stored NAIVE UTC, matching how the backend serializes timestamps -
 * `formatDateTimeInMalaysia` adds +8 for display. Writing MYT wall-clock here would
 * render 8 hours late.
 *
 * Container numbers and dates below are real rows from `Container Status 2026.xlsx`.
 * The `observed_*` values are synthetic - no feed exists yet, which is the point of
 * building this surface before the scrapers.
 */

export type Verdict = 'agree' | 'disagree' | 'integration_led';

export interface TrackingObservationRow {
  id: string;
  container_number: string;
  field_key: string;
  field_label: string;
  /** What the human typed in the sheet. */
  sheet_value: string | null;
  /** What the feed reported. */
  observed_value: string | null;
  source: 'liner_cma' | 'liner_whl' | 'liner_oocl' | 'cidb_epermit' | 'unsupported';
  source_label: string;
  observed_at: string;
  verdict: Verdict;
  /** Days the feed was ahead of the human. Only meaningful when verdict is integration_led. */
  lag_days: number | null;
}

export const MOCK_OBSERVATIONS: TrackingObservationRow[] = [
  {
    id: 'obs-1',
    container_number: 'GXYU5106903',
    field_key: 'eta_delay_date',
    field_label: 'ETA Delay',
    sheet_value: '2026-07-08',
    observed_value: '2026-07-08',
    source: 'liner_cma',
    source_label: 'CMA CGM',
    observed_at: '2026-07-02T01:14:00',
    verdict: 'integration_led',
    lag_days: 3,
  },
  {
    id: 'obs-2',
    container_number: 'GXYU5115470',
    field_key: 'eta_delay_date',
    field_label: 'ETA Delay',
    sheet_value: '2026-07-12',
    observed_value: '2026-07-12',
    source: 'liner_cma',
    source_label: 'CMA CGM',
    observed_at: '2026-07-11T14:05:00',
    verdict: 'agree',
    lag_days: null,
  },
  {
    id: 'obs-3',
    container_number: 'FCIU7600305',
    field_key: 'inspection_date',
    field_label: 'Inspection',
    sheet_value: '2026-07-09',
    observed_value: '2026-07-09',
    source: 'cidb_epermit',
    source_label: 'CIDB ePermit',
    observed_at: '2026-07-07T08:40:00',
    verdict: 'integration_led',
    lag_days: 2,
  },
  {
    id: 'obs-4',
    container_number: 'FCIU7600305',
    field_key: 'approval_date',
    field_label: 'Approval (COA)',
    sheet_value: '2026-07-10',
    observed_value: '2026-07-11',
    source: 'cidb_epermit',
    source_label: 'CIDB ePermit',
    observed_at: '2026-07-11T00:12:00',
    verdict: 'disagree',
    lag_days: null,
  },
  {
    id: 'obs-5',
    container_number: 'SEGU4326041',
    field_key: 'eta_delay_date',
    field_label: 'ETA Delay',
    sheet_value: '2026-07-05',
    observed_value: '2026-07-05',
    source: 'liner_cma',
    source_label: 'CMA CGM',
    observed_at: '2026-07-01T03:30:00',
    verdict: 'integration_led',
    lag_days: 4,
  },
  {
    id: 'obs-6',
    container_number: 'CAIU7321914',
    field_key: 'approval_date',
    field_label: 'Approval (COA)',
    sheet_value: '2026-07-10',
    observed_value: '2026-07-10',
    source: 'cidb_epermit',
    source_label: 'CIDB ePermit',
    observed_at: '2026-07-10T06:02:00',
    verdict: 'agree',
    lag_days: null,
  },
  {
    id: 'obs-7',
    container_number: 'OOCU8630645',
    field_key: 'eta_delay_date',
    field_label: 'ETA Delay',
    sheet_value: '2026-07-06',
    observed_value: null,
    source: 'unsupported',
    source_label: 'NSS - no adapter',
    observed_at: '2026-07-03T23:00:00',
    verdict: 'disagree',
    lag_days: null,
  },
  {
    id: 'obs-8',
    container_number: 'CICU1013499',
    field_key: 'gatepass_date',
    field_label: 'Gatepass',
    sheet_value: '2026-07-17',
    observed_value: '2026-07-17',
    source: 'liner_oocl',
    source_label: 'OOCL',
    observed_at: '2026-07-16T11:45:00',
    verdict: 'agree',
    lag_days: null,
  },
];

export interface ValidationSummary {
  containers: number;
  observations: number;
  agree_pct: number;
  integration_led_pct: number;
  disagree_pct: number;
  avg_lag_days: number;
}

/** The one sentence that earns the cutover off the Excel. Computed, never hardcoded. */
export function summarize(rows: TrackingObservationRow[]): ValidationSummary {
  const total = rows.length || 1;
  const led = rows.filter((r) => r.verdict === 'integration_led');
  const lagSum = led.reduce((acc, r) => acc + (r.lag_days ?? 0), 0);
  const pct = (n: number) => Math.round((n / total) * 100);
  return {
    containers: new Set(rows.map((r) => r.container_number)).size,
    observations: rows.length,
    agree_pct: pct(rows.filter((r) => r.verdict === 'agree').length),
    integration_led_pct: pct(led.length),
    disagree_pct: pct(rows.filter((r) => r.verdict === 'disagree').length),
    avg_lag_days: led.length ? Math.round((lagSum / led.length) * 10) / 10 : 0,
  };
}
