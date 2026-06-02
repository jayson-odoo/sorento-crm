'use client';

/**
 * useAttachmentIntegrationLog — read the latest integration_log row for an
 * attachment and shape it into a UploadActivityFile for IntegrationPanel /
 * IntegrationStatusChip reuse.
 *
 * Strategy:
 *   1. Prefer the upload-activity feed (which already joins ground-truth
 *      linkages from product_attachments / promotion_attachments / forms /
 *      packing_lists) so the user sees real entity names even when the n8n
 *      callback payload was malformed or empty.
 *   2. Fall back to /api/v1/integrations/logs?business_table=attachments
 *      &business_id=<id> when the attachment isn't in the drawer feed
 *      (older than the 7-day window).
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api';

import type {
  LinkedEntity,
  UnlinkedReason,
  UploadActivityFile,
} from './types';
import { useUploadActivity } from './useUploadActivity';

interface RawIntegrationLog {
  id: string;
  status: 'pending' | 'processing' | 'success' | 'failed';
  response_payload?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  processed_at?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
}

interface ListResponse {
  data: RawIntegrationLog[];
  pagination: { total: number; page: number; limit: number };
}

function parsePayload(raw: string | null | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function asArray<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

function mapStatus(
  log: RawIntegrationLog,
  payload: Record<string, unknown>,
): UploadActivityFile['status'] {
  if (log.status === 'failed') return 'failed';
  if (log.status === 'success') {
    const outcome = payload.outcome as string | undefined;
    if (outcome === 'unlinked') return 'unlinked';
    if (outcome === 'failed') return 'failed';
    // linked / partial / missing outcome → linked
    return 'linked';
  }
  return 'processing';
}

export function useAttachmentIntegrationLog(attachmentId: string | null | undefined): {
  log: UploadActivityFile | null;
  isLoading: boolean;
} {
  // First try the drawer feed: it already has the joined linkages, so the
  // entity display_names are populated correctly even for legacy n8n payloads.
  const { sessions } = useUploadActivity();
  const fromFeed = useMemo<UploadActivityFile | null>(() => {
    if (!attachmentId) return null;
    for (const s of sessions) {
      const match = s.files.find((f) => f.attachment_id === attachmentId);
      if (match) return match;
    }
    return null;
  }, [sessions, attachmentId]);

  // Fall back to the raw integration_log row only when the attachment isn't
  // in the drawer feed window.
  const enabled = !!attachmentId && fromFeed === null;

  const query = useQuery<ListResponse>({
    queryKey: ['integration-log', 'latest', 'attachment', attachmentId],
    enabled,
    queryFn: async () => {
      const params = new URLSearchParams({
        page: '1',
        limit: '1',
        sort: 'created_at',
        dir: 'desc',
        business_table: 'attachments',
        business_id: String(attachmentId),
      });
      const res = await apiFetch(`/api/v1/integrations/logs?${params}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch integration log (${res.status})`);
      }
      return (await res.json()) as ListResponse;
    },
    staleTime: 0,
  });

  const log = useMemo<UploadActivityFile | null>(() => {
    if (fromFeed) return fromFeed;
    const raw = query.data?.data?.[0];
    if (!raw || !attachmentId) return null;
    const payload = parsePayload(raw.response_payload);
    const status = mapStatus(raw, payload);
    return {
      client_id: attachmentId,
      attachment_id: attachmentId,
      filename: '',
      status,
      summary: typeof payload.summary === 'string' ? payload.summary : '',
      linked: asArray<LinkedEntity>(payload.linked),
      unlinked_reasons: asArray<UnlinkedReason>(payload.unlinked_reasons),
      error_code: raw.error_code ?? null,
      error_message: raw.error_message ?? null,
      integration_log_id: raw.id,
      last_updated_at:
        raw.updated_at ?? raw.processed_at ?? raw.created_at ?? new Date().toISOString(),
    };
  }, [query.data, attachmentId]);

  return { log, isLoading: fromFeed === null && query.isLoading };
}
