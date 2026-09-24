/**
 * ============================================================================
 * Stock Debt - feature service (S2, AC-S2-6 / AC-S2-7; extended 24 Sep 2026,
 * PLAN-stock-debt-filters-totals-export-24sep.md, Phase 1)
 * ============================================================================
 * Layering: UI -> hooks (`useStockDebtQuery`) -> THIS service -> lib/api-client
 * -> backend.
 *
 * ── PHASE-1 MOCK CONTRACT (24 Sep 2026 lane only) ───────────────────────────
 * `getStockDebtList` runs off `mockStockDebtList()` below while
 * `USE_STOCK_DEBT_FILTER_MOCKS` is `true` - the base board (S2) already calls
 * the real backend, but this lane's five new fields (`cutoff`, `supplier_id`,
 * `book` on the request; `totals`, `suppliers`, and per-row `supplier_id` /
 * `supplier_name` / `category_code` / `total` on the response) do not exist on
 * it yet (Phase 2, AC-1 to AC-11). Rather than half-call the real endpoint and
 * paper over the missing fields, the whole function is mocked, the same shape
 * `reorderRunService.ts`'s `USE_M4_MOCKS` and `summaryOrderMockStore.ts` use:
 * Phase 2 flips the flag to `false` and deletes the mock branch - a one-line
 * swap at this function's first statement, not a rewrite of its callers.
 *
 * `getStockDebtCell` is UNCHANGED and keeps calling the real backend: the cell
 * drill is not part of this lane's Phase 1 scope (extending it with `cutoff` /
 * `book`, AC-11, lands with the rest of the backend work in Phase 2).
 *
 * `exportStockDebt` has no real route to fall back to at all yet (AC-12 is
 * net-new in Phase 2), so it is mocked unconditionally behind the same flag -
 * there is nothing for the flag to choose between until Phase 2 exists.
 *
 * The export popover's "212 rows, 14 sheets" preview (AC-33) reads
 * `pagination.total` for rows and the envelope's `sheet_counts` (AC-7b) for
 * sheets - both already committed, whole-filtered-set fields, not a Phase-1
 * add-on, so `previewStockDebtExport()` needs no branch of its own once Phase 2
 * lands: it already reads the real shape.
 *
 * ── PHASE-2 BACKEND CONTRACT ────────────────────────────────────────────────
 * Both routes live under the `projects` domain router and both require
 * `projects.stock_debt.view` (AC-S2-8, R22; permission + grant sweep shipped in
 * migration 443 with S1).
 *
 * 1) The month x product board (AC-S2-6, extended AC-1 to AC-9)
 *
 *      GET /api/v1/project-sales/stock-debt
 *          ?page=<1-based>      standard `buildDataGridParams` paging
 *          &limit=<n>
 *          &query=<text>        product code or name
 *          &group=<BB|IB|...>   ownership group; narrows the `project` half of
 *                               `book` only (AC-8, R1) - ignored under `book=retail`
 *          &only_debt=<bool>    drop rows with no negative month (default true on
 *                               the screen)
 *          &cutoff=<YYYY-MM-DD> drop demand due after this date; ends the axis
 *                               at its month (R2, A2, AC-1/AC-2/AC-3)
 *          &supplier_id=<uuid>|none  keep only products whose LAST supplier
 *                               (newest PO line, else the primary flag) is this
 *                               one; `none` keeps products with neither (R3, AC-4)
 *          &book=<all|project|retail>  `all` (default) = flagged project bins
 *                               PLUS the site pools, in one span; `project` is
 *                               today's view; `retail` is pools only (R1, AC-8)
 *
 *      -> 200 {
 *           data: [{
 *             product_id, product_code, product_name,
 *             months: [{ key: 'YYYY-MM', balance, tone: 'red'|'amber'|'green' }],
 *             tba, undated, unlocated,
 *             supplier_id, supplier_name, category_code, total
 *           }],
 *           pagination: { total, page, limit },
 *           months:    ['YYYY-MM', ...],   the column axis
 *           tba_month: 'YYYY-MM',          the policy's `tba_date_from`, by month
 *           groups:    ['BB', ...]         what the flag admits, for the select
 *           totals:    { months: { 'YYYY-MM': number, ... }, tba, undated,
 *                        unlocated, total }   over the WHOLE filtered set (AC-6)
 *           suppliers: [{ id, name }]      distinct last suppliers of the
 *                                          filtered set, sorted by name (AC-7)
 *           sheet_counts: { supplier, category, supplier_category }
 *                                          exact export sheet counts for the current
 *                                          filtered set, none-buckets included (AC-7b)
 *         }
 *
 *      `data[].months` carries one entry per axis key, in axis order. A month states its
 *      OWN month (R37, 30 Aug 2026): the supply dated in it that is still free once the
 *      assignment walk is over, less what the lines due in it went short of on their own
 *      dates. Nothing carries, so a month with nothing due and nothing arriving reads 0.
 *      Rows are sorted by EARLIEST RED MONTH, then product code; a row with no red
 *      month sorts after every row that has one.
 *      `tba`, `undated` and `unlocated` are plain signed totals - the demand dated on
 *      or after `tba_date_from`, the demand with no date, and the demand booked at no
 *      warehouse at all. None of the three draws supply (R14), so they carry no tone and
 *      the screen renders them as informational.
 *      `total` (AC-5) sums every month's balance plus `tba` + `undated` + `unlocated` -
 *      it INCLUDES the three no-supply buckets (R9), so it is never the sum of `months`
 *      alone.
 *      `product_name` is `null` when it equals `product_code`, case-sensitive and
 *      trimmed, so the board and the export agree without each re-deriving it (AC-9).
 *
 *      The axis fields, `totals`, `suppliers` and `sheet_counts` are envelope-level and
 *      NOT per row, because each is a property of the whole filtered set: derived per
 *      page, the columns (or the footer, or the select, or the export preview) would
 *      change under the reader as they page (AC-7b: page 2 states the same
 *      `sheet_counts` as page 1).
 *
 * 2) The cell drill (AC-S2-7, R28) - UNCHANGED in this lane's Phase 1; Phase 2 adds
 *    `cutoff` and `book` (AC-11) so the drill foots with a narrowed board.
 *
 *      GET /api/v1/project-sales/stock-debt/{product_id}/cell
 *          ?month=<YYYY-MM | tba | undated | unlocated>
 *          &group=<BB|IB|...>   the group the BOARD is narrowed to. Same meaning as on
 *                               the list: it narrows the span the balance is recomputed
 *                               from, so the drill foots with the cell that opened it.
 *                               Omitted = the whole book.
 *
 *      -> 200 {
 *           demand: [{ so_number, agent_code, warehouse_code, required_date, open_qty,
 *                      assigned_qty, assigned_source, short_qty,
 *                      status: 'covered'|'late'|'short'|'pinned' }],
 *           supply: [{ kind: 'on_hand'|'spo'|'po', ref, warehouse_code, date,
 *                      bought_for, qty, free_qty, overdue,
 *                      assigned_to: [{ so_number, qty }] }]
 *         }
 *
 *      `demand` = the lines whose required date falls in that month, or every TBA /
 *      undated line for those two keys. `supply` = the events dated in that month:
 *      on hand by bin for the current month, an SPO at its arrival, a PO line at
 *      `issue + lead` (R29) carrying its `expected_date` as `bought_for` (display
 *      only, R30). An event whose arrival has passed with nothing received is listed
 *      with `overdue: true` and counted as nothing (R31), so its `free_qty` is 0.
 *
 *      The drill FOOTS with the cell that opened it (R37): `sum(free_qty)` less
 *      `sum(short_qty)` over these rows IS that month's balance, which is what the two
 *      tab footers print. `short_qty` is what a line went short of on its own date, so a
 *      `late` line ends covered and still carries one.
 *
 * 3) Export (AC-12 to AC-18, Phase 2 net-new)
 *
 *      POST /api/v1/project-sales/stock-debt/export
 *          { query?, group?, only_debt?, cutoff?, supplier_id?, book?, split }
 *
 *      -> 201 MyDownload (`status: 'pending'`, `kind: 'stock_debt_xlsx'`) - a
 *         `user_downloads` row; `generate_stock_debt_xlsx` runs on the `imports`
 *         queue and the workbook is fetched later from My Downloads, once the
 *         worker marks the row ready. Same pipeline as the low stock report
 *         (`exportLowStockReport` in `summaryOrderService.ts`), a different route
 *         because this screen has its own filters and its own `split`, not a
 *         `run_id` off a reorder run.
 *      -> 422 above `MAX_LOW_STOCK_ROWS` rows, same reason and same cap as the
 *         low stock report; nothing is written.
 *
 * The shapes are typed field for field in `types/stockDebt.types.ts`; they are not
 * restated here, so the two cannot drift.
 *
 * ── PERMISSION ──────────────────────────────────────────────────────────────
 * `projects.stock_debt.view` PRESUMES `projects.projects.view`. The page sits under
 * `app/(protected)/project-sales/layout.tsx`, which gates every child of the section
 * on `projects.projects.view`, and `RequireAccess` takes ONE permission - it has no
 * any-of mode, and building one for a single caller is machinery nobody has asked for
 * yet. Migration 443's sweep grants `stock_debt.view` to exactly the roles that hold
 * `projects.view`, so the presumption holds for every role that can reach the entry;
 * recorded in the UAC as AC-S2-8. The trigger for an any-of gate is the first role that
 * needs Stock Debt WITHOUT the section it lives in.
 *
 * ── ERROR SHAPE ─────────────────────────────────────────────────────────────
 * The standard `AppException` envelope the global handler in `app/main.py`
 * serialises, read with `extractApiError(res, fallback)` and surfaced as an `Error`
 * message - which is what the page's error state renders beside its Retry.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { MyDownload } from '@/services/myDownloadsService';
import type {
  StockDebtBook,
  StockDebtCell,
  StockDebtExportPreview,
  StockDebtExportSplit,
  StockDebtListResponse,
  StockDebtRow,
  StockDebtSupplierOption,
} from '../types/stockDebt.types';

/** Phase 1 -> Phase 2 switch (see the header). Flip to `false` once the backend in
 *  AC-1 to AC-18 ships, and delete the branch it guards below. */
export const USE_STOCK_DEBT_FILTER_MOCKS = true;

/** What the board asks for: a page, a needle, a group, the book, a supplier, a
 *  cutoff and the debt-only switch. */
export interface StockDebtListParams {
  pageIndex: number;
  pageSize: number;
  query: string;
  /** Ownership group, or '' for every group. Ignored while `book === 'retail'` (AC-8). */
  group: string;
  onlyDebt: boolean;
  /** `all` (default) / `project` / `retail` (R1, AC-8). */
  book: StockDebtBook;
  /** A supplier id, `'none'` for "no supplier", or '' for every supplier (R3, AC-4). */
  supplierId: string;
  /** `YYYY-MM-DD`, or null for no cutoff (R2, AC-1/AC-2/AC-3). */
  cutoff: string | null;
}

/** The list params minus paging, plus the workbook split - what `exportStockDebt` sends. */
export interface StockDebtExportParams {
  query: string;
  group: string;
  onlyDebt: boolean;
  book: StockDebtBook;
  supplierId: string;
  cutoff: string | null;
  split: StockDebtExportSplit;
}

/**
 * The month x product board (AC-S2-6, AC-1 to AC-9). Phase 1: `mockStockDebtList` (see
 * the header's Phase-1 section).
 */
export async function getStockDebtList(
  params: StockDebtListParams,
): Promise<StockDebtListResponse> {
  if (USE_STOCK_DEBT_FILTER_MOCKS) return mockStockDebtList(params);

  const search = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      searchQuery: params.query,
    },
    {
      group: params.group,
      only_debt: params.onlyDebt,
      book: params.book === 'all' ? '' : params.book,
      supplier_id: params.supplierId,
      cutoff: params.cutoff ?? '',
    },
  );
  const res = await apiFetch(`/api/v1/project-sales/stock-debt?${search}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load stock debt'));
  return (await res.json()) as StockDebtListResponse;
}

/**
 * The demand and supply behind one cell (AC-S2-7). `month` is `YYYY-MM`, `tba`,
 * `undated` or `unlocated`; `group` is the board's own narrowing, passed through so the
 * drill is recomputed over the same span the cell was.
 *
 * NOT extended with `cutoff` / `book` in this lane's Phase 1 (see the header) - that is
 * AC-11, landing with the rest of the backend in Phase 2.
 */
export async function getStockDebtCell(
  productId: string,
  month: string,
  group?: string,
): Promise<StockDebtCell> {
  const search = new URLSearchParams({ month });
  if (group) search.set('group', group);
  const res = await apiFetch(
    `/api/v1/project-sales/stock-debt/${encodeURIComponent(productId)}/cell?${search}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the cell'));
  return (await res.json()) as StockDebtCell;
}

/**
 * Starts the workbook export through My Downloads (R10/R12, AC-12 to AC-18, AC-33/AC-34).
 * Mocked unconditionally (see the header): AC-12's route does not exist until Phase 2, so
 * there is no real branch to fall back to yet. Returns a `MyDownload` row shaped exactly
 * like the low stock report's (`exportLowStockReport` in `summaryOrderService.ts`) so the
 * same drawer / toast plumbing serves both.
 */
export async function exportStockDebt(params: StockDebtExportParams): Promise<MyDownload> {
  if (USE_STOCK_DEBT_FILTER_MOCKS) return mockExportStockDebt(params);

  const res = await apiFetch('/api/v1/project-sales/stock-debt/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: params.query || undefined,
      group: params.group || undefined,
      only_debt: params.onlyDebt,
      book: params.book,
      supplier_id: params.supplierId || undefined,
      cutoff: params.cutoff ?? undefined,
      split: params.split,
    }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start the stock debt export'));
  return (await res.json()) as MyDownload;
}

// ============================================================================
// Phase 1 mock data (see the header). Deleted, along with the two branches
// above, once Phase 2 ships.
// ============================================================================

const MOCK_SUPPLIERS: StockDebtSupplierOption[] = [
  { id: 'sup-guangdong', name: 'Guangdong Sanitary Co' },
  { id: 'sup-foshan', name: 'Foshan Ceramics' },
  { id: 'sup-kohler', name: 'Kohler Asia' },
];

const MOCK_GROUPS = ['BB', 'IB', 'PJ'];
const MOCK_MONTHS = ['2026-09', '2026-10', '2026-11', '2026-12'];
const MOCK_TBA_MONTH = '2027-06';

interface MockRowSeed {
  code: string;
  name: string | null;
  book: 'project' | 'retail';
  group: string;
  /** One balance per `MOCK_MONTHS` entry, in order. */
  balances: number[];
  tba: number;
  undated: number;
  unlocated: number;
  supplierIndex: number | null;
  category: string | null;
}

const MOCK_SEEDS: MockRowSeed[] = [
  {
    code: 'SRTWB242',
    name: 'Sorento basin 242',
    book: 'project',
    group: 'BB',
    balances: [55, -16, -652, 40],
    tba: -100,
    undated: -12,
    unlocated: -7,
    supplierIndex: 0,
    category: 'BASIN',
  },
  {
    code: 'SRTWC118',
    name: null,
    book: 'project',
    group: 'IB',
    balances: [-30, -18, 22, 0],
    tba: 0,
    undated: -5,
    unlocated: 0,
    supplierIndex: 1,
    category: 'WC',
  },
  {
    code: 'SRTTP305',
    name: 'Sorento single lever tap',
    book: 'project',
    group: 'BB',
    balances: [12, 8, -4, -9],
    tba: -20,
    undated: 0,
    unlocated: 0,
    supplierIndex: null,
    category: 'TAP',
  },
  {
    code: 'SRTAC090',
    name: null,
    book: 'retail',
    group: 'PJ',
    balances: [-2, -14, -6, 5],
    tba: 0,
    undated: 0,
    unlocated: -3,
    supplierIndex: 2,
    category: 'ACC',
  },
  {
    code: 'SRTWB255',
    name: 'Sorento basin 255',
    book: 'retail',
    group: 'PJ',
    balances: [0, 0, -1, 0],
    tba: 0,
    undated: 0,
    unlocated: 0,
    supplierIndex: 0,
    category: 'BASIN',
  },
  {
    code: 'SRTWC120',
    name: 'Sorento close-couple WC',
    book: 'project',
    group: 'IB',
    balances: [-8, -8, -8, -8],
    tba: -40,
    undated: -2,
    unlocated: 0,
    supplierIndex: 1,
    category: 'WC',
  },
  {
    code: 'SRTTP310',
    name: null,
    book: 'project',
    group: 'BB',
    balances: [3, 3, 3, 3],
    tba: 0,
    undated: 0,
    unlocated: 0,
    supplierIndex: null,
    category: 'TAP',
  },
];

function mockRowTotal(row: Omit<StockDebtRow, 'total'>): number {
  return (
    row.months.reduce((sum, month) => sum + month.balance, 0) +
    row.tba +
    row.undated +
    row.unlocated
  );
}

function toneFor(balance: number): 'red' | 'amber' | 'green' {
  // The real tone depends on lead time (`supply_assignment.tone_for`); the mock only
  // needs to exercise all three colours, so a fixed split is enough for Phase 1 screens.
  if (balance >= 0) return 'green';
  return balance <= -50 ? 'red' : 'amber';
}

function buildMockRow(seed: MockRowSeed, productId: string): StockDebtRow {
  const months = MOCK_MONTHS.map((key, index) => ({
    key,
    balance: seed.balances[index] ?? 0,
    tone: toneFor(seed.balances[index] ?? 0),
  }));
  const supplier = seed.supplierIndex === null ? null : MOCK_SUPPLIERS[seed.supplierIndex];
  const base: Omit<StockDebtRow, 'total'> = {
    product_id: productId,
    product_code: seed.code,
    // AC-9: null when it equals the code - none of the seeds above do, but the guard
    // stays here rather than only in the UI, so the mock and the eventual backend agree.
    product_name: seed.name === seed.code ? null : seed.name,
    months,
    tba: seed.tba,
    undated: seed.undated,
    unlocated: seed.unlocated,
    supplier_id: supplier?.id ?? null,
    supplier_name: supplier?.name ?? null,
    category_code: seed.category,
  };
  return { ...base, total: mockRowTotal(base) };
}

/** `2026-11-30` -> `2026-11`, for trimming the axis and the demand at a cutoff (R2, A2). */
function monthOf(dateIso: string): string {
  return dateIso.slice(0, 7);
}

function mockStockDebtList(params: StockDebtListParams): StockDebtListResponse {
  const cutoffMonth = params.cutoff ? monthOf(params.cutoff) : null;
  const axis = cutoffMonth ? MOCK_MONTHS.filter((key) => key <= cutoffMonth) : MOCK_MONTHS;
  const tbaMonth = MOCK_TBA_MONTH;
  // A3: TBA is dated on or after `tba_date_from`, so a cutoff before it drops the whole
  // bucket; undated and unlocated demand have no date to test and are never dropped.
  const tbaDroppedByCutoff = Boolean(cutoffMonth && tbaMonth > cutoffMonth);

  let rows = MOCK_SEEDS.map((seed, index) => buildMockRow(seed, `mock-${index + 1}`)).map(
    (row, index) => {
      const seed = MOCK_SEEDS[index];
      const trimmedMonths = row.months.filter((month) => axis.includes(month.key));
      const tba = tbaDroppedByCutoff ? 0 : row.tba;
      const total =
        trimmedMonths.reduce((sum, month) => sum + month.balance, 0) +
        tba +
        row.undated +
        row.unlocated;
      return { row: { ...row, months: trimmedMonths, tba, total }, seed };
    },
  );

  if (params.book !== 'all') {
    rows = rows.filter((entry) => entry.seed.book === params.book);
  }
  if (params.group && params.book !== 'retail') {
    rows = rows.filter((entry) => entry.seed.book !== 'project' || entry.seed.group === params.group);
  }
  if (params.supplierId === 'none') {
    rows = rows.filter((entry) => entry.row.supplier_id === null);
  } else if (params.supplierId) {
    rows = rows.filter((entry) => entry.row.supplier_id === params.supplierId);
  }
  if (params.query.trim()) {
    const needle = params.query.trim().toLowerCase();
    rows = rows.filter(
      (entry) =>
        entry.row.product_code.toLowerCase().includes(needle) ||
        (entry.row.product_name ?? '').toLowerCase().includes(needle),
    );
  }
  if (params.onlyDebt) {
    rows = rows.filter(
      (entry) =>
        entry.row.months.some((month) => month.balance < 0) ||
        entry.row.tba < 0 ||
        entry.row.undated < 0 ||
        entry.row.unlocated < 0,
    );
  }

  rows.sort((a, b) => a.row.product_code.localeCompare(b.row.product_code));

  const filtered = rows.map((entry) => entry.row);
  const totalsMonths: Record<string, number> = {};
  axis.forEach((key) => {
    totalsMonths[key] = filtered.reduce(
      (sum, row) => sum + (row.months.find((month) => month.key === key)?.balance ?? 0),
      0,
    );
  });
  const totals = {
    months: totalsMonths,
    tba: filtered.reduce((sum, row) => sum + row.tba, 0),
    undated: filtered.reduce((sum, row) => sum + row.undated, 0),
    unlocated: filtered.reduce((sum, row) => sum + row.unlocated, 0),
    total: filtered.reduce((sum, row) => sum + row.total, 0),
  };
  const suppliers = MOCK_SUPPLIERS.filter((supplier) =>
    filtered.some((row) => row.supplier_id === supplier.id),
  ).sort((a, b) => a.name.localeCompare(b.name));

  const start = params.pageIndex * params.pageSize;
  const page = filtered.slice(start, start + params.pageSize);

  return {
    data: page,
    pagination: { total: filtered.length, page: params.pageIndex + 1, limit: params.pageSize },
    months: axis,
    tba_month: tbaMonth,
    groups: MOCK_GROUPS,
    totals,
    suppliers,
    sheet_counts: mockSheetCounts(filtered),
  };
}

/**
 * The exact export sheet counts over the WHOLE filtered set (AC-7b) - none-buckets
 * ("No supplier" / "No category") counted only when at least one row actually has none,
 * and `supplier_category` counted as the distinct PAIRS present, not suppliers times
 * categories (a pair with no row does not get a sheet).
 */
function mockSheetCounts(filtered: StockDebtRow[]): {
  supplier: number;
  category: number;
  supplier_category: number;
} {
  const supplierKeys = new Set(filtered.map((row) => row.supplier_id ?? '__none__'));
  const categoryKeys = new Set(filtered.map((row) => row.category_code ?? '__none__'));
  const pairKeys = new Set(
    filtered.map((row) => `${row.supplier_id ?? '__none__'}||${row.category_code ?? '__none__'}`),
  );
  return {
    supplier: supplierKeys.size,
    category: categoryKeys.size,
    supplier_category: pairKeys.size,
  };
}

let mockDownloadSeq = 0;

function mockExportStockDebt(params: StockDebtExportParams): Promise<MyDownload> {
  mockDownloadSeq += 1;
  const now = new Date().toISOString();
  const download: MyDownload = {
    id: `mock-stock-debt-download-${mockDownloadSeq}`,
    kind: 'stock_debt_xlsx',
    status: 'pending',
    filename: `stock-debt-${params.split}.xlsx`,
    created_at: now,
    ready_at: null,
  };
  return Promise.resolve(download);
}

/**
 * The export popover's preview (AC-33) - never a network call of its own: both fields are
 * already whole-filtered-set, envelope-level values (`pagination.total`, AC-6; `sheet_counts`,
 * AC-7b), so reading them here is exact, not a guess - `split=none` is the only case not
 * carried on the envelope, because it is always exactly one sheet.
 */
export function previewStockDebtExport(
  envelope: StockDebtListResponse | undefined,
  split: StockDebtExportSplit,
): StockDebtExportPreview {
  const rows = envelope?.pagination.total ?? 0;
  if (!envelope || rows === 0) return { rows: 0, sheets: 0 };

  switch (split) {
    case 'none':
      return { rows, sheets: 1 };
    case 'supplier':
      return { rows, sheets: envelope.sheet_counts.supplier };
    case 'category':
      return { rows, sheets: envelope.sheet_counts.category };
    case 'supplier_category':
      return { rows, sheets: envelope.sheet_counts.supplier_category };
    default:
      return { rows, sheets: 1 };
  }
}
