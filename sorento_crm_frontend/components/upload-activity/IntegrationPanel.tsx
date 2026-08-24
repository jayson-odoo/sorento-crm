'use client';

/**
 * IntegrationPanel - card-less view of the latest integration_log for an
 * attachment. Mounted inside AttachmentDetailModal's tabbed details card.
 *
 * Linked entities are always derived from the attachment object's
 * `linked_products / linked_promotions / linked_form / linked_packing_lists`
 * arrays (already returned by getAttachmentMetadata + kept fresh by the
 * Linkages tab's mutation hooks). The integration_log only contributes the
 * run status, timestamp, and error fields - its `response_payload` is
 * unreliable in the wild and we never trust it for entity rendering.
 */

import Link from 'next/link';
import { CheckCircle2, Clock, ExternalLink, Loader2 } from 'lucide-react';

import { parseServerDate } from './timeUtil';
import { summariseFile, ERROR_CODE_FRIENDLY } from './translation';
import { useAttachmentIntegrationLog } from './useAttachmentIntegrationLog';
import type { LinkedEntity, UploadActivityFile } from './types';

interface AttachmentLikeForLinked {
  linked_products?: { id: string; name: string }[] | null;
  linked_promotions?: { id: string; name: string }[] | null;
  linked_form?: { id: string; name: string } | null;
  linked_packing_lists?: { id: string; name: string }[] | null;
}

interface Props {
  attachmentId: string;
  /**
   * Pass the AttachmentDetailModal's attachment object so linked entities
   * stay in sync with the Linkages tab without waiting on drawer-feed refetch.
   */
  attachment?: AttachmentLikeForLinked | null;
}

function deriveLinkedFromAttachment(
  a: AttachmentLikeForLinked | null | undefined,
): LinkedEntity[] {
  if (!a) return [];
  const out: LinkedEntity[] = [];
  for (const p of a.linked_products ?? []) {
    out.push({
      entity_type: 'product',
      entity_id: p.id,
      display_name: p.name || p.id,
      matched_by: 'manual_or_n8n',
    });
  }
  for (const pr of a.linked_promotions ?? []) {
    out.push({
      entity_type: 'promotion',
      entity_id: pr.id,
      display_name: pr.name || pr.id,
      matched_by: 'manual_or_n8n',
    });
  }
  if (a.linked_form) {
    out.push({
      entity_type: 'form',
      entity_id: a.linked_form.id,
      display_name: a.linked_form.name || a.linked_form.id,
      matched_by: 'manual_or_n8n',
    });
  }
  for (const pl of a.linked_packing_lists ?? []) {
    out.push({
      entity_type: 'packing_list',
      entity_id: pl.id,
      display_name: pl.name || pl.id,
      matched_by: 'manual_or_n8n',
    });
  }
  return out;
}

export function IntegrationPanel({ attachmentId, attachment }: Props) {
  const { log, isLoading } = useAttachmentIntegrationLog(attachmentId);

  if (isLoading) {
    return (
      <div className="text-sm text-muted-foreground py-2 flex items-center gap-2">
        <Loader2 className="size-3.5 animate-spin" />
        Loading integration status…
      </div>
    );
  }

  // Attachment-derived linked entities take precedence (fresher than the
  // upload-activity feed cache).
  const linkedFromAttachment = deriveLinkedFromAttachment(attachment);
  const linked = linkedFromAttachment.length > 0 ? linkedFromAttachment : log?.linked ?? [];

  if (!log && linked.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-2">
        No integration runs recorded for this attachment yet.
      </div>
    );
  }

  // Promote status to "linked" when the attachment actually has links, even
  // if the integration_log was never updated by n8n.
  const effectiveStatus: UploadActivityFile['status'] =
    linked.length > 0 ? 'linked' : log?.status ?? 'processing';

  const effectiveLog: UploadActivityFile =
    log ?? {
      client_id: attachmentId,
      attachment_id: attachmentId,
      filename: '',
      status: effectiveStatus,
      summary: '',
      linked,
      unlinked_reasons: [],
      error_code: null,
      error_message: null,
      integration_log_id: null,
      last_updated_at: new Date().toISOString(),
    };

  const friendly = summariseFile({ ...effectiveLog, status: effectiveStatus, linked });
  const errorCodeFriendly = effectiveLog.error_code
    ? ERROR_CODE_FRIENDLY[effectiveLog.error_code] ?? effectiveLog.error_code
    : null;

  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Clock className="size-3.5" />
        <span>
          Last run: {parseServerDate(effectiveLog.last_updated_at).toLocaleString()}
        </span>
      </div>

      <div className="text-foreground">{friendly}</div>

      {linked.length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Linked entities
          </div>
          <ul className="space-y-1">
            {linked.map((l) => (
              <li
                key={`${l.entity_type}-${l.entity_id}`}
                className="text-sm flex items-center gap-2"
              >
                <CheckCircle2 className="size-3.5 text-green-600 shrink-0" />
                <span className="font-medium">{l.display_name}</span>
                <span className="text-xs text-muted-foreground">
                  ({l.entity_type.replace('_', ' ')})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {effectiveLog.unlinked_reasons.length > 0 && linked.length === 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Why no match
          </div>
          <ul className="space-y-1">
            {effectiveLog.unlinked_reasons.map((r, i) => (
              <li key={i} className="text-sm text-muted-foreground">
                {r.reason}
              </li>
            ))}
          </ul>
          <div className="text-xs text-muted-foreground mt-2">
            Tip: open the Linkages section below to link this attachment
            manually.
          </div>
        </div>
      )}

      {(effectiveStatus === 'failed' || effectiveStatus === 'post_failed') && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
          <div className="font-medium text-destructive">
            {errorCodeFriendly ?? effectiveLog.error_message ?? 'Failed'}
          </div>
          {effectiveLog.error_message && errorCodeFriendly && (
            <div className="text-xs text-muted-foreground mt-1">
              {effectiveLog.error_message}
            </div>
          )}
          <div className="text-xs text-muted-foreground mt-2">
            Use the <span className="font-medium">Resubmit</span> button at
            the top to re-run the integration.
          </div>
        </div>
      )}

      {effectiveLog.integration_log_id && (
        <div className="pt-2 border-t border-border">
          <Link
            href={`/integration-management/integration-logs/${effectiveLog.integration_log_id}`}
            className="text-xs text-primary hover:underline inline-flex items-center gap-1"
          >
            View raw log
            <ExternalLink className="size-3" />
          </Link>
        </div>
      )}
    </div>
  );
}
