import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The embedding columns of the `system_settings` singleton: read from the settings blob, written through the
 * general settings route. `embedding_records_search_model` is read-only here: only the backend guard changes it.
 */
export interface EmbeddingSettings {
  /** null: the setting was never saved; the resolved embedder (overview) stands in. */
  embedding_provider: string | null;
  embedding_model: string | null;
  embedding_records_search_model: string | null;
  embedding_backfill_rpm: number;
}

export type EmbeddingSettingsInput = {
  embedding_provider?: string;
  embedding_model?: string;
  embedding_backfill_rpm: number;
};

const DEFAULT_RPM = 20;

export async function getEmbeddingSettings(): Promise<EmbeddingSettings> {
  const response = await apiFetch('/api/user-management/settings');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load settings'));
  const row = (await response.json())?.settings ?? {};
  return {
    embedding_provider: row.embedding_provider ?? null,
    embedding_model: row.embedding_model ?? null,
    embedding_records_search_model: row.embedding_records_search_model ?? null,
    embedding_backfill_rpm: row.embedding_backfill_rpm ?? DEFAULT_RPM,
  };
}

export async function saveEmbeddingSettings(input: EmbeddingSettingsInput): Promise<void> {
  const response = await apiFetch('/api/user-management/settings/general', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    // Undefined fields are dropped by JSON.stringify: only what the page chose to send goes.
    body: JSON.stringify({
      embedding_provider: input.embedding_provider,
      embedding_model: input.embedding_model,
      embedding_backfill_rpm: input.embedding_backfill_rpm,
    }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save settings'));
}
