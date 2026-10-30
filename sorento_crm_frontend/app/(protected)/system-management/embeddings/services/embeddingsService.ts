import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  BackfillAction,
  EmbeddingsOverview,
  LookupListName,
  LookupWordsResponse,
  TryResult,
} from '../types/embeddings.types';

const RECORDS = '/api/v1/system/embeddings';
const WORDS = '/api/v1/system/chatbot/lookup-words';

/** The server's sentence for a refused call; a response shape `extractApiError` cannot read still gets the fallback. */
async function refusal(response: Response, fallback: string): Promise<Error> {
  try {
    return new Error(await extractApiError(response, fallback));
  } catch {
    const text = await response.text().catch(() => '');
    return new Error(text ? text.slice(0, 300) : fallback);
  }
}

async function read<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw await refusal(response, fallback);
  return response.json();
}

async function post(url: string, body: unknown, fallback: string): Promise<void> {
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await refusal(response, fallback);
}

export async function getOverview(): Promise<EmbeddingsOverview> {
  return read(await apiFetch(`${RECORDS}/overview`), 'Failed to load embeddings');
}

export async function getLookupWords(list: LookupListName | string): Promise<LookupWordsResponse> {
  return read(await apiFetch(`${WORDS}?list=${encodeURIComponent(list)}`), 'Failed to load lookup words');
}

export async function tryPhrase(phrase: string): Promise<TryResult> {
  const response = await apiFetch(`${WORDS}/try`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phrase }),
  });
  return read(response, 'Failed to try the phrase');
}

export async function embedMissing(): Promise<void> {
  await post(`${WORDS}/embed-missing`, undefined, 'Failed to start embedding');
}

export async function recordsBackfill(action: BackfillAction): Promise<void> {
  await post(`${RECORDS}/records-backfill`, { action }, 'Failed to update the backfill');
}
