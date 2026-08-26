/**
 * Phase 1 fixtures for the reporting foundation (PLAN-reporting-foundation, S1).
 *
 * This module stands in for `app/services/reports/engine.py` until S2. It really
 * filters, really groups and really totals, so every state the screen can show is a
 * state the engine will produce: switching the date basis moves a form between months,
 * widening the status filter brings rows back, and a blank measure stays blank rather
 * than becoming a zero.
 *
 * Money is handled in whole sen (integers) here for the same reason the engine uses
 * Decimal: adding "0.1" to "0.2" in float and printing two places is how a total ends
 * up a sen out from the workbook.
 *
 * DELETE THIS FILE in S2 together with the mock branches in `services/reportService.ts`.
 */

import type {
  ReportCatalogColumn,
  ReportColumn,
  ReportColumnGroup,
  ReportDetailLayout,
  ReportExportResult,
  ReportMeta,
  ReportParamValues,
  ReportPeriod,
  ReportPivotLayout,
  ReportResult,
  ReportRow,
  ReportView,
  ReportViewConfig,
  ReportViews,
} from '@/services/reportService';

export const MOCK_SCENARIO_KEYS = ['error', 'capped', 'loading', 'nopublish'] as const;
export type MockScenario = (typeof MOCK_SCENARIO_KEYS)[number];

const REPORT_KEY = 'sponsorship';
const PERMISSION = 'procurement.sponsorship_forms.report';
const LATENCY_MS = 220;

const delay = (ms = LATENCY_MS) => new Promise((resolve) => setTimeout(resolve, ms));

/* ------------------------------------------------------------------ catalog */

const CATALOG: ReportCatalogColumn[] = [
  { key: 'request_number', label: 'PS No', type: 'text', tag: 'dimension', size: 130 },
  { key: 'sales_agent', label: 'Sales agent', type: 'text', tag: 'dimension', size: 150 },
  { key: 'customer_name', label: 'Customer', type: 'text', tag: 'dimension', size: 170 },
  { key: 'project_title', label: 'Project title', type: 'text', tag: 'dimension', size: 220 },
  { key: 'sponsor_subject', label: 'Sponsor project', type: 'text', tag: 'dimension', size: 170 },
  { key: 'project_value', label: 'Project value', type: 'money', tag: 'measure', size: 150 },
  { key: 'project_value_text', label: 'Project value as stated', type: 'text', tag: 'text', size: 200 },
  { key: 'sample_price', label: 'Sample price', type: 'money', tag: 'measure', size: 140 },
  {
    key: 'expected_delivery_year',
    label: 'Expected year of delivery',
    type: 'integer',
    tag: 'dimension',
    size: 130,
  },
  { key: 'month', label: 'Month', type: 'text', tag: 'dimension', size: 110 },
  { key: 'status', label: 'Status', type: 'text', tag: 'dimension', size: 140 },
  { key: 'approved_at', label: 'Approved on', type: 'date', tag: 'date', size: 130 },
  { key: 'request_date', label: 'Form date', type: 'date', tag: 'date', size: 130 },
  { key: 'submitted_at', label: 'Submitted on', type: 'date', tag: 'date', size: 130 },
  { key: 'approver', label: 'Approver', type: 'text', tag: 'dimension', size: 150 },
  { key: 'purpose', label: 'Purpose', type: 'text', tag: 'text', size: 200 },
  { key: 'delivery_address', label: 'Delivery address', type: 'text', tag: 'text', size: 240 },
  { key: 'pic', label: 'PIC', type: 'text', tag: 'dimension', size: 150 },
];

/** The group source is a catalog dimension; the engine emits one tick column per year present. */
const YEAR_GROUP_SOURCE = 'expected_delivery_year';
const YEAR_GROUP_LABEL = 'Expected year of delivery';

/* ------------------------------------------------------------------- source */

type SourceRow = {
  request_number: string;
  sales_agent: string;
  customer_name: string;
  project_title: string;
  sponsor_subject: string;
  /** Sen, or null when the form carries no numeric project value. */
  project_value: number | null;
  project_value_text: string | null;
  /** Sen, or null when the form has no lines. */
  sample_price: number | null;
  expected_delivery_year: number | null;
  status: string;
  approved_at: string | null;
  request_date: string | null;
  submitted_at: string | null;
  approver: string | null;
  purpose: string;
  delivery_address: string;
  pic: string;
};

const SOURCE_ROWS: SourceRow[] = [
  {
    request_number: 'PSSF26-0310',
    sales_agent: 'Eric Ng',
    customer_name: 'Gamuda Land',
    project_title: 'Gamuda Cove clubhouse signage',
    sponsor_subject: 'Trophy',
    project_value: 116683070,
    project_value_text: null,
    sample_price: 40000,
    expected_delivery_year: 2026,
    status: 'processed_by_cs',
    approved_at: '2026-05-14',
    request_date: '2026-04-28',
    submitted_at: '2026-05-02',
    approver: 'Chin Wei Loon',
    purpose: 'Client sponsorship',
    delivery_address: 'Persiaran Gamuda Cove, 42700 Banting, Selangor',
    pic: 'Nadia Rahim',
  },
  {
    request_number: 'PSSF26-0288',
    sales_agent: 'Eric Ng',
    customer_name: 'Sunway Property',
    project_title: 'Sunway Velocity lobby display',
    sponsor_subject: 'Plaque',
    project_value: null,
    project_value_text: 'BULK ORDER EST RM1.6MIL',
    sample_price: 160000,
    expected_delivery_year: 2026,
    status: 'approved',
    approved_at: '2026-03-09',
    request_date: '2026-02-20',
    submitted_at: '2026-02-25',
    approver: 'Chin Wei Loon',
    purpose: 'Launch gift',
    delivery_address: 'Lingkaran SV, Cheras, 55100 Kuala Lumpur',
    pic: 'Nadia Rahim',
  },
  {
    request_number: 'PSSF26-0295',
    sales_agent: 'Amirul Hakim',
    customer_name: 'IJM Land',
    project_title: 'Riana Dutamas welcome wall',
    sponsor_subject: 'Corporate gift',
    project_value: null,
    project_value_text: null,
    sample_price: 244000,
    expected_delivery_year: 2027,
    status: 'approved',
    approved_at: '2026-04-17',
    request_date: '2026-03-30',
    submitted_at: '2026-04-01',
    approver: 'Lim Sok Cheng',
    purpose: 'Handover ceremony',
    delivery_address: 'Jalan Dutamas Raya, 51200 Kuala Lumpur',
    pic: 'Hafiz Zulkifli',
  },
  {
    request_number: 'PSSF26-0301',
    sales_agent: 'Leena Marzuki',
    customer_name: 'Eco World',
    project_title: 'Eco Ardence sales gallery',
    sponsor_subject: 'Others: Ramadan hamper',
    project_value: null,
    project_value_text: null,
    sample_price: null,
    expected_delivery_year: 2026,
    status: 'processed_by_cs',
    approved_at: '2026-06-05',
    request_date: '2026-05-19',
    submitted_at: '2026-05-22',
    approver: 'Lim Sok Cheng',
    purpose: 'Festive sponsorship',
    delivery_address: 'Persiaran Setia Alam, 40170 Shah Alam, Selangor',
    pic: 'Hafiz Zulkifli',
  },
  {
    request_number: 'PSSF26-0242',
    sales_agent: 'Amirul Hakim',
    customer_name: 'Mah Sing Group',
    project_title: 'M Vertica sky lounge',
    sponsor_subject: 'Trophy',
    project_value: 8800000,
    project_value_text: null,
    sample_price: 95000,
    expected_delivery_year: 2026,
    status: 'submitted',
    approved_at: null,
    request_date: '2026-01-12',
    submitted_at: '2026-01-15',
    approver: null,
    purpose: 'Topping-up ceremony',
    delivery_address: 'Jalan Cheras, 56000 Kuala Lumpur',
    pic: 'Hafiz Zulkifli',
  },
  {
    request_number: 'PSSF26-0333',
    sales_agent: 'Farah Idris',
    customer_name: 'LBS Bina Group',
    project_title: 'LBS Alam Perdana clubhouse',
    sponsor_subject: 'Corporate gift',
    project_value: null,
    project_value_text: null,
    sample_price: 30000,
    expected_delivery_year: 2026,
    status: 'rejected',
    approved_at: null,
    request_date: '2026-07-02',
    submitted_at: '2026-07-04',
    approver: 'Chin Wei Loon',
    purpose: 'Community day',
    delivery_address: 'Jalan Bandar Puncak Alam, 42300 Kuala Selangor',
    pic: 'Nadia Rahim',
  },
  {
    request_number: 'PSSF25-0198',
    sales_agent: 'Eric Ng',
    customer_name: 'Gamuda Land',
    project_title: 'Gamuda Gardens pocket park',
    sponsor_subject: 'Plaque',
    project_value: 4500000,
    project_value_text: null,
    sample_price: 120000,
    expected_delivery_year: 2025,
    status: 'approved',
    approved_at: '2025-11-20',
    request_date: '2025-10-30',
    submitted_at: '2025-11-03',
    approver: 'Chin Wei Loon',
    purpose: 'Park handover',
    delivery_address: 'Persiaran Gamuda Gardens, 48050 Rawang, Selangor',
    pic: 'Nadia Rahim',
  },
];

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'approved', label: 'Approved' },
  { value: 'processed_by_cs', label: 'Processed by CS' },
  { value: 'rejected', label: 'Rejected' },
];

const DATE_BASIS_OPTIONS = [
  { value: 'approved_at', label: 'Approved' },
  { value: 'request_date', label: 'Form date' },
  { value: 'submitted_at', label: 'Submitted' },
];

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const DEFAULT_VIEW: ReportViewConfig = {
  params: {
    date_basis: 'approved_at',
    period: { kind: 'year', year: 2026 },
    sales_agent: [],
    status: ['approved', 'processed_by_cs'],
  },
  detail: {
    columns: [
      'request_number',
      'sales_agent',
      'customer_name',
      'project_title',
      'sponsor_subject',
      'project_value',
      'sample_price',
      YEAR_GROUP_SOURCE,
    ],
    order: [
      'request_number',
      'sales_agent',
      'customer_name',
      'project_title',
      'sponsor_subject',
      'project_value',
      'sample_price',
      YEAR_GROUP_SOURCE,
    ],
  },
  pivot: { rows: 'sales_agent', cols: 'month', measures: ['project_value', 'sample_price'] },
};

/* -------------------------------------------------------------- saved views */

let VIEWS: ReportView[] = [
  {
    id: 'view-management-default',
    name: 'Management default',
    is_shared: true,
    is_default: true,
    owner_name: 'Chin Wei Loon',
    view: DEFAULT_VIEW,
  },
  {
    id: 'view-my-pipeline',
    name: 'My pipeline, form date',
    is_shared: false,
    is_default: false,
    owner_name: null,
    view: {
      ...DEFAULT_VIEW,
      params: {
        ...DEFAULT_VIEW.params,
        date_basis: 'request_date',
        status: ['approved', 'processed_by_cs', 'submitted'],
      },
      pivot: { rows: 'sponsor_subject', cols: 'month', measures: ['sample_price'] },
    },
  },
];

/* -------------------------------------------------------------- mock engine */

function money(sen: number): string {
  const sign = sen < 0 ? '-' : '';
  const abs = Math.abs(sen);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}

function periodBounds(period: ReportPeriod): { start: string; endExclusive: string; label: string } {
  if (period.kind === 'year') {
    const yy = String(period.year).slice(2);
    return {
      start: `${period.year}-01-01`,
      endExclusive: `${period.year + 1}-01-01`,
      label: `Jan'${yy} to Dec'${yy}`,
    };
  }
  if (period.kind === 'month_range') {
    const yy = String(period.year).slice(2);
    const endYear = period.to_month === 12 ? period.year + 1 : period.year;
    const endMonth = period.to_month === 12 ? 1 : period.to_month + 1;
    return {
      start: `${period.year}-${String(period.from_month).padStart(2, '0')}-01`,
      endExclusive: `${endYear}-${String(endMonth).padStart(2, '0')}-01`,
      label: `${MONTH_ABBR[period.from_month - 1]}'${yy} to ${MONTH_ABBR[period.to_month - 1]}'${yy}`,
    };
  }
  const end = new Date(`${period.to}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 1);
  return {
    start: period.from,
    endExclusive: end.toISOString().slice(0, 10),
    label: `${period.from} to ${period.to}`,
  };
}

/** Every month key inside the period, chronological, with the workbook's label. */
function monthsInPeriod(period: ReportPeriod): { values: string[]; labels: Record<string, string> } {
  const { start, endExclusive } = periodBounds(period);
  const values: string[] = [];
  const labels: Record<string, string> = {};
  const cursor = new Date(`${start}T00:00:00Z`);
  const stop = new Date(`${endExclusive}T00:00:00Z`);
  while (cursor < stop) {
    const key = cursor.toISOString().slice(0, 7);
    values.push(key);
    labels[key] = `${MONTH_ABBR[cursor.getUTCMonth()]}'${String(cursor.getUTCFullYear()).slice(2)}`;
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return { values, labels };
}

function asPeriod(value: unknown): ReportPeriod {
  const period = value as ReportPeriod | undefined;
  if (period && typeof period === 'object' && 'kind' in period) return period;
  return { kind: 'year', year: 2026 };
}

function asList(value: unknown): string[] {
  return Array.isArray(value) ? (value as string[]) : [];
}

function statusLabel(value: string): string {
  return STATUS_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

function filterRows(params: ReportParamValues): { rows: SourceRow[]; basis: string; period: ReportPeriod } {
  const basis = typeof params.date_basis === 'string' ? params.date_basis : 'approved_at';
  const period = asPeriod(params.period);
  const { start, endExclusive } = periodBounds(period);
  const agents = asList(params.sales_agent);
  const statuses = asList(params.status);

  const rows = SOURCE_ROWS.filter((row) => {
    const date = row[basis as 'approved_at' | 'request_date' | 'submitted_at'];
    if (!date || date < start || date >= endExclusive) return false;
    if (statuses.length > 0 && !statuses.includes(row.status)) return false;
    if (agents.length > 0 && !agents.includes(row.sales_agent)) return false;
    return true;
  });
  return { rows, basis, period };
}

function detailLayout(rows: SourceRow[], basis: string): ReportDetailLayout {
  const years = Array.from(
    new Set(rows.map((r) => r.expected_delivery_year).filter((y): y is number => y != null)),
  ).sort((a, b) => a - b);

  const tickColumns: ReportColumn[] = years.map((year) => ({
    key: `y${year}`,
    label: String(year),
    type: 'bool',
    size: 80,
  }));

  const columns: ReportColumn[] = [
    ...CATALOG.filter((c) => c.key !== YEAR_GROUP_SOURCE).map((c) => ({
      key: c.key,
      label: c.label,
      type: c.type,
      size: c.size,
    })),
    ...tickColumns,
  ];

  const groups: ReportColumnGroup[] =
    tickColumns.length > 0
      ? [{ label: YEAR_GROUP_LABEL, source: YEAR_GROUP_SOURCE, keys: tickColumns.map((c) => c.key) }]
      : [];

  const outRows: ReportRow[] = rows.map((row) => {
    const dateValue = row[basis as 'approved_at' | 'request_date' | 'submitted_at'];
    const out: ReportRow = {
      request_number: row.request_number,
      sales_agent: row.sales_agent,
      customer_name: row.customer_name,
      project_title: row.project_title,
      sponsor_subject: row.sponsor_subject,
      project_value: row.project_value == null ? null : money(row.project_value),
      project_value_text: row.project_value_text,
      sample_price: row.sample_price == null ? null : money(row.sample_price),
      month: dateValue ? dateValue.slice(0, 7) : null,
      status: statusLabel(row.status),
      approved_at: row.approved_at,
      request_date: row.request_date,
      submitted_at: row.submitted_at,
      approver: row.approver,
      purpose: row.purpose,
      delivery_address: row.delivery_address,
      pic: row.pic,
    };
    for (const year of years) out[`y${year}`] = row.expected_delivery_year === year;
    return out;
  });

  const totals: Record<string, string> = {};
  const projectValue = rows.reduce((sum, r) => sum + (r.project_value ?? 0), 0);
  const samplePrice = rows.reduce((sum, r) => sum + (r.sample_price ?? 0), 0);
  if (rows.some((r) => r.project_value != null)) totals.project_value = money(projectValue);
  if (rows.some((r) => r.sample_price != null)) totals.sample_price = money(samplePrice);

  return {
    key: 'detail',
    title: 'Sponsorships',
    columns,
    column_groups: groups,
    rows: outRows,
    totals,
  };
}

function dimensionValue(row: SourceRow, key: string, basis: string): string {
  if (key === 'month') {
    const date = row[basis as 'approved_at' | 'request_date' | 'submitted_at'];
    return date ? date.slice(0, 7) : '';
  }
  if (key === 'status') return statusLabel(row.status);
  if (key === 'expected_delivery_year') {
    return row.expected_delivery_year == null ? '' : String(row.expected_delivery_year);
  }
  const value = (row as unknown as Record<string, unknown>)[key];
  return value == null ? '' : String(value);
}

function measureSen(row: SourceRow, key: string): number | null {
  if (key === 'project_value') return row.project_value;
  if (key === 'sample_price') return row.sample_price;
  return null;
}

function pivotLayout(
  rows: SourceRow[],
  basis: string,
  period: ReportPeriod,
  config: ReportViewConfig['pivot'],
): ReportPivotLayout {
  const rowKey = config.rows;
  const colKey = config.cols;
  const measureKeys = config.measures.filter((m) =>
    CATALOG.some((c) => c.key === m && c.tag === 'measure'),
  );
  const measures: ReportColumn[] = measureKeys.map((key) => {
    const col = CATALOG.find((c) => c.key === key)!;
    return { key: col.key, label: col.label, type: col.type, size: col.size };
  });

  const colValues: string[] = [];
  let colLabels: Record<string, string> | undefined;
  if (colKey === 'month') {
    const months = monthsInPeriod(period);
    colValues.push(...months.values);
    colLabels = months.labels;
  } else {
    const seen = new Set<string>();
    for (const row of rows) {
      const value = dimensionValue(row, colKey, basis);
      if (value && !seen.has(value)) seen.add(value);
    }
    colValues.push(...Array.from(seen).sort());
  }

  const rowValues: string[] = Array.from(
    new Set(rows.map((r) => dimensionValue(r, rowKey, basis)).filter(Boolean)),
  ).sort((a, b) => a.localeCompare(b));

  const senCells: Record<string, Record<string, Record<string, number>>> = {};
  const senRowTotals: Record<string, Record<string, number>> = {};
  const senColTotals: Record<string, Record<string, number>> = {};
  const senGrand: Record<string, number> = {};

  for (const row of rows) {
    const rv = dimensionValue(row, rowKey, basis);
    const cv = dimensionValue(row, colKey, basis);
    if (!rv || !cv) continue;
    for (const measure of measureKeys) {
      const value = measureSen(row, measure);
      if (value == null) continue;
      senCells[rv] ??= {};
      senCells[rv][cv] ??= {};
      senCells[rv][cv][measure] = (senCells[rv][cv][measure] ?? 0) + value;
      senRowTotals[rv] ??= {};
      senRowTotals[rv][measure] = (senRowTotals[rv][measure] ?? 0) + value;
      senColTotals[cv] ??= {};
      senColTotals[cv][measure] = (senColTotals[cv][measure] ?? 0) + value;
      senGrand[measure] = (senGrand[measure] ?? 0) + value;
    }
  }

  const toMoneyMap = (input: Record<string, number>): Record<string, string> =>
    Object.fromEntries(Object.entries(input).map(([k, v]) => [k, money(v)]));

  return {
    key: 'summary',
    title: 'Summary by salesman',
    row_dim: {
      key: rowKey,
      label: CATALOG.find((c) => c.key === rowKey)?.label ?? rowKey,
    },
    col_dim: {
      key: colKey,
      label: CATALOG.find((c) => c.key === colKey)?.label ?? colKey,
      values: colValues,
      ...(colLabels ? { value_labels: colLabels } : {}),
    },
    measures,
    row_values: rowValues,
    cells: Object.fromEntries(
      Object.entries(senCells).map(([rv, cols]) => [
        rv,
        Object.fromEntries(Object.entries(cols).map(([cv, m]) => [cv, toMoneyMap(m)])),
      ]),
    ),
    row_totals: Object.fromEntries(Object.entries(senRowTotals).map(([k, v]) => [k, toMoneyMap(v)])),
    col_totals: Object.fromEntries(Object.entries(senColTotals).map(([k, v]) => [k, toMoneyMap(v)])),
    grand_total: toMoneyMap(senGrand),
  };
}

/* -------------------------------------------------------------- entry points */

export async function mockReportMeta(key: string, scenario: MockScenario | null): Promise<ReportMeta> {
  await delay();
  if (key !== REPORT_KEY) throw new Error(`Unknown report "${key}"`);
  const agents = Array.from(new Set(SOURCE_ROWS.map((r) => r.sales_agent))).sort((a, b) =>
    a.localeCompare(b),
  );
  return {
    key: REPORT_KEY,
    title: 'Sponsorship report',
    permission: PERMISSION,
    can_publish: scenario !== 'nopublish',
    params: [
      {
        kind: 'date_basis',
        key: 'date_basis',
        label: 'Date basis',
        default: 'approved_at',
        options: DATE_BASIS_OPTIONS,
      },
      {
        kind: 'period',
        key: 'period',
        label: 'Period',
        default: { kind: 'year', year: 2026 },
        years: [2026, 2025],
      },
      {
        kind: 'select',
        key: 'sales_agent',
        label: 'Sales agent',
        multi: true,
        clearable: true,
        default: [],
        options: agents.map((name) => ({ value: name, label: name })),
      },
      {
        kind: 'select',
        key: 'status',
        label: 'Status',
        multi: true,
        clearable: true,
        default: ['approved', 'processed_by_cs'],
        options: STATUS_OPTIONS,
      },
    ],
    catalog: CATALOG,
    default_view: DEFAULT_VIEW,
  };
}

export async function mockRunReport(
  key: string,
  params: ReportParamValues,
  view: ReportViewConfig,
  scenario: MockScenario | null,
): Promise<ReportResult> {
  if (scenario === 'loading') return new Promise<ReportResult>(() => {});
  await delay();
  if (key !== REPORT_KEY) throw new Error(`Unknown report "${key}"`);
  if (scenario === 'error') throw new Error('The report could not be run. Try again.');
  if (scenario === 'capped') {
    const capped = new Error(
      'This run returns more than 5,000 rows. Narrow the period or export to Excel instead.',
    );
    capped.name = 'ReportCappedError';
    throw capped;
  }

  const { rows, basis, period } = filterRows(params);
  return {
    key: REPORT_KEY,
    period_label: periodBounds(period).label,
    row_count: rows.length,
    capped: false,
    layouts: {
      detail: detailLayout(rows, basis),
      summary: pivotLayout(rows, basis, period, view.pivot),
    },
  };
}

export async function mockReportViews(key: string): Promise<ReportViews> {
  await delay(120);
  if (key !== REPORT_KEY) throw new Error(`Unknown report "${key}"`);
  return {
    mine: VIEWS.filter((v) => !v.is_shared),
    shared: VIEWS.filter((v) => v.is_shared),
  };
}

type ViewMutation =
  | { action: 'create'; name: string; view: ReportViewConfig }
  | { action: 'delete'; id: string }
  | { action: 'publish'; id: string; is_shared: boolean }
  | { action: 'set-default'; id: string };

export async function mockReportViewMutation(
  key: string,
  mutation: ViewMutation,
): Promise<ReportView> {
  await delay(160);
  if (key !== REPORT_KEY) throw new Error(`Unknown report "${key}"`);

  if (mutation.action === 'create') {
    const name = mutation.name.trim();
    if (!name) throw new Error('Name is required');
    if (VIEWS.some((v) => !v.is_shared && v.name.toLowerCase() === name.toLowerCase())) {
      throw new Error(`You already have a view called "${name}"`);
    }
    const created: ReportView = {
      id: `view-${Date.now()}`,
      name,
      is_shared: false,
      is_default: false,
      owner_name: null,
      view: mutation.view,
    };
    VIEWS = [...VIEWS, created];
    return created;
  }

  const target = VIEWS.find((v) => v.id === mutation.id);
  if (!target) throw new Error('That view no longer exists');

  if (mutation.action === 'delete') {
    VIEWS = VIEWS.filter((v) => v.id !== mutation.id);
    return target;
  }
  if (mutation.action === 'publish') {
    const updated = { ...target, is_shared: mutation.is_shared };
    VIEWS = VIEWS.map((v) => (v.id === updated.id ? updated : v));
    return updated;
  }
  const updated = { ...target, is_shared: true, is_default: true };
  VIEWS = VIEWS.map((v) =>
    v.id === updated.id ? updated : v.is_default ? { ...v, is_default: false } : v,
  );
  return updated;
}

export async function mockExportReport(
  key: string,
  params: ReportParamValues,
  view: ReportViewConfig,
): Promise<ReportExportResult> {
  void view; // The workbook honours it in S4; the mock only names the file.
  await delay(300);
  if (key !== REPORT_KEY) throw new Error(`Unknown report "${key}"`);
  const period = asPeriod(params.period);
  const suffix = period.kind === 'custom' ? `${period.from}_${period.to}` : String(period.year);
  return { download_id: `download-${Date.now()}`, filename: `Sponsorship report-${suffix}.xlsx` };
}
