/**
 * WhatsApp Template service — Respond.io template sync, per-use-case defaults,
 * 24h-window state and template sending.
 *
 * =========================================================================
 * EXPECTED API CONTRACT (Phase 1 — locked for Phase 2 backend work)
 * See docs/plans/PLAN-whatsapp-template-fallback.md
 * =========================================================================
 *
 * GET /api/v1/integrations/respond/templates
 *   Query: page, limit, sort, dir, query (buildDataGridParams), status?
 *   200: { data: WhatsAppTemplate[], pagination: { total, page, limit } }
 *
 * POST /api/v1/integrations/respond/templates/sync
 *   200: { synced: number, deleted: number, channels: number }
 *   Errors: 502 when Respond.io API unreachable.
 *
 * GET /api/v1/integrations/respond/template-defaults
 *   200: TemplateDefault[]  (always 4 rows — one per use_case, template_id
 *        null when unset; is_valid=false when the referenced template was
 *        deleted on sync or is no longer `approved`)
 *
 * PUT /api/v1/integrations/respond/template-defaults/{use_case}
 *   Body: { template_id: string, param_mapping: Record<string, ParamVariable> }
 *   - param_mapping keys are the template's positional params ("1".."n");
 *     every param of the template MUST be mapped (422 otherwise).
 *   - template must have status=approved (422 otherwise).
 *   200: TemplateDefault
 *
 * DELETE /api/v1/integrations/respond/template-defaults/{use_case}
 *   200: TemplateDefault (template_id null)
 *
 * Per-entity chat routes (keyed by use case in ENTITY_CHAT_BASE):
 *   GET  /{entity_base}/{id}/conversation/window-state
 *     - Backend scans Respond.io list_messages for the latest incoming
 *       message; window treated as 23h (margin). Degrades to chat_history
 *       when the Respond API errors; no data at all => closed.
 *     200: WindowState
 *   POST /{entity_base}/{id}/conversation/template-message
 *     Body: { template_id: string, params: Record<string, string> }
 *     - params keys "1".."n" must cover the template's param_count (422).
 *       Contact is resolved server-side from the entity (no contact_id needed).
 *     200: { ok: true, template_name, rendered_body }
 *     Errors: 422 template not approved / params missing; 502 send failed.
 *   entity_base: complaint=/complaints-management/complaints,
 *     stock_inquiry|purchase_request|sponsorship_form=/procurement/*
 *
 * Status enums:
 *   TemplateStatus: approved | pending | rejected
 *   UseCase: complaint | stock_inquiry | purchase_request | sponsorship_form
 *   ParamVariable: contact_name | entity_number | status | reason | portal_url | message
 * =========================================================================
 */

export type TemplateStatus = 'approved' | 'pending' | 'rejected';

export type UseCase =
  | 'complaint'
  | 'stock_inquiry'
  | 'purchase_request'
  | 'sponsorship_form'
  | 'portal_otp'
  | 'sla_daily_summary'
  | 'sla_assignment'
  | 'sla_escalation'
  | 'product_discontinued';

export type ParamVariable =
  | 'contact_name'
  | 'entity_number'
  | 'status'
  | 'reason'
  | 'portal_url'
  | 'message'
  | 'otp_code'
  | 'outstanding'
  | 'escalated_last_24h'
  | 'resolved_last_24h'
  | 'discontinued_count'
  | 'discontinued_link'
  | 'today_date'
  | 'system_url'
  | 'respond_due_at'
  | 'resolve_due_at';

export interface WhatsAppTemplate {
  id: string;
  respond_template_id: string;
  name: string;
  language: string;
  category: string; // MARKETING | UTILITY | AUTHENTICATION
  status: TemplateStatus;
  body_text: string; // body component text containing {{1}}..{{n}}
  param_count: number;
  channel_name: string;
  synced_at: string; // ISO UTC
}

export interface TemplateDefault {
  use_case: UseCase;
  template_id: string | null;
  template_name: string | null;
  template_status: TemplateStatus | null;
  param_mapping: Record<string, ParamVariable>;
  /** false when the referenced template vanished on sync or lost approval */
  is_valid: boolean;
}

export interface WindowState {
  open: boolean;
  last_incoming_at: string | null; // ISO UTC
  checked_at: string; // ISO UTC
}

export interface TemplateListResult {
  data: WhatsAppTemplate[];
  pagination: { total: number; page: number; limit: number };
}

export interface SyncResult {
  synced: number;
  deleted: number;
  channels: number;
}

export const USE_CASES: { key: UseCase; label: string; description: string }[] = [
  {
    key: 'complaint',
    label: 'Complaint',
    description: 'Decision updates (approved / rejected) sent to the complainant.',
  },
  {
    key: 'stock_inquiry',
    label: 'Stock Inquiry',
    description: 'Reply and rejection updates sent to the inquiring contact.',
  },
  {
    key: 'purchase_request',
    label: 'Purchase Request',
    description: 'Status updates (form number, approval) sent to the requester.',
  },
  {
    key: 'sponsorship_form',
    label: 'Sponsorship Form',
    description: 'Approval updates sent to the sponsorship applicant.',
  },
  {
    key: 'portal_otp',
    label: 'Portal OTP',
    description:
      'Login verification code sent when a contact opens the portal on a new device and the 24h window is closed. Map the code param to "OTP code".',
  },
  {
    key: 'sla_daily_summary',
    label: 'SLA Daily Summary',
    description:
      'Daily SLA digest sent to staff on WhatsApp when their 24h window is closed. Bounded template — map params to the outstanding / escalated (24h) / resolved (24h) counts and the dashboard deep link (Portal URL).',
  },
  {
    key: 'sla_assignment',
    label: 'SLA Assignment',
    description:
      'Sent to a staff member when an SLA task is assigned to them. Map params to "Contact name" (the staff name) and "Full update message" at minimum; add "Entity number" / "Status" when the template carries them.',
  },
  {
    key: 'sla_escalation',
    label: 'SLA Escalation',
    description:
      'Sent to a staff member when an SLA task escalates to them. Map params to "Contact name" and "Full update message" at minimum; add "Entity number" / "Status" when the template carries them.',
  },
  {
    key: 'product_discontinued',
    label: 'Product Discontinued',
    description:
      'Batch alert sent to subscribed staff when products are newly discontinued. Map params to "Discontinued count" and "Discontinued link" (the deep link to the filtered product list).',
  },
];

export const PARAM_VARIABLES: { key: ParamVariable; label: string; description: string }[] = [
  { key: 'contact_name', label: 'Contact name', description: 'WhatsApp contact display name' },
  { key: 'entity_number', label: 'Entity number', description: 'e.g. CMP-2606-0012 / RMA-PS2605-0017' },
  { key: 'status', label: 'Status', description: 'New status of the record (approved, rejected…)' },
  { key: 'reason', label: 'Reason', description: 'Decision reason when present' },
  { key: 'portal_url', label: 'Portal URL', description: 'Customer portal link for the record' },
  { key: 'message', label: 'Full update message', description: 'The composed update text, flattened to one line' },
  { key: 'otp_code', label: 'OTP code', description: 'The 6-digit portal login verification code' },
  { key: 'outstanding', label: 'Outstanding count', description: 'Outstanding conversations assigned to the staff member' },
  { key: 'escalated_last_24h', label: 'Escalated (24h)', description: 'Conversations escalated to the staff member in the last 24h' },
  { key: 'resolved_last_24h', label: 'Resolved (24h)', description: 'Conversations the staff member resolved in the last 24h' },
  { key: 'discontinued_count', label: 'Discontinued count', description: 'Number of products newly discontinued in this batch' },
  { key: 'discontinued_link', label: 'Discontinued link', description: 'Deep link to the product list filtered to that batch' },
  { key: 'today_date', label: "Today's date", description: 'Date the message is sent (DD/MM/YYYY, Malaysia time)' },
  { key: 'system_url', label: 'System URL', description: 'CRM base URL (e.g. https://fe-sorento.foundryx.my)' },
  { key: 'respond_due_at', label: 'Respond by', description: 'SLA response deadline (KL wall time)' },
  { key: 'resolve_due_at', label: 'Resolve by', description: 'SLA resolution deadline (KL wall time)' },
];


// ===========================================================================
// Real API calls (Phase 2). Window-state + template send are per-entity routes
// keyed by use case; the rest hit /integrations/respond/*.
// ===========================================================================

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

async function jsonOrThrow<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

const RESPOND_BASE = '/api/v1/integrations/respond';

/** Conversation base path per chat entity (window-state + template-message live under it). */
const ENTITY_CHAT_BASE: Record<string, string> = {
  complaint: '/api/v1/complaints-management/complaints',
  stock_inquiry: '/api/v1/procurement/stock-inquiries',
  purchase_request: '/api/v1/procurement/purchase-requests',
  sponsorship_form: '/api/v1/procurement/purchase-requests',
};

function chatBase(entityType: string): string {
  const base = ENTITY_CHAT_BASE[entityType];
  if (!base) throw new Error(`No chat route configured for entity type: ${entityType}`);
  return base;
}

export async function listTemplates(params: {
  page?: number;
  limit?: number;
  query?: string;
  status?: TemplateStatus | 'all';
}): Promise<TemplateListResult> {
  const sp = new URLSearchParams();
  sp.set('page', String(params.page ?? 1));
  sp.set('limit', String(params.limit ?? 50));
  if (params.query) sp.set('query', params.query);
  if (params.status && params.status !== 'all') sp.set('status', params.status);
  const res = await apiFetch(`${RESPOND_BASE}/templates?${sp.toString()}`);
  return jsonOrThrow<TemplateListResult>(res, 'Failed to load templates');
}

export async function syncTemplates(): Promise<SyncResult> {
  const res = await apiFetch(`${RESPOND_BASE}/templates/sync`, { method: 'POST' });
  return jsonOrThrow<SyncResult>(res, 'Template sync failed');
}

export async function listTemplateDefaults(): Promise<TemplateDefault[]> {
  const res = await apiFetch(`${RESPOND_BASE}/template-defaults`);
  return jsonOrThrow<TemplateDefault[]>(res, 'Failed to load template defaults');
}

export async function setTemplateDefault(
  useCase: UseCase,
  body: { template_id: string; param_mapping: Record<string, ParamVariable> },
): Promise<TemplateDefault> {
  const res = await apiFetch(`${RESPOND_BASE}/template-defaults/${useCase}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<TemplateDefault>(res, 'Failed to save default');
}

export async function clearTemplateDefault(useCase: UseCase): Promise<TemplateDefault> {
  const res = await apiFetch(`${RESPOND_BASE}/template-defaults/${useCase}`, {
    method: 'DELETE',
  });
  return jsonOrThrow<TemplateDefault>(res, 'Failed to clear default');
}

export async function getWindowState(
  entityType: string,
  entityId: string,
): Promise<WindowState> {
  const res = await apiFetch(
    `${chatBase(entityType)}/${encodeURIComponent(entityId)}/conversation/window-state`,
  );
  return jsonOrThrow<WindowState>(res, 'Failed to check window state');
}

/** Approved templates for the send dialog — reuses the templates list endpoint. */
export async function listApprovedTemplates(): Promise<WhatsAppTemplate[]> {
  const res = await listTemplates({ page: 1, limit: 200, status: 'approved' });
  return res.data;
}

export async function sendTemplateMessage(
  entityType: string,
  entityId: string,
  body: { contact_id: string; template_id: string; params: Record<string, string> },
): Promise<{ ok: true }> {
  const res = await apiFetch(
    `${chatBase(entityType)}/${encodeURIComponent(entityId)}/conversation/template-message`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: body.template_id, params: body.params }),
    },
  );
  await jsonOrThrow(res, 'Failed to send template');
  return { ok: true };
}

/** Render a template body with params filled; unfilled params stay as {{n}}. */
export function renderTemplateBody(bodyText: string, params: Record<string, string>): string {
  return bodyText.replace(/\{\{(\d+)\}\}/g, (m, n: string) => {
    const v = (params[n] ?? '').trim();
    return v || m;
  });
}
