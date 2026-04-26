import { apiFetch } from '@/lib/api';

const BASE = '/api/v1/commercial/process-config/settings/assignment-select';

export const LEAD_ASSIGNMENT_KEYS = [
  'lead_states',
  'lead_countries',
  'lead_property_types',
  'lead_budget_ranges',
  'lead_sales_closure_confidence',
  'lead_sources',
  'lead_industries',
] as const;

export type LeadAssignmentKey = (typeof LEAD_ASSIGNMENT_KEYS)[number];

export type AssignmentSelectOption = { code: string; label: string };

export async function fetchLeadAssignmentSelect(key: LeadAssignmentKey): Promise<AssignmentSelectOption[]> {
  const res = await apiFetch(`${BASE}/${key}`);
  if (!res.ok) throw new Error('Failed to load master list');
  const json = (await res.json()) as { data?: AssignmentSelectOption[] };
  return Array.isArray(json.data) ? json.data : [];
}
