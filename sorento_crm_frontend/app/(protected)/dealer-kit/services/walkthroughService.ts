/**
 * Showroom walkthroughs (PLAN-showroom-walkthrough-28oct.md).
 *
 * CONTRACT - `app/api/v1/dealer_kit/walkthroughs.py`, under `/api/v1/dealer-kit`.
 * Reads carry `dealer_kit.page.view`, writes `dealer_kit.page.edit`. Another
 * company's walkthrough is a 404.
 *
 * GET    /walkthroughs                          -> WalkthroughSummary[], newest first
 * POST   /walkthroughs {name}                   -> 201 Walkthrough
 * GET    /walkthroughs/{id}                     -> Walkthrough (stops in walking order)
 * PATCH  /walkthroughs/{id} {name}              -> Walkthrough
 * POST   /walkthroughs/{id}/stops  multipart `files` (repeat) + `title`
 *          -> 202 WalkthroughStop, `status: 'processing'`. The stitch runs on the
 *          worker; a stop that cannot be stitched lands as `failed` with the reason.
 *          400 for a file that is not a photo or video, 413 over 300 MB.
 * GET    /walkthroughs/{id}/stops/{stopId}/panorama -> image/jpeg, 409 until done
 * Deletes go through the deferred actions `dk_walkthrough.delete` and
 * `dk_walkthrough_stop.delete`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/dealer-kit/walkthroughs';

export type WalkthroughStopStatus = 'processing' | 'done' | 'failed';

export interface WalkthroughStop {
  id: string;
  position: number;
  title: string;
  status: WalkthroughStopStatus;
  errorMessage: string | null;
  /** The angle the panorama covers. 360 x 180 is a full sphere. Null until done. */
  hFovDeg: number | null;
  vFovDeg: number | null;
  createdAt: string;
  finishedAt: string | null;
}

export interface WalkthroughSummary {
  id: string;
  name: string;
  stopCount: number;
  processingCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface Walkthrough extends WalkthroughSummary {
  stops: WalkthroughStop[];
}

const path = (id: string) => `${BASE}/${encodeURIComponent(id)}`;

async function json<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await extractApiError(response, fallback));
  }
  return (await response.json()) as T;
}

export async function listWalkthroughs(): Promise<WalkthroughSummary[]> {
  const rows = await json<WalkthroughSummary[]>(
    await apiFetch(BASE),
    'Could not load the walkthroughs',
  );
  return Array.isArray(rows) ? rows : [];
}

export async function getWalkthrough(id: string): Promise<Walkthrough> {
  return json(await apiFetch(path(id)), 'Could not load this walkthrough');
}

export async function createWalkthrough(name: string): Promise<Walkthrough> {
  return json(
    await apiFetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
    'Could not create the walkthrough',
  );
}

export async function renameWalkthrough(id: string, name: string): Promise<Walkthrough> {
  return json(
    await apiFetch(path(id), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
    'Could not rename the walkthrough',
  );
}

/** No Content-Type header: the browser has to write the multipart boundary itself. */
export async function addStop(
  id: string,
  files: File[],
  title: string,
): Promise<WalkthroughStop> {
  const body = new FormData();
  files.forEach((file) => body.append('files', file));
  body.append('title', title);
  return json(
    // A 300 MB video takes a while to leave a showroom's wifi.
    await apiFetch(`${path(id)}/stops`, { method: 'POST', body, timeoutMs: 10 * 60 * 1000 }),
    'Could not add this stop',
  );
}

/** Through the backend, so WebGL never needs the bucket to send CORS headers. */
export async function getPanorama(id: string, stopId: string): Promise<Blob> {
  const response = await apiFetch(
    `${path(id)}/stops/${encodeURIComponent(stopId)}/panorama`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load this panorama'));
  }
  return response.blob();
}
