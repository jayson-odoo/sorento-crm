import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/** The record kinds whose Project field can be set on their own page (PROJECT-RELATED-RECORDS D2). */
export type RecordProjectKind =
  | 'stock_inquiry'
  | 'complaint'
  | 'purchase_request'
  | 'sponsorship_form'
  | 'new_product_application';

const BASE: Record<RecordProjectKind, string> = {
  stock_inquiry: '/api/v1/procurement/stock-inquiries',
  complaint: '/api/v1/complaints-management/complaints',
  purchase_request: '/api/v1/procurement/purchase-requests',
  sponsorship_form: '/api/v1/procurement/purchase-requests',
  new_product_application: '/api/v1/procurement/new-product-applications',
};

/**
 * Set (or clear, with null) a record's registered project at any status, approval untouched.
 * The server needs the type's edit permission and an approved project.
 */
export async function setRecordProject(
  kind: RecordProjectKind,
  recordId: string,
  projectId: string | null,
): Promise<void> {
  const response = await apiFetch(`${BASE[kind]}/${recordId}/project`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the project'));
}
