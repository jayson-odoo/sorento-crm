/**
 * The PO link calls both screens share: the Stock Debt relocate / resume routes (scope-free),
 * the Settings switch, and the JSON post helper. UI -> hooks (`usePoLink`) -> THIS service ->
 * lib/api-client -> backend.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { PoLinkResult } from '../../stock-debt/types/stockDebtSnapshot.types';

export const PO_LINK_BASE = '/api/v1/project-sales/stock-debt/po-link';

export async function postJson<T>(url: string, body: unknown, fallback: string): Promise<T> {
  const res = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

/** Move a linked PO line to its sales order line's location. */
export async function relocatePoLine(poLineId: string): Promise<PoLinkResult> {
  return postJson(`${PO_LINK_BASE}/relocate`, { po_line_id: poLineId }, 'Failed to move the PO line');
}

export interface ResumePoLinkInput {
  operationId: string;
  poLineId: string;
  salesOrderLineId: string | null;
}

/** Ask the Shared Service to finish an operation it stopped (it re-reads AutoCount first). */
export async function resumePoLink(input: ResumePoLinkInput): Promise<PoLinkResult> {
  return postJson(
    `${PO_LINK_BASE}/operations/${encodeURIComponent(input.operationId)}/resume`,
    { po_line_id: input.poLineId, sales_order_line_id: input.salesOrderLineId },
    'Failed to resume',
  );
}

/** Whether "AutoCount PO links" is on (System Settings, owner 5 Nov), read off the app-config
 *  projection every signed-in user may read. Off: no PO actions at all. */
export async function getPoLinkSwitch(): Promise<boolean> {
  const res = await apiFetch('/api/user-management/settings/app-config');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load settings'));
  const body = (await res.json()) as { stock_debt_po_link_enabled?: boolean };
  return body.stock_debt_po_link_enabled === true;
}
