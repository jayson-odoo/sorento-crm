import { apiFetch } from '@/lib/api';
import type {
  Complaint,
  ComplaintFormData,
  ComplaintDetail,
} from '../types/complaint.types';
import type {
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';

export async function getComplaints(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<Complaint>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch complaints');
  return response.json();
}

export async function getComplaint(id: string): Promise<ComplaintDetail> {
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints/${id}`,
  );
  if (!response.ok) throw new Error('Failed to fetch complaint');
  return response.json();
}

export async function createComplaint(
  data: ComplaintFormData,
): Promise<Complaint> {
  const response = await apiFetch('/api/v1/complaints-management/complaints', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to create complaint' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateComplaint(
  id: string,
  data: Partial<ComplaintFormData>,
): Promise<Complaint> {
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints/${id}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to update complaint' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteComplaint(id: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints/${id}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to delete complaint' }));
    throw new Error(error.message);
  }
}

export async function linkComplaintAttachment(
  complaintId: string,
  attachmentId: string,
): Promise<{ message: string; link_id: string }> {
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints/${complaintId}/attachments`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attachment_id: attachmentId }),
    },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to link attachment' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteComplaintAttachment(linkId: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/complaints-management/complaints/attachments/${linkId}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'Failed to unlink attachment' }));
    throw new Error(error.message);
  }
}
