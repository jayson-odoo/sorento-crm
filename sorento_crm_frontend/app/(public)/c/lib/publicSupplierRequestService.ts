/**
 * The supplier's read-only view of a container request we sent them.
 *
 * Deliberately NOT `apiFetch`, for the reason `publicCatalogueService` states and
 * this page shares exactly: `apiFetch` resolves a NextAuth token before every
 * call, and the reader here is a factory in Chaozhou who has no session and never
 * will. A plain relative fetch is what keeps the link openable by them.
 *
 * ---------------------------------------------------------------------------
 * CONTRACT
 *
 * GET /api/v1/public/supplier-request/{token}
 *     -> { supplier_name, requested_at, line_count, sheet, lines[], has_pdf, has_xlsx }
 *
 * GET /api/v1/public/supplier-request/{token}/document/{pdf|xlsx}
 *     -> { url, filename, expires_in }
 *
 * 404 covers "no such token", "expired token" and "superseded by a resend", and
 * it is ONE answer on purpose: telling a caller that a token exists but has
 * expired confirms the token, and this endpoint is public
 * (`project_quotation_document_service.get_issue_by_sign_token`).
 * ---------------------------------------------------------------------------
 */

export interface SupplierRequestLine {
  item_code: string | null;
  product_name: string | null;
  /** What we are asking them to pack. */
  qty: number;
  /** Their own figures, as their last stock list stated them. Null = they never listed it. */
  qty_packed: number | null;
  qty_unfinished: number | null;
}

/**
 * The supplier's own sheet, as the backend's ONE `SheetModel` (R12): their ten columns in
 * their own spellings plus `需装数量 / Qty to load`, their row order, and their merged
 * families as `rowspan`. The xlsx and the PDF are drawn from this same model, which is what
 * makes the three tally.
 */
export interface SupplierRequestSheetColumn {
  /** Their heading, in their own words. */
  label: string;
  /** Ours, as a second line under it. Null for a column we cannot name. */
  label_en: string | null;
}

export interface SupplierRequestSheetCell {
  value: string | number | null;
  rowspan: number;
  colspan: number;
  /** True when a merge starting above or to the left covers this position: draw nothing. */
  covered: boolean;
  /** Their own marks on their own document: a maintained field, and a figure to notice. */
  fill: 'yellow' | null;
  red: boolean;
}

export interface SupplierRequestSheetRow {
  cells: SupplierRequestSheetCell[];
  /** How many rows this product family covers; 0 on a row that continues one. */
  family_span: number;
  /** True for a line we added because their list never named the product. */
  appended: boolean;
}

export interface SupplierRequestSheet {
  title: string | null;
  columns: SupplierRequestSheetColumn[];
  rows: SupplierRequestSheetRow[];
  totals: SupplierRequestSheetRow | null;
}

export interface SupplierRequest {
  supplier_name: string;
  requested_at: string;
  line_count: number;
  sheet: SupplierRequestSheet | null;
  /** The flat form, kept for links issued before the sheet existed. */
  lines: SupplierRequestLine[];
  has_pdf: boolean;
  has_xlsx: boolean;
}

export interface SupplierRequestDocument {
  url: string;
  filename: string | null;
}

export class SupplierRequestUnavailableError extends Error {
  constructor() {
    super('This link is no longer available');
    this.name = 'SupplierRequestUnavailableError';
  }
}

function apiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  return env ? env.replace(/\/$/, '') : '';
}

function path(token: string): string {
  return `/api/v1/public/supplier-request/${encodeURIComponent(token)}`;
}

export async function readSupplierRequest(token: string): Promise<SupplierRequest> {
  const response = await fetch(`${apiBase()}${path(token)}`, { cache: 'no-store' });

  if (response.status === 404) throw new SupplierRequestUnavailableError();
  if (!response.ok) throw new Error('This request could not be loaded right now.');

  return (await response.json()) as SupplierRequest;
}

export async function readSupplierRequestDocument(
  token: string,
  kind: 'pdf' | 'xlsx',
): Promise<SupplierRequestDocument> {
  const response = await fetch(`${apiBase()}${path(token)}/document/${kind}`, {
    cache: 'no-store',
  });

  if (response.status === 404) throw new SupplierRequestUnavailableError();
  if (!response.ok) throw new Error('This file could not be downloaded right now.');

  return (await response.json()) as SupplierRequestDocument;
}
