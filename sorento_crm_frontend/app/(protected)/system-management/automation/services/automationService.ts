import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  Automation,
  AutomationCreateBody,
  AutomationRun,
  AutomationRunNowResult,
  AutomationUpdateBody,
  ListResponse,
  TriggerSpec,
} from '../types/automation.types';

export async function getAutomations(
  params: { page?: number; limit?: number; query?: string } = {},
): Promise<ListResponse<Automation>> {
  const sp = new URLSearchParams();
  sp.set('page', String(params.page ?? 1));
  sp.set('limit', String(params.limit ?? 50));
  if (params.query) sp.set('query', params.query);
  const r = await apiFetch(`/api/v1/system/automation/automations?${sp.toString()}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load automations'));
  return r.json();
}

export async function getAutomation(id: string): Promise<Automation> {
  const r = await apiFetch(`/api/v1/system/automation/automations/${id}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load automation'));
  return r.json();
}

/**
 * Rule-condition save failure. The backend's `validate_tree` returns a
 * top-level `{ detail: string[] }` (NOT the pydantic `{loc,msg,type}` shape),
 * so callers can surface every problem instead of just the first line.
 */
export class AutomationRuleValidationError extends Error {
  problems: string[];
  constructor(problems: string[]) {
    super(problems.join('\n'));
    this.name = 'AutomationRuleValidationError';
    this.problems = problems;
  }
}

/** Throw the right error for a failed automation save — a rule-validation
 * problems array when present, otherwise the standard extracted message. */
async function throwAutomationSaveError(r: Response, fallback: string): Promise<never> {
  if (r.status === 422) {
    const body = await r
      .clone()
      .json()
      .catch(() => null);
    const detail = body?.detail;
    if (Array.isArray(detail) && detail.length > 0 && detail.every((d) => typeof d === 'string')) {
      throw new AutomationRuleValidationError(detail as string[]);
    }
  }
  throw new Error(await extractApiError(r, fallback));
}

export async function createAutomation(body: AutomationCreateBody): Promise<Automation> {
  const r = await apiFetch('/api/v1/system/automation/automations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) await throwAutomationSaveError(r, 'Failed to create automation');
  return r.json();
}

export async function updateAutomation(id: string, body: AutomationUpdateBody): Promise<Automation> {
  const r = await apiFetch(`/api/v1/system/automation/automations/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) await throwAutomationSaveError(r, 'Failed to update automation');
  return r.json();
}

export async function toggleAutomation(id: string, enabled: boolean): Promise<Automation> {
  const r = await apiFetch(`/api/v1/system/automation/automations/${id}/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to toggle automation'));
  return r.json();
}

export async function deleteAutomation(id: string): Promise<void> {
  const r = await apiFetch(`/api/v1/system/automation/automations/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to delete automation'));
}

export async function runAutomationNow(id: string): Promise<AutomationRunNowResult> {
  const r = await apiFetch(`/api/v1/system/automation/automations/${id}/run`, { method: 'POST' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to run automation'));
  return r.json();
}

export async function getAutomationRuns(
  id: string,
  page = 1,
  limit = 50,
): Promise<ListResponse<AutomationRun>> {
  const sp = new URLSearchParams({ page: String(page), limit: String(limit) });
  const r = await apiFetch(`/api/v1/system/automation/automations/${id}/runs?${sp.toString()}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load runs'));
  return r.json();
}

export async function getTriggerCatalog(): Promise<{ triggers: TriggerSpec[] }> {
  const r = await apiFetch('/api/v1/system/automation/triggers/catalog');
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load triggers'));
  return r.json();
}
