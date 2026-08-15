import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface AIAssistantConfig {
  id: string;
  provider: string;
  model: string;
  temperature: number;
  system_prompt: string;
  api_key_masked: string | null;
  anthropic_api_key_masked: string | null;
  gemini_api_key_masked: string | null;
  enabled_tools: string[];
  rag_enabled: boolean;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIAssistantConfigUpdatePayload {
  provider: string;
  model: string;
  temperature: number;
  system_prompt: string;
  api_key?: string | null;
  anthropic_api_key?: string | null;
  gemini_api_key?: string | null;
  enabled_tools: string[];
  rag_enabled: boolean;
  is_enabled: boolean;
}

export async function getAIAssistantConfig(): Promise<AIAssistantConfig> {
  const r = await apiFetch('/api/v1/system/ai-assistant/config');
  if (!r.ok) throw new Error('Failed to load AI assistant config');
  return r.json();
}

export async function updateAIAssistantConfig(
  payload: AIAssistantConfigUpdatePayload,
): Promise<AIAssistantConfig> {
  const r = await apiFetch('/api/v1/system/ai-assistant/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update AI assistant config');
  }
  return r.json();
}

export async function getAIAssistantTools(): Promise<string[]> {
  const r = await apiFetch('/api/v1/system/ai-assistant/tools');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to load AI assistant tools');
  }
  return r.json();
}

export interface TestConnectionPayload {
  provider: string;
  api_key: string;
  model: string;
}

export interface TestConnectionResult {
  ok: boolean;
  message: string;
  latency_ms: number;
}

export async function testAIAssistantConnection(
  payload: TestConnectionPayload,
): Promise<TestConnectionResult> {
  const r = await apiFetch('/api/v1/system/ai-assistant/test-connection', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    throw new Error(await extractApiError(r, 'Failed to test AI assistant connection'));
  }
  return r.json();
}
