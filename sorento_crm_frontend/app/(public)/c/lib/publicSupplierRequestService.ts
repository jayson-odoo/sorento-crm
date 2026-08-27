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
 *     -> { supplier_name, requested_at, line_count, lines[], has_pdf, has_xlsx }
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

export interface SupplierRequest {
  supplier_name: string;
  requested_at: string;
  line_count: number;
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
