import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  AutocountWriteCapabilities,
  AutocountWriteResult,
  ProjectAutocountRegisterStatus,
} from '../types/projectAutocountWrite.types';

const BASE = '/api/v1/project-sales';

/**
 * AC-QTSO-CRM: create, update and cancel a quotation or sales order in AutoCount.
 *
 * No call takes a body: the server resolves the company code and every AutoCount key from its
 * own record (U19). A refusal from AutoCount is a normal answer (HTTP 200 with the result), so
 * it comes back as data for the dialog; only a CRM refusal (switch off, not eligible) throws.
 */

/** One admin switch, off the narrow app-config projection every signed-in user may read. */
async function getAppConfigSwitch(
  field: 'project_autocount_write_enabled' | 'project_autocount_register_enabled',
): Promise<boolean> {
  const response = await apiFetch('/api/user-management/settings/app-config');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load settings'));
  const data = await response.json();
  return Boolean(data?.[field]);
}

/** "AutoCount quotations and sales orders from Project sales". */
export const getAutocountWriteSwitch = () => getAppConfigSwitch('project_autocount_write_enabled');

/** AC-PROJECT-REGISTER: "AutoCount project registration". */
export const getAutocountRegisterSwitch = () =>
  getAppConfigSwitch('project_autocount_register_enabled');

export async function getAutocountWriteCapabilities(): Promise<AutocountWriteCapabilities> {
  const response = await apiFetch(`${BASE}/autocount-write/capabilities`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to check AutoCount'));
  return response.json();
}

async function post(path: string, fallback: string): Promise<AutocountWriteResult> {
  const response = await apiFetch(`${BASE}${path}`, { method: 'POST' });
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

export const createSalesOrderInAutocount = (psoId: string) =>
  post(`/sales-orders/${psoId}/autocount`, 'Could not create the sales order in AutoCount');

export const updateSalesOrderInAutocount = (amendmentId: string) =>
  post(
    `/sales-orders/amendments/${amendmentId}/autocount`,
    'Could not update the sales order in AutoCount',
  );

export const cancelSalesOrderInAutocount = (psoId: string) =>
  post(`/sales-orders/${psoId}/autocount/cancel`, 'Could not cancel the sales order in AutoCount');

export const sendQuotationToAutocount = (documentId: string) =>
  post(`/quotation-documents/${documentId}/autocount`, 'Could not send the quotation to AutoCount');

export const cancelQuotationInAutocount = (documentId: string) =>
  post(
    `/quotation-documents/${documentId}/autocount/cancel`,
    'Could not cancel the quotation in AutoCount',
  );

/** AC-PROJECT-REGISTER: whether this project can be registered in AutoCount now. */
export async function getProjectAutocountRegister(
  projectId: string,
): Promise<ProjectAutocountRegisterStatus> {
  const response = await apiFetch(`${BASE}/${projectId}/autocount-register`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to check AutoCount'));
  return response.json();
}

export const registerProjectInAutocount = (projectId: string) =>
  post(`/${projectId}/autocount-register`, 'Could not register the project in AutoCount');
