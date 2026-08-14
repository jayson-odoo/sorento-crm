/**
 * The captain-side onboarding API contract (UAC AC-6, AC-9).
 *
 *   GET    /api/v1/user-management/onboarding/requests            `.view`
 *          DataGrid page of OnboardingRequestSummary.
 *   POST   /api/v1/user-management/onboarding/requests            `.add`
 *          { company_id, title, requester_name, requester_email, requester_phone,
 *            expiry_days } -> the request plus its intake link.
 *   GET    /api/v1/user-management/onboarding/requests/{id}       `.view`
 *          OnboardingRequestDetail, with collisions computed live on read.
 *   DELETE /api/v1/user-management/onboarding/requests/{id}       `.delete`
 *          Hard delete; people cascade.
 *   POST   .../requests/{id}/send                                 `.add`
 *   POST   .../requests/{id}/revoke                               `.edit`
 *   POST   .../requests/{id}/regenerate-token                     `.edit`
 *   POST   .../requests/{id}/start-review                         `.edit`
 *   PUT    .../requests/{id}/people/{person_id}                   `.edit`
 *   POST   .../requests/{id}/people/{person_id}/reject { reason } `.edit`
 *          422 when the reason is blank - checked server-side, not only in the dialog.
 *   POST   .../requests/{id}/approve                              `.approve`
 *          Transitions in_review -> processing and queues the provisioning job.
 *          409 on a second approve, by construction of the status graph.
 *
 * PHASE 1: the bodies answer from fixtures so the review screens can be built
 * and reviewed before the endpoints exist. Phase 2 replaces the bodies with
 * `apiFetch` + `extractApiError` + `buildDataGridParams`; the signatures are the
 * contract the backend is built to.
 */

import type {
  OnboardingPersonPatch,
  OnboardingRequestDetail,
  OnboardingRequestSummary,
} from '@/components/common/onboarding/types';
import {
  MOCK_PEOPLE,
  MOCK_TEMPLATES,
} from '@/app/(auth)/onboarding/__mocks__/onboarding';

export interface OnboardingRequestListParams {
  page?: number;
  limit?: number;
  query?: string;
  status?: string;
}

export interface OnboardingRequestListResult {
  data: OnboardingRequestSummary[];
  pagination: { page: number; limit: number; total: number };
}

const MOCK_DELAY_MS = 200;

function later<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_DELAY_MS));
}

const MOCK_SUMMARIES: OnboardingRequestSummary[] = [
  {
    id: 'req-mocha',
    title: 'MOCHA staff onboarding',
    company_name: 'MOCHA Sdn Bhd',
    requester_name: 'Esther Lim',
    requester_email: 'esther@mocha.com.my',
    status: 'submitted',
    people_count: 18,
    approved_count: 0,
    rejected_count: 0,
    submitted_at: '2026-08-14T09:12:00',
    created_at: '2026-08-12T10:00:00',
    expires_at: '2026-08-26T10:00:00',
    revoked_at: null,
  },
  {
    id: 'req-dealers',
    title: 'Northern dealer wave',
    company_name: 'Sorento Sdn Bhd',
    requester_name: 'Faridah Osman',
    requester_email: 'faridah@sorento.com.my',
    status: 'sent',
    people_count: 0,
    approved_count: 0,
    rejected_count: 0,
    submitted_at: null,
    created_at: '2026-08-13T14:30:00',
    expires_at: '2026-08-27T14:30:00',
    revoked_at: null,
  },
  {
    id: 'req-warehouse',
    title: 'Warehouse night shift',
    company_name: 'Sorento Sdn Bhd',
    requester_name: 'Hafiz Rahim',
    requester_email: 'hafiz@sorento.com.my',
    status: 'partially_completed',
    people_count: 4,
    approved_count: 4,
    rejected_count: 0,
    submitted_at: '2026-08-10T08:00:00',
    created_at: '2026-08-09T08:00:00',
    expires_at: '2026-08-23T08:00:00',
    revoked_at: null,
  },
];

export async function listOnboardingRequests(
  params: OnboardingRequestListParams = {},
): Promise<OnboardingRequestListResult> {
  const query = (params.query ?? '').trim().toLowerCase();
  const filtered = query
    ? MOCK_SUMMARIES.filter(
        (r) =>
          r.title.toLowerCase().includes(query) ||
          r.requester_name.toLowerCase().includes(query) ||
          r.company_name.toLowerCase().includes(query),
      )
    : MOCK_SUMMARIES;
  return later({
    data: filtered,
    pagination: { page: params.page ?? 1, limit: params.limit ?? 10, total: filtered.length },
  });
}

export async function getOnboardingRequest(id: string): Promise<OnboardingRequestDetail> {
  const summary = MOCK_SUMMARIES.find((r) => r.id === id) ?? MOCK_SUMMARIES[0];
  const isEmptyRequest = summary.people_count === 0;
  const people = isEmptyRequest
    ? []
    : MOCK_PEOPLE.map((person, index) => {
        // A couple of collisions and one provisioned lane so every chip state is
        // exercised on the prototype rather than only the happy one.
        if (index === 1) {
          return {
            ...person,
            collisions: [
              { kind: 'user_email' as const, label: 'Already a user: Tan Wei Ming' },
            ],
          };
        }
        if (index === 4) {
          return {
            ...person,
            collisions: [
              { kind: 'contact_phone' as const, label: 'Already a WhatsApp contact' },
            ],
          };
        }
        if (index === 10) {
          return {
            ...person,
            review_status: 'rejected' as const,
            rejection_reason: 'Left the company last month.',
          };
        }
        return person;
      });

  return later({
    ...summary,
    reviewer_note: null,
    requester_note: isEmptyRequest ? null : 'Zul starts next month - no rush on his account.',
    reviewed_by_name: null,
    provisioned_at: null,
    source_file_name: isEmptyRequest ? null : 'PHONE LIST.xlsx',
    templates: MOCK_TEMPLATES,
    people,
  });
}

export async function updateOnboardingPerson(
  _requestId: string,
  _personId: string,
  _patch: OnboardingPersonPatch,
): Promise<void> {
  await later(undefined);
}

export async function rejectOnboardingPerson(
  _requestId: string,
  _personId: string,
  reason: string,
): Promise<void> {
  if (!reason.trim()) {
    throw new Error('Say why it is being rejected. The requester sees this.');
  }
  await later(undefined);
}

export async function approveOnboardingPerson(
  _requestId: string,
  _personId: string,
): Promise<void> {
  await later(undefined);
}

export async function startOnboardingReview(_requestId: string): Promise<void> {
  await later(undefined);
}

export async function approveOnboardingRequest(_requestId: string): Promise<void> {
  await later(undefined);
}

export async function deleteOnboardingRequest(_requestId: string): Promise<void> {
  await later(undefined);
}
