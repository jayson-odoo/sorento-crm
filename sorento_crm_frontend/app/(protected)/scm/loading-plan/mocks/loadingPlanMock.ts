/**
 * PHASE 1 MOCK - DEBT. Deleted the moment the S1 endpoints land (Phase 2 of
 * `PLAN-scm-fulfilment-feedback-p4.md`, R1-R6).
 *
 * What is mocked is ONLY the plan ROW (list / create / cancel / delete / edits): the
 * `/container-requests/build` read behind the record page is real and already ships, so the
 * record page is tuned against real suppliers, real stock lists and real demand rather than
 * invented numbers. The single seam is `fulfilmentService`'s loading-plan block; swapping it
 * is five one-line edits there plus deleting this file.
 *
 * Backed by `sessionStorage` rather than a module-level Map so a full page reload (which is
 * what a `router.push` onto a fresh record does after an upload) does not lose the plan that
 * was just created and 404 the screen under verification.
 */
import type {
  LoadingPlanRecord,
  LoadingPlanStatus,
  PlanDocumentKind,
} from '../../services/fulfilmentService';

const STORE_KEY = 'scm.loading-plan.mock.v1';

function read(): LoadingPlanRecord[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(window.sessionStorage.getItem(STORE_KEY) || '[]') as LoadingPlanRecord[];
  } catch {
    return [];
  }
}

function write(rows: LoadingPlanRecord[]) {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(STORE_KEY, JSON.stringify(rows));
}

function documentLabel(kind: PlanDocumentKind, startedAt: string): string {
  if (kind === 'stock_list') return `Stock list ${startedAt.slice(0, 10)}`;
  if (kind === 'proforma') return `Proforma invoice ${startedAt.slice(0, 10)}`;
  return 'No file';
}

export function mockCreatePlan(body: {
  supplier_id: string;
  supplier_name: string | null;
  plan_horizon_date: string | null;
  document_kind: PlanDocumentKind;
  source_attachment_id: string | null;
}): LoadingPlanRecord {
  const startedAt = new Date().toISOString().slice(0, 19);
  const plan: LoadingPlanRecord = {
    id: crypto.randomUUID(),
    supplier_id: body.supplier_id,
    supplier_name: body.supplier_name,
    started_at: startedAt,
    plan_horizon_date: body.plan_horizon_date,
    document_kind: body.document_kind,
    document_label: documentLabel(body.document_kind, startedAt),
    source_attachment_id: body.source_attachment_id,
    status: 'planning',
    sent_at: null,
    sent_channel: null,
    opened_at: null,
    cancelled_at: null,
    cancelled_by: null,
    line_edits: {},
    to_request_qty: null,
    to_request_cbm: null,
  };
  write([plan, ...read()]);
  return plan;
}

export function mockGetPlan(id: string): LoadingPlanRecord {
  const found = read().find((p) => p.id === id);
  if (!found) throw new Error('Loading plan not found');
  return found;
}

export function mockListPlans(params: {
  query: string;
  status: LoadingPlanStatus | 'active' | '';
  pageIndex: number;
  pageSize: number;
}): { data: LoadingPlanRecord[]; total: number } {
  const needle = params.query.trim().toLowerCase();
  let rows = read();
  if (needle) {
    rows = rows.filter((p) => (p.supplier_name ?? '').toLowerCase().includes(needle));
  }
  if (params.status === 'active' || params.status === '') {
    rows = rows.filter((p) => p.status !== 'cancelled');
  } else {
    rows = rows.filter((p) => p.status === params.status);
  }
  const start = params.pageIndex * params.pageSize;
  return { data: rows.slice(start, start + params.pageSize), total: rows.length };
}

export function mockPatchPlan(id: string, patch: Partial<LoadingPlanRecord>): LoadingPlanRecord {
  const rows = read();
  const i = rows.findIndex((p) => p.id === id);
  if (i < 0) throw new Error('Loading plan not found');
  rows[i] = { ...rows[i], ...patch };
  write(rows);
  return rows[i];
}

export function mockDeletePlan(id: string): void {
  const rows = read();
  const found = rows.find((p) => p.id === id);
  if (found?.sent_at) throw new Error('Sent plans are cancelled, not deleted.');
  write(rows.filter((p) => p.id !== id));
}
