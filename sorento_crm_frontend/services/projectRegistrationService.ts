import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { ProjectRegisterBody } from '@/app/(protected)/project-sales/_shared/types/project.types';
import type {
  ProjectRegistrationDetail,
  ProjectRegistrationPage,
} from '@/types/projectRegistration';

const BASE = '/api/v1/project-sales/projects/registrations';

export type ProjectRegistrationListParams = DataGridApiFetchParams & {
  /** A status key or `all`; empty means the server default (pending). */
  status?: string;
};

async function read<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

export async function getProjectRegistrations(
  params: ProjectRegistrationListParams,
): Promise<ProjectRegistrationPage> {
  const sp = buildDataGridParams(params, { status: params.status });
  const res = await apiFetch(`${BASE}/?${sp.toString()}`);
  return read<ProjectRegistrationPage>(res, 'Failed to load registrations');
}

export async function getProjectRegistration(id: string): Promise<ProjectRegistrationDetail> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  return read<ProjectRegistrationDetail>(res, 'Failed to load the registration');
}

export async function approveProjectRegistration(
  id: string,
  payload: ProjectRegisterBody,
): Promise<ProjectRegistrationDetail> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return read<ProjectRegistrationDetail>(res, 'Failed to approve the registration');
}

export async function rejectProjectRegistration(
  id: string,
  reason: string,
): Promise<ProjectRegistrationDetail> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
  return read<ProjectRegistrationDetail>(res, 'Failed to reject the registration');
}
