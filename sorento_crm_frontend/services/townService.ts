import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { TownPayload } from '@/types/town.types';

export type TownSnapshotResult =
  | { notModified: true }
  | { notModified: false; snapshot: TownPayload; etag?: string };

/** The town snapshot. Send back the last ETag: a 304 means the snapshot you hold is current. */
export async function getSnapshot(etag?: string, mode?: 'wallboard'): Promise<TownSnapshotResult> {
  const url = `/api/v1/town/snapshot${mode ? `?mode=${mode}` : ''}`;
  const response = await apiFetch(url, etag ? { headers: { 'If-None-Match': etag } } : undefined);
  if (response.status === 304) return { notModified: true };
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the town'));
  return {
    notModified: false,
    snapshot: (await response.json()) as TownPayload,
    etag: response.headers.get('ETag') ?? undefined,
  };
}
