/**
 * S6 - the dispatch board's data, and the one thing the UI must not paper over.
 *
 * **A job cannot be confirmed without a date AND a recorded agreement** (AC-F5). The backend
 * refuses, with a `code` naming which half is missing, and the board surfaces that sentence
 * verbatim rather than a generic toast. That refusal is the entire reason the slice has a
 * state machine: "Service Date: TBA" wearing a Confirmed badge tells CS the case is handled,
 * so nobody chases it, and the office finds out when the consumer calls back.
 *
 * **A job's source is a polymorphic pair, never a complaint id** (ADR-0009). Every job today
 * comes from a complaint; hard-coding that here would make the first job raised from anything
 * else a change to this file rather than a different string.
 *
 * Costs are read through a SEPARATE permission from the board (`case_costs.manage`), so a
 * 403 on the cost panel is an ordinary outcome for a dispatcher, not an error to shout about.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/complaints-management/service-jobs';
const TECHNICIANS = '/api/v1/complaints-management/technicians';
const PROVIDERS = '/api/v1/complaints-management/external-providers';

/** The seven states of the seeded graph. Labels live in `SERVICE_JOB_STATUS_LABELS`. */
export type ServiceJobStatusKey =
  | 'proposed'
  | 'confirmed'
  | 'on_the_way'
  | 'arrived'
  | 'completed'
  | 'verified'
  | 'cancelled';

export interface ServiceJob {
  id: string;
  job_number: string | null;
  source_entity_type: string;
  source_entity_id: string;
  status_key: ServiceJobStatusKey | null;
  site_address: string | null;
  site_contact_name: string | null;
  site_contact_phone: string | null;
  site_latitude: number | null;
  site_longitude: number | null;
  site_place_id: string | null;
  scheduled_from: string | null;
  scheduled_to: string | null;
  proposed_at: string | null;
  confirmed_at: string | null;
  /** Who agreed the date. Without it the job is not Confirmed, whatever the date says. */
  customer_agreed_by: string | null;
  arrived_at: string | null;
  completed_at: string | null;
  verified_at: string | null;
  diagnosis_root_cause_id: string | null;
  /** Money IN. Independent of what the case cost Sorento (AC-M30). */
  charge_state: string | null;
  charge_amount: number | null;
  waiting_on_party: string | null;
  waiting_on_reason: string | null;
  waiting_since: string | null;
  /** confirmed_at -> arrived_at. Null, never zero, when nobody has arrived (AC-F22). */
  attend_seconds: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BoardJob {
  service_job_id: string;
  job_number: string | null;
  status_key: ServiceJobStatusKey | null;
  scheduled_from: string | null;
  scheduled_to: string | null;
  site_address: string | null;
  site_contact_name: string | null;
  site_contact_phone: string | null;
  source_entity_type: string;
  source_entity_id: string;
}

export interface BoardGroup {
  /** YYYY-MM-DD. */
  day: string;
  /** Null is the unassigned column, and it is deliberately the first thing on the board. */
  technician_id: string | null;
  technician_name: string | null;
  jobs: BoardJob[];
}

export interface StalledJob {
  service_job_id: string;
  job_number: string | null;
  scheduled_from: string | null;
  stalled_seconds: number;
  site_address: string | null;
  source_entity_type: string;
  source_entity_id: string;
  waiting_on_party: string | null;
  waiting_on_reason: string | null;
}

export interface Technician {
  id: string;
  name: string;
  phone: string | null;
  employment_type: string | null;
  respond_contact_id: string | null;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExternalProvider {
  id: string;
  name: string;
  provider_type: string;
  phone: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string | null;
}

export interface CaseCostLine {
  id: string;
  cost_kind: 'labour' | 'parts' | 'travel';
  amount: number | null;
  currency: string | null;
  external_provider_id: string | null;
  incurred_on: string | null;
  recorded_by: string | null;
  recorded_at: string | null;
}

export interface CaseCosts {
  total: number;
  /** Per kind, because one number per case does not answer the costing question (AC-M29). */
  breakdown: Record<string, number>;
  lines: CaseCostLine[];
}

export const SERVICE_JOB_STATUS_LABELS: Record<ServiceJobStatusKey, string> = {
  proposed: 'Proposed',
  confirmed: 'Confirmed',
  on_the_way: 'On the way',
  arrived: 'Arrived',
  completed: 'Completed',
  verified: 'Verified',
  cancelled: 'Cancelled',
};

export const COST_KINDS: Array<CaseCostLine['cost_kind']> = ['labour', 'parts', 'travel'];

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return (await response.json()) as T;
}

// ------------------------------------------------------------------- reads

export async function getDispatchBoard(params: {
  dateFrom: string;
  dateTo: string;
}): Promise<BoardGroup[]> {
  const qs = new URLSearchParams({ date_from: params.dateFrom, date_to: params.dateTo });
  const response = await apiFetch(`${BASE}/board?${qs.toString()}`);
  return readJson<BoardGroup[]>(response, 'Failed to load the dispatch board.');
}

export async function getStalledJobs(): Promise<StalledJob[]> {
  const response = await apiFetch(`${BASE}/stalls`);
  return readJson<StalledJob[]>(response, 'Failed to load stalled jobs.');
}

export async function getJobsForSource(
  sourceEntityType: string,
  sourceEntityId: string,
): Promise<ServiceJob[]> {
  const qs = new URLSearchParams({
    source_entity_type: sourceEntityType,
    source_entity_id: sourceEntityId,
  });
  const response = await apiFetch(`${BASE}/by-source?${qs.toString()}`);
  return readJson<ServiceJob[]>(response, 'Failed to load service jobs.');
}

export async function getServiceJob(id: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}`);
  return readJson<ServiceJob>(response, 'Failed to load the service job.');
}

export interface ServiceJobListResult {
  data: ServiceJob[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}

/**
 * Every job, regardless of which day it is on.
 *
 * The board is a day. A job proposed with no date yet - the state every job starts in -
 * belongs to no day, and a job confirmed for last Tuesday leaves the board as soon as it
 * moves on. Both then read as "it disappeared", which is what this list exists to stop.
 */
export async function listServiceJobs(params: {
  page?: number;
  limit?: number;
  query?: string;
  status?: string[];
  sort?: string;
  dir?: string;
}): Promise<ServiceJobListResult> {
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: params.limit ?? 50,
      searchQuery: params.query ?? '',
      sorting: params.sort ? [{ id: params.sort, desc: params.dir !== 'asc' }] : [],
    },
    params.status?.length ? { status: params.status.join(',') } : undefined,
  );
  const response = await apiFetch(`${BASE}/?${search.toString()}`);
  return readJson<ServiceJobListResult>(response, 'Failed to load service jobs.');
}

// ------------------------------------------------------------------ writes

export async function createServiceJob(payload: {
  source_entity_type: string;
  source_entity_id: string;
  site_address?: string | null;
  site_contact_name?: string | null;
  site_contact_phone?: string | null;
}): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson<ServiceJob>(response, 'Failed to raise the service job.');
}

/**
 * Raise a job for a case. The body names the case and NOTHING else.
 *
 * The Site is read off the case server-side (AC-B3): a complaint routinely carries the
 * dealer's shop in `customer_address` alongside the house the fault is in, and posting the
 * address this page happened to display would make that decision in a second place.
 */
export async function raiseServiceJobFromSource(
  sourceEntityType: string,
  sourceEntityId: string,
): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/from-source`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_entity_type: sourceEntityType,
      source_entity_id: sourceEntityId,
    }),
  });
  return readJson<ServiceJob>(response, 'Failed to raise the service job.');
}

/**
 * AC-F5. Both fields, or the backend refuses with `service_job_date_required` /
 * `service_job_agreement_required`. The caller surfaces that message as-is.
 */
export async function confirmServiceJob(
  id: string,
  payload: { scheduled_from: string | null; scheduled_to?: string | null; customer_agreed_by: string },
): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson<ServiceJob>(response, 'Failed to confirm the service job.');
}

export async function assignServiceJob(id: string, technicianId: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ technician_id: technicianId }),
  });
  return readJson<ServiceJob>(response, 'Failed to assign the technician.');
}

/** The consumer cancelled. Attempt kept, job back to Proposed, wait attributed (R12). */
export async function rejectServiceJobVisit(id: string, reason?: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason ?? null }),
  });
  return readJson<ServiceJob>(response, 'Failed to record the rejected visit.');
}

export async function startServiceJobTravel(id: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}/on-the-way`, { method: 'POST' });
  return readJson<ServiceJob>(response, 'Failed to update the service job.');
}

export async function arriveAtServiceJob(id: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}/arrive`, { method: 'POST' });
  return readJson<ServiceJob>(response, 'Failed to record the arrival.');
}

export async function completeServiceJob(
  id: string,
  diagnosisRootCauseId?: string | null,
): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ diagnosis_root_cause_id: diagnosisRootCauseId ?? null }),
  });
  return readJson<ServiceJob>(response, 'Failed to complete the service job.');
}

export async function verifyServiceJob(id: string): Promise<ServiceJob> {
  const response = await apiFetch(`${BASE}/${id}/verify`, { method: 'POST' });
  return readJson<ServiceJob>(response, 'Failed to verify the service job.');
}

// --------------------------------------------------------------- masters

export async function listTechnicians(params?: {
  query?: string;
  isActive?: boolean;
}): Promise<Technician[]> {
  const qs = new URLSearchParams();
  if (params?.query) qs.set('query', params.query);
  if (params?.isActive !== undefined) qs.set('is_active', String(params.isActive));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  const response = await apiFetch(`${TECHNICIANS}/${suffix}`);
  return readJson<Technician[]>(response, 'Failed to load technicians.');
}

export async function createTechnician(payload: {
  name: string;
  phone?: string | null;
  employment_type?: string | null;
  is_active?: boolean;
}): Promise<Technician> {
  const response = await apiFetch(`${TECHNICIANS}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson<Technician>(response, 'Failed to create the technician.');
}

export async function updateTechnician(
  id: string,
  payload: Partial<Pick<Technician, 'name' | 'phone' | 'employment_type' | 'is_active'>>,
): Promise<Technician> {
  const response = await apiFetch(`${TECHNICIANS}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson<Technician>(response, 'Failed to update the technician.');
}

export async function deleteTechnician(id: string): Promise<void> {
  const response = await apiFetch(`${TECHNICIANS}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete the technician.'));
}

export async function listExternalProviders(params?: {
  query?: string;
  providerType?: string;
}): Promise<ExternalProvider[]> {
  const qs = new URLSearchParams();
  if (params?.query) qs.set('query', params.query);
  if (params?.providerType) qs.set('provider_type', params.providerType);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  const response = await apiFetch(`${PROVIDERS}/${suffix}`);
  return readJson<ExternalProvider[]>(response, 'Failed to load external providers.');
}

export async function createExternalProvider(payload: {
  name: string;
  provider_type: string;
  phone?: string | null;
  notes?: string | null;
}): Promise<ExternalProvider> {
  const response = await apiFetch(`${PROVIDERS}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson<ExternalProvider>(response, 'Failed to create the provider.');
}

export async function deleteExternalProvider(id: string): Promise<void> {
  const response = await apiFetch(`${PROVIDERS}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete the provider.'));
}

// ------------------------------------------------------------------ costs

export async function getCaseCosts(
  sourceEntityType: string,
  sourceEntityId: string,
): Promise<CaseCosts> {
  const qs = new URLSearchParams({
    source_entity_type: sourceEntityType,
    source_entity_id: sourceEntityId,
  });
  const response = await apiFetch(`${BASE}/costs/by-source?${qs.toString()}`);
  return readJson<CaseCosts>(response, 'Failed to load case costs.');
}

export async function recordCaseCost(payload: {
  source_entity_type: string;
  source_entity_id: string;
  cost_kind: CaseCostLine['cost_kind'];
  amount: string;
  currency?: string;
  external_provider_id?: string | null;
  recorded_by?: string | null;
}): Promise<CaseCostLine> {
  const response = await apiFetch(`${BASE}/costs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return readJson<CaseCostLine>(response, 'Failed to record the cost.');
}

// ----------------------------------------------------------------- format

/** "2h 30m". Hours and minutes, because a dispatcher reads a board, not a stopwatch. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '-';
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}
