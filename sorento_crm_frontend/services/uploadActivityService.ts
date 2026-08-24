/**
 * uploadActivityService - Phase 1 stub + Phase 2 API contract.
 *
 * ─── Phase 2 backend contract (binding) ────────────────────────────
 *
 *   GET /api/v1/resource-management/upload-activity
 *     Query params:
 *       scope=me               (only value for now; admins use
 *                              /integration-management/integration-logs)
 *       since=<iso8601>        default = now - 7 days
 *       limit=<int>            default = 50, max = 200
 *     Auth: bearer JWT (created_by filter applied server-side)
 *     Response 200:
 *       {
 *         "sessions": UploadActivitySession[]
 *       }
 *     Errors:
 *       401 Unauthorized
 *       422 Validation error (bad `since`)
 *
 *   Server groups by `attachments.upload_batch_id`. Bulk ZIPs set
 *   `upload_batch_id = import_job.job_id` so the same key serves both
 *   modal multi-upload and ZIP imports.
 *
 *   n8n callback (existing endpoint, Phase 2 adds Pydantic validation):
 *     PUT /api/v1/integrations/logs/{log_id}
 *     Body:
 *       {
 *         "status": "success" | "failed",
 *         "status_code": int | null,
 *         "response_payload": {
 *           "schema_version": 1,
 *           "outcome": "linked" | "unlinked" | "failed" | "partial",
 *           "summary": str,
 *           "linked": LinkedEntityV1[],
 *           "unlinked_reasons": [{"reason": str}],
 *           "errors": [{"code": str, "message": str, "retryable": bool}]
 *         },
 *         "error_code": str | null,
 *         "error_message": str | null
 *       }
 *
 *   Sweeper extension: integration_log with status="sent" and
 *   processed_at < now() - N8N_CALLBACK_TIMEOUT_MINUTES (default 10)
 *   marked as failed with error_code="N8N_CALLBACK_TIMEOUT".
 *
 * ─── Phase 1 status ────────────────────────────────────────────────
 *
 * No backend exists yet. `fetchUploadActivity` returns mock data via
 * `useUploadActivity`'s direct MOCK_SESSIONS import. This service file
 * is a placeholder so Phase 2 can drop in the real api-client call
 * without changing import sites.
 */

import { apiFetch } from '@/lib/api';

import type { UploadActivitySession } from '@/components/upload-activity/types';

export interface UploadActivityResponse {
  sessions: UploadActivitySession[];
}

export interface UploadActivityQuery {
  scope?: 'me';
  since?: string; // ISO 8601
  limit?: number;
}

const BASE = '/api/v1/resource-management/upload-activity';

/**
 * Phase 2 implementation. Phase 1 callers should NOT use this - they
 * read mocks directly through `useUploadActivity`.
 */
export async function fetchUploadActivity(
  query: UploadActivityQuery = {},
): Promise<UploadActivityResponse> {
  const params = new URLSearchParams();
  params.set('scope', query.scope ?? 'me');
  if (query.since) params.set('since', query.since);
  if (query.limit != null) params.set('limit', String(query.limit));

  const res = await apiFetch(`${BASE}?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch upload activity (${res.status})`);
  }
  return (await res.json()) as UploadActivityResponse;
}
