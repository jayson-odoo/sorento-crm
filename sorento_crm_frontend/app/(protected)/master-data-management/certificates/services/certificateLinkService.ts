/**
 * "Certificate links to check" - feature service (CERT-LINK-CLEANUP).
 *
 * Layering: components -> hooks/useCertificateLinks -> THIS service -> lib/api-client -> backend.
 *
 *   GET  /api/v1/master-data/certificate-links/   (master_data.certificates.view)
 *        Query: page, limit, sort, dir, query, certificate_ids, attachment_type_ids, verdict (repeated),
 *        source, status (certificate status).
 *        200: { data: CertificateLink[], pagination, empty, summary: { <verdict>: count }, types }
 *        `summary` counts every verdict under every filter except the verdict one.
 *   POST /api/v1/master-data/certificate-links/check     200: { queued }  (worker reads each PDF once)
 *   POST /api/v1/master-data/certificate-links/confirm   body { ids }  200: { confirmed }
 *        (master_data.certificates.edit) source -> manual, one audit row per link.
 *   Remove is the `certificate_link.remove` pending action (10 s countdown), not a route here.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { CertificateLinksResponse } from '../types/certificateLink.types';

const BASE = '/api/v1/master-data/certificate-links';

export type CertificateLinksParams = DataGridApiFetchParams & {
  certificateId?: string;
  verdicts?: string[];
  source?: string;
  typeIds?: string[];
  statuses?: string[];
};

export async function getCertificateLinks(params: CertificateLinksParams): Promise<CertificateLinksResponse> {
  const qs = buildDataGridParams(params, {
    certificate_ids: params.certificateId,
    verdict: params.verdicts && params.verdicts.length ? params.verdicts : undefined,
    source: params.source,
    attachment_type_ids: params.typeIds && params.typeIds.length ? params.typeIds : undefined,
    status: params.statuses && params.statuses.length ? params.statuses : undefined,
  });
  const response = await apiFetch(`${BASE}/?${qs.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch certificate links'));
  }
  return response.json();
}

export async function checkCertificateLinks(): Promise<{ queued: number }> {
  const response = await apiFetch(`${BASE}/check`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to start the check'));
  }
  return response.json();
}

export async function confirmCertificateLinks(ids: string[]): Promise<{ confirmed: number }> {
  const response = await apiFetch(`${BASE}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to confirm the links'));
  }
  return response.json();
}
