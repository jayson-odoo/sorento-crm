import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { REVISION_HEADER } from '@/lib/revision-fence';
import type { DeferredFormAction } from '@/app/(protected)/sla-management/_shared/formAction';
import type {
  OcnChangeType,
  OcnDetail,
  OcnPage,
  OcnProductHit,
  OcnWrite,
} from '@/types/orderChangeNotice';

const BASE = '/api/v1/procurement/order-change-notices';

/** A filter set: a comma list or an array, sent as one repeated param. */
type MultiValue = string | string[] | undefined;

export type OrderChangeNoticeListParams = DataGridApiFetchParams & {
  status?: MultiValue;
  changeTypeId?: MultiValue;
  riskLevel?: MultiValue;
};

/** A refusal that names a field (`{message, details: {field}}`) keeps the field, so the form can
 *  put the sentence beside it. */
export class OrderChangeNoticeError extends Error {
  field: string | null;
  constructor(message: string, field: string | null) {
    super(message);
    this.name = 'OrderChangeNoticeError';
    this.field = field;
  }
}

async function fail(res: Response, fallback: string): Promise<never> {
  const spare = res.clone();
  const message = await extractApiError(res, fallback);
  let field: string | null = null;
  try {
    const body = (await spare.json()) as { details?: { field?: unknown } };
    field = typeof body?.details?.field === 'string' ? body.details.field : null;
  } catch {
    field = null;
  }
  throw new OrderChangeNoticeError(message, field);
}

async function read<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) return fail(res, fallback);
  return (await res.json()) as T;
}

function asList(value: MultiValue): string[] | undefined {
  const parts = (Array.isArray(value) ? value : String(value ?? '').split(','))
    .map((v) => v.trim())
    .filter(Boolean);
  return parts.length ? parts : undefined;
}

const recordPath = (id: string, move?: string) =>
  `${BASE}/${encodeURIComponent(id)}${move ? `/${move}` : ''}`;

export async function listOrderChangeNotices(params: OrderChangeNoticeListParams): Promise<OcnPage> {
  const sp = buildDataGridParams(params, {
    status: asList(params.status),
    change_type_id: asList(params.changeTypeId),
    risk_level: asList(params.riskLevel),
  });
  const res = await apiFetch(`${BASE}?${sp.toString()}`);
  return read<OcnPage>(res, 'Failed to load order change notices');
}

/** The project page's panel: that project's notices, newest first. `linkable` (the amendment
 *  dialog) keeps only the ones an amendment may pick, by the backend's own predicate. */
export async function listProjectOrderChangeNotices(
  projectId: string,
  options: { linkable?: boolean } = {},
): Promise<OcnPage> {
  const qs = options.linkable ? '?linkable=true' : '';
  const res = await apiFetch(
    `/api/v1/project-sales/projects/${encodeURIComponent(projectId)}/order-change-notices${qs}`,
  );
  return read<OcnPage>(res, 'Failed to load order change notices');
}

export async function getOrderChangeNotice(id: string): Promise<OcnDetail> {
  const res = await apiFetch(recordPath(id));
  return read<OcnDetail>(res, 'Failed to load the order change notice');
}

export async function listChangeTypes(): Promise<OcnChangeType[]> {
  const res = await apiFetch(`${BASE}/change-types`);
  return read<OcnChangeType[]>(res, 'Failed to load the change types');
}

export async function searchOrderChangeNoticeProducts(q: string): Promise<OcnProductHit[]> {
  const res = await apiFetch(`${BASE}/products?q=${encodeURIComponent(q)}`);
  return read<OcnProductHit[]>(res, 'Failed to search products');
}

export async function createOrderChangeNotice(body: OcnWrite): Promise<OcnDetail> {
  const res = await apiFetch(BASE, { method: 'POST', body: JSON.stringify(body) });
  return read<OcnDetail>(res, 'Failed to save the order change notice');
}

/** An edit, sent at the revision on screen when it is known (the PUT is fenced too). */
export async function updateOrderChangeNotice(
  id: string,
  body: OcnWrite,
  revisionNo?: number | null,
): Promise<OcnDetail> {
  const res = await apiFetch(recordPath(id), {
    method: 'PUT',
    ...(revisionNo == null ? {} : { headers: { [REVISION_HEADER]: String(revisionNo) } }),
    body: JSON.stringify(body),
  });
  return read<OcnDetail>(res, 'Failed to save the order change notice');
}

export async function linkOrderChangeNoticeAttachment(id: string, attachmentId: string): Promise<OcnDetail> {
  const res = await apiFetch(recordPath(id, 'attachments'), {
    method: 'POST',
    body: JSON.stringify({ attachment_id: attachmentId }),
  });
  return read<OcnDetail>(res, 'Failed to link the attachment');
}

/** Whether the System Settings switch asks for a project; read from the open app-config
 *  projection, as the sample request form reads its own switch. */
export async function getOrderChangeNoticeSwitches(): Promise<{ requireProject: boolean }> {
  const res = await apiFetch('/api/user-management/settings/app-config');
  const body = await read<{ order_change_notice_require_project?: boolean }>(res, 'Failed to load settings');
  return { requireProject: Boolean(body.order_change_notice_require_project) };
}

/** What a move answers: the updated notice, or (a stage move inside its grace window) the
 *  shared 202 "held, you can still undo" body every deferrable route answers. */
export type OcnMoveResult = OcnDetail | DeferredFormAction;

/** One move, sent at the revision on screen (the backend refuses a stale one, UAC B9). */
async function move(
  id: string,
  revisionNo: number,
  path: string,
  fallback: string,
  body?: unknown,
): Promise<OcnMoveResult> {
  const res = await apiFetch(recordPath(id, path), {
    method: 'POST',
    headers: { [REVISION_HEADER]: String(revisionNo ?? 0) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return read<OcnMoveResult>(res, fallback);
}

export const submitOrderChangeNotice = (id: string, revisionNo: number) =>
  move(id, revisionNo, 'submit', 'Failed to submit the order change notice');

export const sendForApproval = (id: string, revisionNo: number) =>
  move(id, revisionNo, 'send-for-approval', 'Failed to send the notice for approval');

export const sendBack = (id: string, revisionNo: number, reason: string) =>
  move(id, revisionNo, 'reject-submitted', 'Failed to send the notice back', { reason });

export const decideOrderChangeNotice = (
  id: string,
  revisionNo: number,
  action: 'approved' | 'rejected',
  comments: string | null,
) => move(id, revisionNo, 'approval-decision', 'Failed to record the decision', { action, comments });

export const markDone = (id: string, revisionNo: number, csComment: string | null) =>
  move(id, revisionNo, 'done', 'Failed to mark the notice done', { cs_comment: csComment });

export const voidOrderChangeNotice = (id: string, revisionNo: number, reason: string) =>
  move(id, revisionNo, 'void', 'Failed to void the notice', { reason });

export const reviseOrderChangeNotice = (id: string, revisionNo: number, reason: string) =>
  move(id, revisionNo, 'revise', 'Failed to revise the notice', { reason });
