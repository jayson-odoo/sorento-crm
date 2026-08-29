/**
 * The captain-side onboarding API contract (UAC AC-6, AC-9).
 *
 *   GET    /api/v1/user-management/onboarding/requests            `.view`
 *          Paged, sorted and searched server-side; standard grid envelope.
 *   GET    /api/v1/user-management/onboarding/requests/neighbours `.view`
 *          Prev/next within the active list query, for the detail pager.
 *   POST   /api/v1/user-management/onboarding/requests            `.add`
 *   GET    /api/v1/user-management/onboarding/requests/{id}       `.view`
 *          Detail, with collisions computed live on read.
 *   DELETE /api/v1/user-management/onboarding/requests/{id}       `.delete`
 *          Hard delete; people cascade.
 *   POST   .../requests/{id}/send                                 `.add`
 *   POST   .../requests/{id}/revoke                               `.edit`
 *   POST   .../requests/{id}/regenerate-token                     `.edit`
 *   POST   .../requests/{id}/start-review                         `.edit`
 *   PUT    .../requests/{id}/people/{person_id}                   `.edit`
 *   POST   .../requests/{id}/people/{person_id}/keep              `.edit`
 *   POST   .../requests/{id}/people/{person_id}/reject { reason } `.edit`
 *          422 when the reason is blank - checked server-side, not only in the dialog.
 *   POST   .../requests/{id}/approve                              `.approve`
 *          Transitions in_review -> processing and queues the provisioning job.
 *          422 on a second approve, by construction of the status graph.
 *
 * `apiFetch('/api/user-management/...')` maps straight onto the FastAPI backend
 * at `/api/v1/user-management/...` via the rewrite table in `lib/api.ts`.
 */

import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type {
  OnboardingPersonPatch,
  OnboardingRequestDetail,
  OnboardingRequestSummary,
} from '@/components/common/onboarding/types';

const BASE = '/api/user-management/onboarding';


export type OnboardingRequestListParams = DataGridApiFetchParams & {
  /** A single `onboarding_request` status code, or undefined for all. */
  statusKey?: string;
};

export interface OnboardingRequestListResult {
  data: OnboardingRequestSummary[];
  pagination: { page: number; limit: number; total: number };
}

export interface OnboardingApproveResult {
  status: string;
  /** Null when the transition committed but the job could not be queued. */
  job_id: string | null;
  queued_people: number;
}

async function readOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await extractApiError(response, fallback));
  }
  return response.json();
}

/** One page of the queue. Paging, sorting and search all happen server-side. */
export async function listOnboardingRequests(
  params: OnboardingRequestListParams,
): Promise<OnboardingRequestListResult> {
  const search = buildDataGridParams(params, { status_key: params.statusKey });
  const response = await apiFetch(`${BASE}/requests?${search.toString()}`);
  return readOrThrow(response, 'Could not load onboarding requests');
}

export async function getOnboardingRequest(id: string): Promise<OnboardingRequestDetail> {
  const response = await apiFetch(`${BASE}/requests/${id}`);
  return readOrThrow(response, 'Could not load this onboarding request');
}

export interface CreateOnboardingRequestInput {
  company_id: string;
  title: string;
  requester_name: string;
  requester_email: string;
  requester_phone?: string | null;
  expiry_days?: number;
}

export async function createOnboardingRequest(
  input: CreateOnboardingRequestInput,
): Promise<OnboardingRequestDetail> {
  const response = await apiFetch(`${BASE}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return readOrThrow(response, 'Could not create the onboarding request');
}

async function post(path: string, fallback: string, body?: unknown): Promise<void> {
  const response = await apiFetch(path, {
    method: 'POST',
    ...(body === undefined
      ? {}
      : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, fallback));
  }
}

export async function updateOnboardingPerson(
  requestId: string,
  personId: string,
  patch: OnboardingPersonPatch,
): Promise<void> {
  const response = await apiFetch(`${BASE}/requests/${requestId}/people/${personId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save that change'));
  }
}

export async function rejectOnboardingPerson(
  requestId: string,
  personId: string,
  reason: string,
): Promise<void> {
  // Checked here so the dialog can refuse instantly, and AGAIN server-side -
  // this is the last place that can stop a rejection the requester cannot act on.
  if (!reason.trim()) {
    throw new Error('Say why it is being rejected. The requester sees this.');
  }
  await post(
    `${BASE}/requests/${requestId}/people/${personId}/reject`,
    'Could not reject that person',
    { reason },
  );
}

export async function approveOnboardingPerson(
  requestId: string,
  personId: string,
): Promise<void> {
  await post(
    `${BASE}/requests/${requestId}/people/${personId}/keep`,
    'Could not keep that person',
  );
}

export async function startOnboardingReview(requestId: string): Promise<void> {
  await post(`${BASE}/requests/${requestId}/start-review`, 'Could not start the review');
}

export async function approveOnboardingRequest(
  requestId: string,
): Promise<OnboardingApproveResult> {
  const response = await apiFetch(`${BASE}/requests/${requestId}/approve`, {
    method: 'POST',
  });
  return readOrThrow(response, 'Could not approve this request');
}

export async function sendOnboardingRequest(requestId: string): Promise<void> {
  await post(`${BASE}/requests/${requestId}/send`, 'Could not send the intake link');
}

export async function revokeOnboardingRequest(requestId: string): Promise<void> {
  await post(`${BASE}/requests/${requestId}/revoke`, 'Could not revoke the link');
}

export async function regenerateOnboardingToken(requestId: string): Promise<void> {
  await post(
    `${BASE}/requests/${requestId}/regenerate-token`,
    'Could not issue a new link',
  );
}

export async function deleteOnboardingRequest(requestId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/requests/${requestId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not delete this request'));
  }
}
