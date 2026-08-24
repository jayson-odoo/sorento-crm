/**
 * AI Assistant Prompt Registry - FE service.
 *
 * ============================================================================
 * API CONTRACT (matches PLAN-ai-assistant-prompt-registry.md §8b - Phase-2 BE
 * MUST match this exactly). All routes gated on the same permission as the
 * existing AI-assistant config routes (view for reads, edit for writes).
 * ============================================================================
 *
 * GET  /api/v1/system/ai-assistant/prompts
 *   -> PromptKeySummary[]
 *      { name, role, active, activates_in|null, variables:[...], dry_runnable,
 *        production_version, staging_version|null, latest_version,
 *        updated_at, updated_by_name }
 *      `dry_runnable` is false for a key that is not an assistant-pipeline node
 *      (spec_understanding, spec_extractor, scm_market_advisory, ideate_extractor):
 *      the dry-run runs ONE whole assistant turn, so a key no turn reads would
 *      report an answer the edit had no part in. It is a property of the KEY and
 *      the versions response below does NOT carry it, so the detail screen reads
 *      it from this list.
 *
 * GET  /api/v1/system/ai-assistant/prompts/{name}/versions
 *   -> PromptVersionsResponse
 *      { name, role, active, activates_in|null, variables:[...],
 *        labels:{ production:int, staging:int|null },
 *        versions:[{ id, version, commit_message, created_by_name,
 *                    created_at, labels:[...] }] }   // version desc
 *
 * GET  /api/v1/system/ai-assistant/prompts/{name}/versions/{v}
 *   -> PromptVersionDetail
 *      { id, name, version, template, variables:[...], commit_message,
 *        created_by_name, created_at, labels:[...] }
 *
 * POST /api/v1/system/ai-assistant/prompts/{name}/versions      # save (new immutable version)
 *   req { template, commit_message }
 *   201 <PromptVersionDetail, version=max+1, labels:[]>
 *   422 { error, unknown_tokens:[...], missing_vars:[...] }   # unknown=block, missing=warn
 *
 * POST /api/v1/system/ai-assistant/prompts/{name}/labels        # publish / rollback
 *   req { label:"production"|"staging", version_id }
 *   200 { labels:{ production, staging } }
 *
 * POST /api/v1/system/ai-assistant/prompts/{name}/test          # single-message dry-run
 *   req { message, version_id }                                 # override THIS key only
 *   200 { output, token_usage, tool_calls:[{name,ok}], used_overrides }
 *   400 dormant key not testable, or dry_runnable=false (not in the pipeline)
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  MOCK_PROMPT_KEYS,
  MOCK_VERSIONS,
  mockDryRun,
  mockSaveVersion,
  mockSetLabel,
  mockTemplateFor,
} from './aiPromptsMocks';

/**
 * Phase-1 prototype toggle. `true` = mock data (no backend). `false` = real
 * API. Flip to `false` in Phase 2 once the backend routes land.
 */
export const USE_PROMPT_MOCKS = false;

export interface PromptKeySummary {
  name: string;
  role: string;
  active: boolean;
  activates_in: string | null;
  variables: string[];
  /**
   * Whether the dry-run means anything for this key. False for a prompt read
   * outside the assistant turn, whose dry-run would exercise the pipeline and
   * not the edit. Only on this summary - the versions response has no such field.
   */
  dry_runnable: boolean;
  production_version: number | null;
  staging_version: number | null;
  latest_version: number | null;
  updated_at: string | null;
  updated_by_name: string | null;
  /** The LLM this agent runs on. null = the global assistant model. */
  provider: string | null;
  model: string | null;
}

export interface PromptVersionRow {
  id: string;
  version: number;
  commit_message: string | null;
  created_by_name: string | null;
  created_at: string;
  labels: string[];
}

export interface PromptVersionsResponse {
  name: string;
  role: string;
  active: boolean;
  activates_in: string | null;
  variables: string[];
  labels: { production: number | null; staging: number | null };
  versions: PromptVersionRow[];
}

export interface PromptVersionDetail {
  id: string;
  name: string;
  version: number;
  template: string;
  variables: string[];
  commit_message: string | null;
  created_by_name: string | null;
  created_at: string;
  labels: string[];
  /** Present on a save (201) response - declared vars not used in the template (soft warn). */
  missing_vars?: string[];
}

export interface SaveVersionPayload {
  template: string;
  commit_message: string;
}

export interface SaveVersionError {
  error: string;
  unknown_tokens: string[];
  missing_vars: string[];
}

export interface SetLabelPayload {
  label: 'production' | 'staging';
  version_id: string;
}

export interface SetLabelResponse {
  labels: { production: number | null; staging: number | null };
}

export interface DryRunPayload {
  message: string;
  version_id: string;
}

export interface DryRunResponse {
  output: string;
  token_usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  tool_calls: { name: string; ok: boolean }[];
  used_overrides: Record<string, string>;
}

const BASE = '/api/v1/system/ai-assistant/prompts';

export async function listPromptKeys(): Promise<PromptKeySummary[]> {
  if (USE_PROMPT_MOCKS) return structuredClone(MOCK_PROMPT_KEYS);
  const r = await apiFetch(BASE);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load prompt keys'));
  return r.json();
}

export async function getPromptVersions(name: string): Promise<PromptVersionsResponse> {
  if (USE_PROMPT_MOCKS) return structuredClone(MOCK_VERSIONS[name]);
  const r = await apiFetch(`${BASE}/${encodeURIComponent(name)}/versions`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load version history'));
  return r.json();
}

export async function getPromptVersion(name: string, version: number): Promise<PromptVersionDetail> {
  if (USE_PROMPT_MOCKS) {
    const v = MOCK_VERSIONS[name]?.versions.find((x) => x.version === version);
    const meta = MOCK_VERSIONS[name];
    return structuredClone({
      id: v?.id ?? `${name}-${version}`,
      name,
      version,
      template: mockTemplateFor(name, version),
      variables: meta?.variables ?? [],
      commit_message: v?.commit_message ?? null,
      created_by_name: v?.created_by_name ?? null,
      created_at: v?.created_at ?? new Date().toISOString(),
      labels: v?.labels ?? [],
    });
  }
  const r = await apiFetch(`${BASE}/${encodeURIComponent(name)}/versions/${version}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load version'));
  return r.json();
}

/**
 * Save a new immutable version. On 422 the rejection carries the parsed
 * {@link SaveVersionError} (unknown tokens block, missing vars are warnings the
 * caller surfaces but the BE already accepted - 422 is only for unknown tokens
 * / blank commit).
 */
export async function saveVersion(name: string, payload: SaveVersionPayload): Promise<PromptVersionDetail> {
  if (USE_PROMPT_MOCKS) return mockSaveVersion(name, payload);
  const r = await apiFetch(`${BASE}/${encodeURIComponent(name)}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as Partial<SaveVersionError> & { detail?: unknown };
    const err = new Error(
      (typeof body.error === 'string' && body.error) ||
        (typeof body.detail === 'string' && body.detail) ||
        'Failed to save version',
    ) as Error & { validation?: SaveVersionError };
    if (Array.isArray(body.unknown_tokens) || Array.isArray(body.missing_vars)) {
      err.validation = {
        error: err.message,
        unknown_tokens: body.unknown_tokens ?? [],
        missing_vars: body.missing_vars ?? [],
      };
    }
    throw err;
  }
  return r.json();
}

export async function setLabel(name: string, payload: SetLabelPayload): Promise<SetLabelResponse> {
  if (USE_PROMPT_MOCKS) return mockSetLabel(name, payload);
  const r = await apiFetch(`${BASE}/${encodeURIComponent(name)}/labels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to move label'));
  return r.json();
}

export interface SetAgentModelPayload {
  label?: string;
  provider: string | null;
  model: string | null;
}

/** Point one agent at one LLM. Empty strings clear the override. */
export async function setAgentModel(
  name: string,
  payload: SetAgentModelPayload,
): Promise<{ provider: string | null; model: string | null }> {
  const r = await apiFetch(`${BASE}/${encodeURIComponent(name)}/model`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: 'production', ...payload }),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to set the model'));
  return r.json();
}

export async function dryRunPrompt(name: string, payload: DryRunPayload): Promise<DryRunResponse> {
  if (USE_PROMPT_MOCKS) return mockDryRun(name, payload);
  const r = await apiFetch(`${BASE}/${encodeURIComponent(name)}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Dry-run failed'));
  return r.json();
}
