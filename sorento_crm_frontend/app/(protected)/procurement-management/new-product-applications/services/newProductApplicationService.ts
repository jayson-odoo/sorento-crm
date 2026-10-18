import { apiFetch } from '@/lib/api';
import { filenameFromContentDisposition } from '@/app/(protected)/project-sales/_shared/services/fileDownload';
import { saveBlobAs } from '@/lib/save-blob';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { stockInquiryLabel } from '@/lib/new-product-application-form';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import {
  NewProductApplicationError,
  type NewProductApplicationDetail,
  type NewProductApplicationFeedbackWrite,
  type NewProductApplicationInquiryImage,
  type NewProductApplicationPage,
  type NewProductApplicationPrefill,
  type NewProductApplicationProductHit,
  type NewProductApplicationSummary,
  type NewProductApplicationWrite,
} from '@/types/newProductApplication';

const BASE = '/api/v1/procurement/new-product-applications';

export type NewProductApplicationListParams = DataGridApiFetchParams & {
  /** Comma list of status keys; empty means every status. */
  status?: string;
  applicantId?: string;
  stockInquiryId?: string;
};

/** The list in the shape the DataGrid and the detail pager read. */
export interface NewProductApplicationListResult {
  data: NewProductApplicationSummary[];
  pagination: { total: number; page: number; limit: number };
}

/** A refusal that names a line or field arrives as `{message, code, details: {field}}`. */
async function fail(res: Response, fallback: string): Promise<never> {
  const spare = res.clone();
  const message = await extractApiError(res, fallback);
  type Body = { code?: unknown; details?: { field?: unknown } };
  let body: Body | null = null;
  try {
    body = (await spare.json()) as Body;
  } catch {
    body = null;
  }
  throw new NewProductApplicationError(
    message,
    typeof body?.code === 'string' ? body.code : null,
    typeof body?.details?.field === 'string' ? body.details.field : null,
  );
}

async function read<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) return fail(res, fallback);
  return (await res.json()) as T;
}

const post = (path: string, fallback: string, body?: unknown) =>
  apiFetch(`${BASE}/${path}`, {
    method: 'POST',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }).then((res) => read<NewProductApplicationDetail>(res, fallback));

export async function getNewProductApplications(
  params: NewProductApplicationListParams,
): Promise<NewProductApplicationListResult> {
  const sp = buildDataGridParams(
    { ...params, searchQuery: undefined },
    {
      q: params.searchQuery,
      status: params.status,
      applicant_id: params.applicantId,
      stock_inquiry_id: params.stockInquiryId,
    },
  );
  const res = await apiFetch(`${BASE}?${sp.toString()}`);
  const body = await read<NewProductApplicationPage>(
    res,
    'Failed to load applications',
  );
  return {
    data: body.items,
    pagination: { total: body.total, page: body.page, limit: body.limit },
  };
}

/** The applications raised from one stock inquiry (its detail page row). */
export async function getStockInquiryApplications(
  stockInquiryId: string,
): Promise<NewProductApplicationSummary[]> {
  const sp = buildDataGridParams(
    { pageIndex: 0, pageSize: 50 },
    { stock_inquiry_id: stockInquiryId },
  );
  const res = await apiFetch(`${BASE}?${sp.toString()}`);
  const body = await read<NewProductApplicationPage>(
    res,
    'Failed to load applications',
  );
  return body.items;
}

export async function getNewProductApplication(
  id: string,
): Promise<NewProductApplicationDetail> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  return read<NewProductApplicationDetail>(
    res,
    'Failed to load the application',
  );
}

export async function getNewProductApplicationPrefill(
  stockInquiryId: string,
): Promise<NewProductApplicationPrefill> {
  const res = await apiFetch(
    `${BASE}/prefill?stock_inquiry_id=${encodeURIComponent(stockInquiryId)}`,
  );
  return read<NewProductApplicationPrefill>(
    res,
    'Failed to load the stock inquiry',
  );
}

export async function createNewProductApplication(
  data: NewProductApplicationWrite,
): Promise<NewProductApplicationDetail> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return read<NewProductApplicationDetail>(
    res,
    'Failed to save the application',
  );
}

export async function updateNewProductApplication(
  id: string,
  data: NewProductApplicationWrite,
): Promise<NewProductApplicationDetail> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return read<NewProductApplicationDetail>(
    res,
    'Failed to save the application',
  );
}

const at = (id: string) => encodeURIComponent(id);

export const submitNewProductApplication = (id: string) =>
  post(`${at(id)}/submit`, 'Failed to submit the application');
export const approveNewProductApplication = (id: string) =>
  post(`${at(id)}/approve`, 'Failed to approve the application');
export const rejectNewProductApplication = (id: string, reason: string) =>
  post(`${at(id)}/reject`, 'Failed to reject the application', { reason });
export const reviseNewProductApplication = (id: string, reason: string) =>
  post(`${at(id)}/revise`, 'Failed to revise the application', { reason });
export const cancelNewProductApplication = (id: string, reason?: string) =>
  post(
    `${at(id)}/cancel`,
    'Failed to cancel the application',
    reason ? { reason } : {},
  );
export const linkNewProductApplicationLine = (
  id: string,
  lineId: string,
  productId: string,
) =>
  post(`${at(id)}/lines/${at(lineId)}/link`, 'Failed to link the product', {
    product_id: productId,
  });
export const closeNewProductApplicationLine = (
  id: string,
  lineId: string,
  reason: string,
) =>
  post(`${at(id)}/lines/${at(lineId)}/close`, 'Failed to close the line', {
    reason,
  });
export const undoNewProductApplicationLine = (id: string, lineId: string) =>
  post(`${at(id)}/lines/${at(lineId)}/undo`, 'Failed to undo the line');

/** Lists matches only (dashes, spaces and case ignored); a person picks one. */
export async function searchNewProductApplicationProducts(
  q: string,
): Promise<NewProductApplicationProductHit[]> {
  const res = await apiFetch(`${BASE}/products?q=${encodeURIComponent(q)}`);
  return read<NewProductApplicationProductHit[]>(
    res,
    'Failed to search products',
  );
}

/** PURCHASING FEEDBACK: lead time and one cost per product (open_code, Approved or Completed). */
export async function saveNewProductApplicationFeedback(
  id: string,
  data: NewProductApplicationFeedbackWrite,
): Promise<NewProductApplicationDetail> {
  const res = await apiFetch(`${BASE}/${at(id)}/feedback`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return read<NewProductApplicationDetail>(res, 'Failed to save the feedback');
}

const imagesPath = (id: string, lineId: string) =>
  `${BASE}/${at(id)}/lines/${at(lineId)}/images`;

export async function uploadNewProductApplicationLineImage(
  id: string,
  lineId: string,
  file: File,
): Promise<NewProductApplicationDetail> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch(imagesPath(id, lineId), {
    method: 'POST',
    body: form,
  });
  return read<NewProductApplicationDetail>(res, 'Failed to upload the image');
}

export async function copyNewProductApplicationLineImage(
  id: string,
  lineId: string,
  attachmentId: string,
): Promise<NewProductApplicationDetail> {
  const res = await apiFetch(`${imagesPath(id, lineId)}/copy`, {
    method: 'POST',
    body: JSON.stringify({ attachment_id: attachmentId }),
  });
  return read<NewProductApplicationDetail>(res, 'Failed to copy the image');
}

export async function deleteNewProductApplicationLineImage(
  id: string,
  lineId: string,
  linkId: string,
): Promise<NewProductApplicationDetail> {
  const res = await apiFetch(`${imagesPath(id, lineId)}/${at(linkId)}`, {
    method: 'DELETE',
  });
  return read<NewProductApplicationDetail>(res, 'Failed to remove the image');
}

/** The image files on a stock inquiry: the "Copy from the inquiry" picker. */
export async function getStockInquiryAttachmentsForNpa(
  stockInquiryId: string,
): Promise<NewProductApplicationInquiryImage[]> {
  const res = await apiFetch(
    `${BASE}/inquiry-attachments?stock_inquiry_id=${at(stockInquiryId)}`,
  );
  return read<NewProductApplicationInquiryImage[]>(
    res,
    'Failed to load the inquiry images',
  );
}

/** The paper sheet as a workbook; the name comes from the server so file and sheet agree. */
export async function downloadNewProductApplicationExcel(
  id: string,
): Promise<void> {
  const res = await apiFetch(`${BASE}/${at(id)}/download`);
  if (!res.ok) return fail(res, 'Failed to download the application');
  const filename =
    filenameFromContentDisposition(res.headers.get('Content-Disposition')) ??
    'new-product-application.xlsx';
  saveBlobAs(await res.blob(), filename);
}

/** Stock inquiries for the header picker, labelled "SI26-0412 - <product code>". */
export async function searchStockInquiryOptions(
  q: string,
): Promise<SearchableSelectOption[]> {
  const sp = buildDataGridParams(
    { pageIndex: 0, pageSize: 25 },
    { query: q.trim() },
  );
  const res = await apiFetch(
    `/api/v1/procurement/stock-inquiries?${sp.toString()}`,
  );
  const body = await read<{
    data: {
      id: string;
      inquiry_number?: string | null;
      product_code?: string | null;
    }[];
  }>(res, 'Failed to load stock inquiries');
  return body.data.map((s) => ({
    value: s.id,
    label: stockInquiryLabel(s.inquiry_number, s.product_code),
  }));
}
