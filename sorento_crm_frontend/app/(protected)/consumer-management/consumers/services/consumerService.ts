/**
 * Consumer 360 - reading the ledger the after-sales module exists to build.
 *
 * Sorento sells through dealers and therefore does not know who owns its products. S1 built
 * the ledger, S2 the engine that decides cover, S3 the journey that fills them. This is the
 * first surface that lets anyone look at the result.
 *
 * **Purchase value may simply not be there.** `total_value` and `currency` are OMITTED, not
 * nulled, for a reader without `consumers.purchase_value.view` (AC-L24), and the seed grants
 * that permission to nobody - so the absent case is the DEFAULT, not the exception. Hence
 * `total_value?: number | null`: undefined means "you may not see it", null means "the
 * receipt showed no total". Rendering them the same way would tell a CS agent the dealer
 * sold it for nothing.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';

const BASE = '/api/consumer-management/consumers';

export interface ConsumerProfile {
  id: string;
  full_name: string | null;
  phone_e164: string | null;
  email: string | null;
  respond_contact_id: string | null;
  /** A phone somebody typed into a message, not a person who authenticated. */
  is_provisional: boolean;
  confirmed_at: string | null;
  consent_purpose: string | null;
  /** Which wording they were shown. The only answerable form of "did they consent". */
  consent_notice_version: string | null;
  consent_recorded_at: string | null;
  anonymised_at: string | null;
  merged_into_id: string | null;
  created_at: string | null;
}

export interface ConsumerPurchaseLine {
  id: string;
  kind_code: string | null;
  product_id: string | null;
  /** Verbatim, and the only evidence when the variant never resolved. */
  claimed_text: string | null;
  quantity: number | null;
  line_value?: number | null;
}

export interface ConsumerPurchase {
  id: string;
  purchase_number: string | null;
  purchase_date: string | null;
  purchase_date_source: string | null;
  dealer_document_number: string | null;
  customer_id: string | null;
  proof_attachment_id: string | null;
  registered_at: string | null;
  registration_source: string | null;
  dedupe_pending: boolean;
  /** Absent when the reader lacks the permission. See the module note. */
  total_value?: number | null;
  currency?: string | null;
  lines: ConsumerPurchaseLine[];
}

export interface ConsumerComplaint {
  id: string;
  complaint_number: string | null;
  complaint_date: string | null;
  status: string | null;
  defect_description: string | null;
  site_address: string | null;
  customer_id: string | null;
}

export interface Consumer360 {
  profile: ConsumerProfile;
  /** Set when this profile lost a merge. The page redirects rather than 404ing (AC-L10). */
  merged_into_id: string | null;
  purchases: ConsumerPurchase[];
  complaints: ConsumerComplaint[];
  counts: { purchases: number; complaints: number };
}

export interface ConsumerListResult {
  data: ConsumerProfile[];
  total: number;
  page: number;
  limit: number;
}

export async function listConsumers(params: {
  pageIndex: number;
  pageSize: number;
  searchQuery?: string;
  includeProvisional?: boolean;
}): Promise<ConsumerListResult> {
  const qs = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      searchQuery: params.searchQuery,
    },
    params.includeProvisional === false ? { include_provisional: 'false' } : {},
  );
  const response = await apiFetch(`${BASE}?${qs}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load consumers.'));
  return (await response.json()) as ConsumerListResult;
}

export async function getConsumer360(id: string): Promise<Consumer360> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load consumer.'));
  return (await response.json()) as Consumer360;
}

export interface ConsumerHeadline {
  /** Confirmed only. A provisional profile is not a consumer Sorento knows (AC-L7). */
  consumers: number;
  provisional: number;
  purchases: number;
}

export async function getConsumerHeadline(): Promise<ConsumerHeadline> {
  const response = await apiFetch(`${BASE}/stats/headline`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load counts.'));
  return (await response.json()) as ConsumerHeadline;
}
