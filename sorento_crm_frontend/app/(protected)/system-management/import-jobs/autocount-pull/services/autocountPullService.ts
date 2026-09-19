/**
 * AutoCount pull + review - feature service.
 * Layering: components -> hooks (useAutocountPull) -> THIS service -> lib/api-client -> backend.
 * Routes (once SR1 ships them): `documentation/plans/autocount/PLAN-autocount-pull-review.md`
 * "Routes" table, prefix `/api/v1/autocount/pulls`.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, codedError, extractApiError, type CodedError } from '@/lib/api-client';
import { generateExcelFile, type ColumnOption } from '@/lib/excel-utils';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  AutocountComparePullResult,
  AutocountCompareDifference,
  AutocountPull,
  AutocountPullCompareSummary,
  AutocountPullCounts,
  AutocountPullEntity,
  AutocountPullExcelRow,
  AutocountPullPhase,
  AutocountPullRowsQuery,
  ProductExcelRow,
  ProductPullCounts,
  StockExcelRow,
  StockPullCounts,
} from '../types/autocountPull.types';

import productsHeaderReady from '../__mocks__/products-header-ready.json';
import productsHeaderBuilding from '../__mocks__/products-header-building.json';
import productsRowsPage1 from '../__mocks__/products-rows-page1.json';
import stockHeaderReady from '../__mocks__/stock-header-ready.json';
import stockRowsPage1 from '../__mocks__/stock-rows-page1.json';
import snapshotFailed from '../__mocks__/snapshot-failed.json';

/**
 * ── Phase 1 mock - deleted in SR2 ───────────────────────────────────────────────────
 * Everything gated behind `USE_MOCK` below simulates FoundryX and the (not-yet-built)
 * Sorento pull routes against the fixtures FoundryX committed
 * (`documentation/plans/sprint-5/10-fixtures/` in `foundryx-shared-service`, copied into
 * `../__mocks__/`), so the review screens can be built and browser-verified before SR1
 * ships a backend. SR2 flips this to `false` and deletes the mock branch; every function
 * below already has the real-request branch it falls through to.
 * ────────────────────────────────────────────────────────────────────────────────────
 */
const USE_MOCK = true;

/**
 * Phase 1 mock: `master_data.products.autocount_pull` / `inventory.stock.autocount_pull` are
 * seeded by SR1's migration and do not exist in the database yet, so a real
 * `useHasPermission` check can only ever say "denied" today. The two list toolbars OR this
 * into their gate so the button is reachable for a browser pass; it tracks `USE_MOCK` and
 * collapses to just the real permission check the moment SR2 flips it off.
 */
export function hasAutocountPullPermissionMock(): boolean {
  return USE_MOCK;
}

// ---- Raw fixture shapes (only the fields this service reads) --------------------------

interface RawProductRow {
  source_ref: string;
  code: string;
  name: string;
  description: string;
  category_code?: string;
  brand_code?: string;
  list_price: string;
  is_active: boolean;
}

interface RawStockRow {
  source_ref: string;
  item_code: string;
  item_description: string;
  location_code: string;
  uom_code?: string;
  qty: number;
}

interface ProductsHeaderFixture {
  recordCount: number;
  extractedAt: string;
  expiresAt: string;
  zeroListPriceCount: number;
  negativeListPriceCount: number;
  excludedRows: unknown[];
}

interface ProductsHeaderBuildingFixture {
  progress?: { pagesDone: number; pagesTotal: number; stage?: string };
}

interface StockHeaderFixture {
  recordCount: number;
  extractedAt: string;
  expiresAt: string;
  negativePairs: number;
  zeroPairs: number;
  excludedCount: number;
  excludedNonzeroCount: number;
}

interface SnapshotFailedFixture {
  error: { code: string; message: string };
}

const PRODUCTS_HEADER = productsHeaderReady as unknown as ProductsHeaderFixture;
const PRODUCTS_HEADER_BUILDING = productsHeaderBuilding as unknown as ProductsHeaderBuildingFixture;
const STOCK_HEADER = stockHeaderReady as unknown as StockHeaderFixture;
const SNAPSHOT_FAILED = snapshotFailed as unknown as SnapshotFailedFixture;
const PRODUCT_RAW_ROWS = productsRowsPage1.rows as unknown as RawProductRow[];
const STOCK_RAW_ROWS = stockRowsPage1.rows as unknown as RawStockRow[];

// ---- Fixture -> Excel-view shape (AC-RV-3's mapping, done once at module load) --------

/** Description = `name`; Desc 2 = the remainder of `description` after `name`, trimmed,
 *  empty when they are equal (AC-RV-3). AutoCount's raw join always leads with `name`. */
function splitDescription(name: string, description: string): { description: string; desc2: string } {
  const trimmedName = name.trim();
  const trimmedDescription = description.trim();
  if (trimmedDescription === trimmedName) return { description: trimmedName, desc2: '' };
  if (trimmedDescription.startsWith(trimmedName)) {
    return { description: trimmedName, desc2: trimmedDescription.slice(trimmedName.length).trim() };
  }
  return { description: trimmedDescription, desc2: '' };
}

function buildProductExcelRows(): ProductExcelRow[] {
  return PRODUCT_RAW_ROWS.map((row) => {
    const { description, desc2 } = splitDescription(row.name, row.description);
    return {
      item_code: row.code,
      description,
      desc_2: desc2,
      item_group: row.category_code ?? '',
      item_brand: row.brand_code ?? '',
      price: Number(row.list_price),
      is_active: row.is_active,
    };
  });
}

function buildStockExcelRows(): StockExcelRow[] {
  // The fixture's row page is a 10-row SAMPLE of the real 12,133-row snapshot (see
  // `__mocks__` README in the FoundryX source) - `rows.length` never equals the header's
  // `recordCount`. Only these 10 are shown/paged in the mock, which is expected.
  return STOCK_RAW_ROWS.map((row) => ({
    item_code: row.item_code,
    item_description: row.item_description,
    location: row.location_code,
    on_hand_qty: row.qty,
  }));
}

const PRODUCT_EXCEL_ROWS = buildProductExcelRows();
const STOCK_EXCEL_ROWS = buildStockExcelRows();

// ---- In-memory pull registry (session-only; lost on a hard reload) --------------------

interface MockPullRecord {
  jobId: string;
  entity: AutocountPullEntity;
  companyCode: string;
  createdAt: number;
  /** Canned demo ids skip the elapsed-time timeline and sit at one phase always. */
  fixedPhase?: AutocountPullPhase;
  confirmed: boolean;
  applyJobId: string | null;
  compare: AutocountPullCompareSummary | null;
  confirmBlockedReason: string | null;
  errorMessage: string | null;
}

const BUILDING_MS = 6000;
const PREVIEWING_UNTIL_MS = 9000;

const mockRegistry = new Map<string, MockPullRecord>();
const openPullByEntity = new Map<AutocountPullEntity, string>();

/**
 * Fixed demo ids reachable without clicking Pull, so a browser pass can land on every
 * state directly: `mock-pull-products-building` (live building -> previewing -> review
 * timeline, starts on first read), `-review`, `-confirmed`, `-failed`, `-expired`, and the
 * stock equivalents plus `mock-pull-stock-blocked` (Confirm disabled, AC-SP-1).
 */
const CANNED_JOBS: Record<string, Omit<MockPullRecord, 'jobId' | 'createdAt'>> = {
  'mock-pull-products-building': { entity: 'products', companyCode: 'SRT', confirmed: false, applyJobId: null, compare: null, confirmBlockedReason: null, errorMessage: null },
  'mock-pull-products-review': { entity: 'products', companyCode: 'SRT', fixedPhase: 'review', confirmed: false, applyJobId: null, compare: null, confirmBlockedReason: null, errorMessage: null },
  'mock-pull-products-confirmed': { entity: 'products', companyCode: 'SRT', fixedPhase: 'review', confirmed: true, applyJobId: 'mock-apply-products-demo', compare: null, confirmBlockedReason: null, errorMessage: null },
  'mock-pull-products-failed': { entity: 'products', companyCode: 'SRT', fixedPhase: 'failed', confirmed: false, applyJobId: null, compare: null, confirmBlockedReason: null, errorMessage: SNAPSHOT_FAILED.error.message },
  'mock-pull-products-expired': { entity: 'products', companyCode: 'SRT', fixedPhase: 'expired', confirmed: false, applyJobId: null, compare: null, confirmBlockedReason: null, errorMessage: 'This pull took too long to build. Pull again.' },
  'mock-pull-stock-review': { entity: 'stock_balances', companyCode: 'SRT', fixedPhase: 'review', confirmed: false, applyJobId: null, compare: null, confirmBlockedReason: null, errorMessage: null },
  'mock-pull-stock-blocked': { entity: 'stock_balances', companyCode: 'SRT', fixedPhase: 'review', confirmed: false, applyJobId: null, compare: null, confirmBlockedReason: 'AutoCount sent rows with a real quantity Sorento could not place as stock. Pull again.', errorMessage: null },
  'mock-pull-stock-confirmed': { entity: 'stock_balances', companyCode: 'SRT', fixedPhase: 'review', confirmed: true, applyJobId: 'mock-apply-stock-demo', compare: null, confirmBlockedReason: null, errorMessage: null },
};

function newJobId(entity: AutocountPullEntity): string {
  const slug = entity === 'products' ? 'products' : 'stock';
  return `mock-pull-${slug}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function entityOfMockJobId(jobId: string): AutocountPullEntity {
  return jobId.includes('stock') ? 'stock_balances' : 'products';
}

function ensureRecord(jobId: string): MockPullRecord | null {
  const existing = mockRegistry.get(jobId);
  if (existing) return existing;
  const canned = CANNED_JOBS[jobId];
  if (!canned) return null;
  const record: MockPullRecord = { ...canned, jobId, createdAt: Date.now() };
  mockRegistry.set(jobId, record);
  return record;
}

function resolvePhase(record: MockPullRecord): AutocountPullPhase {
  if (record.confirmed) return 'confirmed';
  if (record.fixedPhase) return record.fixedPhase;
  const elapsed = Date.now() - record.createdAt;
  if (elapsed < BUILDING_MS) return 'building';
  if (elapsed < PREVIEWING_UNTIL_MS) return 'previewing';
  return 'review';
}

function countsFor(entity: AutocountPullEntity): AutocountPullCounts {
  if (entity === 'products') {
    const counts: ProductPullCounts = {
      received: PRODUCTS_HEADER.recordCount,
      new: PRODUCTS_HEADER.recordCount,
      changed: 0,
      unchanged: 0,
      failed: 0,
      left_out: PRODUCTS_HEADER.excludedRows.length,
      price_to_zero: PRODUCTS_HEADER.zeroListPriceCount,
    };
    return counts;
  }
  // Warehouse-active classification (AC-SP-2) needs a company's warehouse list, which this
  // Phase 1 mock has no backend to join against - `fed` stands in with the sample rows this
  // mock can actually show; the rest are 0 until SR4 wires the real classification.
  const counts: StockPullCounts = {
    received: STOCK_HEADER.recordCount,
    fed: STOCK_EXCEL_ROWS.length,
    not_applied_inactive: 0,
    not_applied_unknown: 0,
    qty_changes: 0,
    set_to_zero: 0,
    skipped_product_not_found: 0,
    negative_in_autocount: STOCK_HEADER.negativePairs,
  };
  return counts;
}

function toAutocountPull(record: MockPullRecord): AutocountPull {
  const phase = resolvePhase(record);
  const inReview = phase === 'review' || phase === 'confirmed';
  const isDead = phase === 'failed' || phase === 'expired';
  const header = record.entity === 'products' ? PRODUCTS_HEADER : STOCK_HEADER;
  return {
    job_id: record.jobId,
    entity: record.entity,
    company_code: record.companyCode,
    phase,
    progress: phase === 'building' ? (PRODUCTS_HEADER_BUILDING.progress ?? { pagesDone: 2, pagesTotal: 4 }) : null,
    extracted_at: inReview ? header.extractedAt : null,
    expires_at: inReview ? header.expiresAt : null,
    counts: inReview ? countsFor(record.entity) : null,
    confirm_blocked_reason: inReview && !record.confirmed ? record.confirmBlockedReason : null,
    compare: record.compare,
    apply_job_id: record.applyJobId,
    error_message: isDead ? (record.errorMessage ?? 'The pull failed.') : null,
  };
}

/**
 * Phase 1 scaffolding only, called from `importJobService.getImportJob` so the generic
 * import job detail page (Job Summary / Results cards) has something to render for a
 * mocked pull id it does not otherwise know about. Returns `null` once `USE_MOCK` flips
 * off in SR2, so a real id is never affected.
 */
export function mockImportJobShim(jobId: string): { job_type: string; status: string } | null {
  if (!USE_MOCK || !jobId.startsWith('mock-pull-')) return null;
  const record = ensureRecord(jobId);
  if (!record) return null;
  const phase = resolvePhase(record);
  const status =
    phase === 'building' ? 'pending' : phase === 'previewing' ? 'started' : isDeadPhase(phase) ? 'failed' : 'finished';
  return {
    job_type: record.entity === 'products' ? 'autocount_products_pull' : 'autocount_stock_pull',
    status,
  };
}

function isDeadPhase(phase: AutocountPullPhase): boolean {
  return phase === 'failed' || phase === 'expired';
}

// ---- Compare (mirrors, best-effort, the manual import's own rules) --------------------

function normalizeCode(value: unknown): string {
  return String(value ?? '').trim().toUpperCase();
}

function parseIsActive(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  const text = String(value ?? '').trim().toLowerCase();
  if (!text) return true;
  return !['f', 'false', '0', 'no', 'n', 'inactive'].includes(text);
}

function parsePrice(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return 0;
  return n;
}

function joinDescription(description: unknown, desc2: unknown): string {
  const base = String(description ?? '').trim();
  const extra = String(desc2 ?? '').trim();
  return extra ? `${base} ${extra}`.trim() : base;
}

function compareProducts(fileRows: Record<string, unknown>[]): AutocountComparePullResult {
  const pullByCode = new Map(PRODUCT_RAW_ROWS.map((row) => [normalizeCode(row.code), row]));
  const seen = new Set<string>();
  let matched = 0;
  const differences: AutocountCompareDifference[] = [];

  for (const fileRow of fileRows) {
    const code = normalizeCode(fileRow['Item Code']);
    if (!code) continue;
    seen.add(code);
    const pullRow = pullByCode.get(code);
    if (!pullRow) {
      differences.push({ item_code: code, field: 'Only in your Excel', your_excel: code, autocount_pull: 'not in the pull' });
      continue;
    }
    const rowDiffs: AutocountCompareDifference[] = [];
    const fileDescription = joinDescription(fileRow['Description'], fileRow['Desc 2']);
    if (fileDescription !== String(pullRow.description ?? '').trim()) {
      rowDiffs.push({ item_code: code, field: 'Description', your_excel: fileDescription, autocount_pull: pullRow.description });
    }
    const fileGroup = String(fileRow['Item Group'] ?? '').trim();
    if (fileGroup !== String(pullRow.category_code ?? '').trim()) {
      rowDiffs.push({ item_code: code, field: 'Item Group', your_excel: fileGroup, autocount_pull: pullRow.category_code ?? '' });
    }
    const fileBrand = String(fileRow['Item Brand'] ?? '').trim();
    if (fileBrand !== String(pullRow.brand_code ?? '').trim()) {
      rowDiffs.push({ item_code: code, field: 'Item Brand', your_excel: fileBrand, autocount_pull: pullRow.brand_code ?? '' });
    }
    const filePrice = parsePrice(fileRow['Price']);
    const pullPrice = parsePrice(pullRow.list_price);
    if (filePrice !== pullPrice) {
      rowDiffs.push({ item_code: code, field: 'Price', your_excel: filePrice.toFixed(2), autocount_pull: pullPrice.toFixed(2) });
    }
    const fileActive = parseIsActive(fileRow['Is Active']);
    if (fileActive !== Boolean(pullRow.is_active)) {
      rowDiffs.push({ item_code: code, field: 'Is Active', your_excel: fileActive ? 'T' : 'F', autocount_pull: pullRow.is_active ? 'T' : 'F' });
    }
    if (rowDiffs.length === 0) matched += 1;
    else differences.push(...rowDiffs);
  }

  const onlyInPull = [...pullByCode.keys()].filter((code) => !seen.has(code));
  for (const code of onlyInPull) {
    differences.push({ item_code: code, field: 'Only in AutoCount', your_excel: 'not in your Excel', autocount_pull: code });
  }

  const onlyInExcelCount = differences.filter((d) => d.field === 'Only in your Excel').length;
  const onlyInPullCount = onlyInPull.length;
  const differentCount = differences.length - onlyInExcelCount - onlyInPullCount;

  return {
    summary: {
      filename: '',
      compared_at: new Date().toISOString(),
      total: seen.size + onlyInPull.length,
      matched,
      different: differentCount,
      only_in_excel: onlyInExcelCount,
      only_in_pull: onlyInPullCount,
    },
    differences,
  };
}

function compareStock(fileRows: Record<string, unknown>[]): AutocountComparePullResult {
  const key = (code: unknown, loc: unknown) => `${normalizeCode(code)}|${normalizeCode(loc)}`;
  const pullByKey = new Map(STOCK_RAW_ROWS.map((row) => [key(row.item_code, row.location_code), row]));
  const seen = new Set<string>();
  let matched = 0;
  let qtyTotalExcel = 0;
  let qtyTotalPull = 0;
  const differences: AutocountCompareDifference[] = [];

  for (const fileRow of fileRows) {
    const code = fileRow['Item Code'];
    const loc = fileRow['Location'];
    if (!normalizeCode(code)) continue;
    const k = key(code, loc);
    seen.add(k);
    const fileQty = Math.round(Number(fileRow['On Hand Qty']) || 0);
    qtyTotalExcel += fileQty;
    const pullRow = pullByKey.get(k);
    if (!pullRow) {
      differences.push({ item_code: normalizeCode(code), location: normalizeCode(loc), field: 'Only in your Excel', your_excel: String(fileQty), autocount_pull: 'not in the pull' });
      continue;
    }
    const pullQty = Math.round(Number(pullRow.qty) || 0);
    qtyTotalPull += pullQty;
    if (fileQty !== pullQty) {
      differences.push({ item_code: normalizeCode(code), location: normalizeCode(loc), field: 'On Hand Qty', your_excel: String(fileQty), autocount_pull: String(pullQty) });
    } else {
      matched += 1;
    }
  }

  const onlyInPullKeys = [...pullByKey.keys()].filter((k) => !seen.has(k));
  for (const k of onlyInPullKeys) {
    const row = pullByKey.get(k)!;
    const pullQty = Math.round(Number(row.qty) || 0);
    qtyTotalPull += pullQty;
    differences.push({ item_code: normalizeCode(row.item_code), location: normalizeCode(row.location_code), field: 'Only in AutoCount', your_excel: 'not in your Excel', autocount_pull: String(pullQty) });
  }

  const onlyInExcelCount = differences.filter((d) => d.field === 'Only in your Excel').length;
  const onlyInPullCount = onlyInPullKeys.length;
  const differentCount = differences.length - onlyInExcelCount - onlyInPullCount;

  return {
    summary: {
      filename: '',
      compared_at: new Date().toISOString(),
      total: seen.size + onlyInPullKeys.length,
      matched,
      different: differentCount,
      only_in_excel: onlyInExcelCount,
      only_in_pull: onlyInPullCount,
      qty_total_excel: qtyTotalExcel,
      qty_total_pull: qtyTotalPull,
    },
    differences,
  };
}

// ---- Public service functions ----------------------------------------------------------

export async function startPull(entity: AutocountPullEntity): Promise<AutocountPull> {
  if (USE_MOCK) {
    const openId = openPullByEntity.get(entity);
    if (openId) {
      const existing = ensureRecord(openId);
      if (existing && !isDeadPhase(resolvePhase(existing)) && resolvePhase(existing) !== 'confirmed') {
        return toAutocountPull(existing);
      }
      openPullByEntity.delete(entity);
    }
    const jobId = newJobId(entity);
    const record: MockPullRecord = {
      jobId,
      entity,
      companyCode: 'SRT',
      createdAt: Date.now(),
      confirmed: false,
      applyJobId: null,
      compare: null,
      confirmBlockedReason: null,
      errorMessage: null,
    };
    mockRegistry.set(jobId, record);
    openPullByEntity.set(entity, jobId);
    return toAutocountPull(record);
  }
  const response = await apiFetch('/api/v1/autocount/pulls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity }),
  });
  if (!response.ok) throw await codedError(response, 'Could not start the pull.');
  return response.json();
}

export async function getCurrentPull(entity: AutocountPullEntity): Promise<AutocountPull | null> {
  if (USE_MOCK) {
    const jobId = openPullByEntity.get(entity);
    if (!jobId) return null;
    const record = ensureRecord(jobId);
    if (!record) return null;
    const phase = resolvePhase(record);
    if (isDeadPhase(phase) || phase === 'confirmed') {
      openPullByEntity.delete(entity);
      return null;
    }
    return toAutocountPull(record);
  }
  const response = await apiFetch(`/api/v1/autocount/pulls/current?entity=${encodeURIComponent(entity)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not check for an open pull.'));
  return response.json();
}

export async function getPull(jobId: string): Promise<AutocountPull> {
  if (USE_MOCK) {
    const record = ensureRecord(jobId);
    if (!record) throw new Error('Pull not found.');
    return toAutocountPull(record);
  }
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load the pull.'));
  return response.json();
}

export async function getPullRows(
  jobId: string,
  params: AutocountPullRowsQuery,
): Promise<DataGridApiResponse<AutocountPullExcelRow>> {
  if (USE_MOCK) {
    const record = ensureRecord(jobId);
    const entity = record?.entity ?? entityOfMockJobId(jobId);
    const all: AutocountPullExcelRow[] = entity === 'products' ? PRODUCT_EXCEL_ROWS : STOCK_EXCEL_ROWS;
    const query = (params.query ?? '').trim().toLowerCase();
    const filtered = query ? all.filter((row) => row.item_code.toLowerCase().includes(query)) : all;
    const start = params.pageIndex * params.pageSize;
    const page = filtered.slice(start, start + params.pageSize);
    return {
      data: page,
      empty: filtered.length === 0,
      pagination: { total: filtered.length, page: params.pageIndex + 1 },
    };
  }
  const search = buildDataGridParams({ pageIndex: params.pageIndex, pageSize: params.pageSize, searchQuery: params.query });
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/rows?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load the pull rows.'));
  return response.json();
}

const PRODUCT_XLSX_COLUMNS: ColumnOption[] = [
  { key: 'Item Code', label: 'Item Code', selected: true },
  { key: 'Description', label: 'Description', selected: true },
  { key: 'Desc 2', label: 'Desc 2', selected: true },
  { key: 'Item Group', label: 'Item Group', selected: true },
  { key: 'Item Brand', label: 'Item Brand', selected: true },
  { key: 'Price', label: 'Price', selected: true },
  { key: 'Is Active', label: 'Is Active', selected: true },
  // AC-RV-5: products add a trailing blank UOM column (withheld during the check period).
  { key: 'UOM', label: 'UOM', selected: true },
];

const STOCK_XLSX_COLUMNS: ColumnOption[] = [
  { key: 'Item Code', label: 'Item Code', selected: true },
  { key: 'Item Description', label: 'Item Description', selected: true },
  { key: 'Location', label: 'Location', selected: true },
  { key: 'On Hand Qty', label: 'On Hand Qty', selected: true },
];

export async function downloadPullXlsx(jobId: string): Promise<void> {
  if (USE_MOCK) {
    const record = ensureRecord(jobId);
    const entity = record?.entity ?? entityOfMockJobId(jobId);
    if (entity === 'products') {
      const rows = PRODUCT_EXCEL_ROWS.map((row) => ({
        'Item Code': row.item_code,
        Description: row.description,
        'Desc 2': row.desc_2,
        'Item Group': row.item_group,
        'Item Brand': row.item_brand,
        Price: row.price,
        'Is Active': row.is_active ? 'T' : 'F',
        UOM: '',
      }));
      await generateExcelFile(rows, PRODUCT_XLSX_COLUMNS, `autocount-products-pull-${jobId}.xlsx`);
    } else {
      const rows = STOCK_EXCEL_ROWS.map((row) => ({
        'Item Code': row.item_code,
        'Item Description': row.item_description,
        Location: row.location,
        'On Hand Qty': row.on_hand_qty,
      }));
      await generateExcelFile(rows, STOCK_XLSX_COLUMNS, `autocount-stock-pull-${jobId}.xlsx`);
    }
    return;
  }
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/download.xlsx`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not download the file.'));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `autocount-pull-${jobId}.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function comparePull(
  jobId: string,
  filename: string,
  rows: Record<string, unknown>[],
): Promise<AutocountComparePullResult> {
  if (USE_MOCK) {
    const record = ensureRecord(jobId);
    const entity = record?.entity ?? entityOfMockJobId(jobId);
    const result = entity === 'products' ? compareProducts(rows) : compareStock(rows);
    const summary: AutocountPullCompareSummary = { ...result.summary, filename };
    if (record) record.compare = summary;
    return { summary, differences: result.differences };
  }
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, rows }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not compare the file.'));
  return response.json();
}

export async function confirmPull(jobId: string): Promise<AutocountPull> {
  if (USE_MOCK) {
    const record = ensureRecord(jobId);
    if (!record) throw new Error('Pull not found.');
    if (!record.confirmed) {
      record.confirmed = true;
      record.applyJobId = `mock-apply-${record.entity === 'products' ? 'products' : 'stock'}-${Date.now().toString(36)}`;
      openPullByEntity.delete(record.entity);
    }
    return toAutocountPull(record);
  }
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/confirm`, { method: 'POST' });
  if (!response.ok) throw await codedError(response, 'Could not confirm the pull.');
  return response.json();
}

// ---- Start-error toast text (AC-PL-6) --------------------------------------------------

const START_ERROR_MESSAGES: Record<string, string> = {
  PULL_NOT_ENABLED: 'AutoCount pull is not switched on for this company.',
  PUSH_ACTIVE: 'This book now updates automatically.',
  TOO_MANY_BUILDS: 'A pull was just started. Try again in a minute.',
  NOT_CONFIGURED: 'AutoCount connection is not set up for this company.',
  UNREACHABLE: 'AutoCount could not be reached. Try again.',
};

/** Maps a `startPull` refusal to the one line the button's toast shows (AC-PL-6). 401/403/404
 *  and anything unmapped fall back to the "connection is not set up" text. */
export function startPullErrorMessage(error: unknown): string {
  const code = (error as CodedError | undefined)?.code;
  if (code && START_ERROR_MESSAGES[code]) return START_ERROR_MESSAGES[code];
  return START_ERROR_MESSAGES.NOT_CONFIGURED;
}
