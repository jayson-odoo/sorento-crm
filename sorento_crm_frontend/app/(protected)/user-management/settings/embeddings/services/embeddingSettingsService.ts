import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The embedding columns of the `system_settings` singleton: read from the settings blob, written through the
 * general settings route. `embedding_records_search_model` is read-only here: only the backend guard changes it.
 */
export interface EmbeddingSettings {
  embedding_provider: string;
  embedding_model: string;
  embedding_records_search_model: string | null;
  embedding_backfill_rpm: number;
}

export type EmbeddingSettingsInput = Pick<
  EmbeddingSettings,
  'embedding_provider' | 'embedding_model' | 'embedding_backfill_rpm'
>;

const DEFAULTS: EmbeddingSettings = {
  embedding_provider: 'openai',
  embedding_model: 'text-embedding-3-small',
  embedding_records_search_model: null,
  embedding_backfill_rpm: 20,
};

export async function getEmbeddingSettings(): Promise<EmbeddingSettings> {
  const response = await apiFetch('/api/user-management/settings');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load settings'));
  const row = (await response.json())?.settings ?? {};
  return {
    embedding_provider: row.embedding_provider ?? DEFAULTS.embedding_provider,
    embedding_model: row.embedding_model ?? DEFAULTS.embedding_model,
    embedding_records_search_model: row.embedding_records_search_model ?? null,
    embedding_backfill_rpm: row.embedding_backfill_rpm ?? DEFAULTS.embedding_backfill_rpm,
  };
}

export async function saveEmbeddingSettings(input: EmbeddingSettingsInput): Promise<void> {
  const response = await apiFetch('/api/user-management/settings/general', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      embedding_provider: input.embedding_provider,
      embedding_model: input.embedding_model,
      embedding_backfill_rpm: input.embedding_backfill_rpm,
    }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save settings'));
}
