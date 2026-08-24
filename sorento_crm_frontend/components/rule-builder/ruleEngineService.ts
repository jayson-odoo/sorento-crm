/**
 * Rule-engine service boundary. UI → hook (useRuleFacts) → this service →
 * lib/api → FastAPI `GET /rule-facts`.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { RuleFactItem } from './types';

/**
 * Whitelisted facts for the given sources (e.g. `["promotion"]`) - backend
 * `GET /api/v1/rule-facts?sources=<csv>`. Dynamic options (access levels) are
 * materialized server-side.
 */
export async function getFacts(sources: string[]): Promise<RuleFactItem[]> {
  if (sources.length === 0) return [];
  const sp = new URLSearchParams({ sources: sources.join(',') });
  const r = await apiFetch(`/api/v1/rule-facts?${sp.toString()}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load rule fields'));
  return r.json();
}
