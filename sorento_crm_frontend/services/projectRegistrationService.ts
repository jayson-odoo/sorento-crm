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

/** An error that may carry the project an exact-duplicate refusal names. */
export class ProjectRegistrationError extends Error {
  existingProject?: { project_id: string; project_code: string; title: string };
}

async function read<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const spare = res.clone();
    const error = new ProjectRegistrationError(await extractApiError(res, fallback));
    try {
      const body = (await spare.json()) as {
        existing_project?: ProjectRegistrationError['existingProject'];
        details?: { existing_project?: ProjectRegistrationError['existingProject'] };
      };
      const existing = body.existing_project ?? body.details?.existing_project;
      if (existing && typeof existing === 'object') error.existingProject = existing;
    } catch {
      // not JSON: the message is all there is
    }
    throw error;
  }
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
