'use client';

import { useMemo, useState } from 'react';
import { Paperclip } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { RevisionSnapshotDialog } from '@/components/common/RevisionSnapshotDialog';
import { resolveVoidedStages } from '@/components/common/RevisionTimeline';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type {
  PortalAttachment,
  PortalRevisionAttachment,
  PortalRevisionEntry,
} from '../lib/portal-client';
import { portalAttachmentDownloadUrl } from '../lib/portal-client';
import { portalFetchBytes } from '../lib/portal-preview';

/**
 * The lineage of one submission as a vertical timeline: the original, every
 * revision since, what changed at each step, and the files as they stood at
 * that moment.
 *
 * Follows the packing-list clearance timeline (`ClearanceDeliveryCard`) rather
 * than inventing a second visual language for the same idea: ordered list, one
 * connector line, one dot per entry.
 *
 * Read only. Always rendered, including when the original is the only version.
 */

/**
 * When a version was sent, in Malaysia time.
 *
 * The backend emits `submitted_at` as naive UTC with no `Z`, so `new Date(value)`
 * would read it as the viewer's local clock and a revision sent at 13:30 MYT
 * would show 05:30 to the contact while the office page (`RevisionTimeline`,
 * same helper) showed 1:30 PM. One event, one wall clock, on both sides.
 */
function formatWhen(value: string | null): string {
  if (!value) return '';
  return formatDateTimeInMalaysia(value);
}

/**
 * Stage output a revision superseded, shown beside the version it answered.
 *
 * A whitelist, not a loop over the payload: the invalidated set also carries
 * `last_responded_by` / `approved_by`, which are user ids, and no id ever
 * reaches a contact's screen.
 */
const SUPERSEDED_LABELS: Record<string, string> = {
  purchasing_response: 'Superseded reply',
  approval_status: 'Superseded approval',
  approval_comments: 'Superseded approval comments',
};

function supersededRows(
  invalidated: Record<string, unknown> | null,
): { label: string; value: string }[] {
  if (!invalidated) return [];
  return Object.entries(SUPERSEDED_LABELS)
    .map(([key, label]) => ({ label, value: String(invalidated[key] ?? '').trim() }))
    .filter((row) => row.value.length > 0);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '(empty)';
  if (Array.isArray(value)) {
    return value.length ? value.map((v) => formatValue(v)).join(', ') : '(empty)';
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/**
 * Preview item for a file as a past version carried it.
 *
 * The snapshot's own `url` wins: the backend signs one per snapshot entry at read
 * time, including for a file whose link a later revision removed, which is the
 * whole mechanism that keeps a historical file previewable inline (UAC I2a). The
 * submission's CURRENT attachment list is only a fallback, for a payload that
 * predates the signed url. With neither, the shared modal shows its download
 * card, whose bytes still come through the portal token route.
 */
function toHistoryPreviewItem(
  file: PortalRevisionAttachment,
  urlByAttachmentId: Record<string, string>,
): AttachmentPreviewItem {
  return {
    id: file.attachment_id,
    name: file.filename || 'Attachment',
    url: file.url || urlByAttachmentId[file.attachment_id] || '',
    downloadUrl: file.attachment_id
      ? portalAttachmentDownloadUrl(file.attachment_id)
      : undefined,
    sizeBytes: file.size ?? null,
  };
}

export function RevisionHistory({
  entries,
  loading,
  error,
  currentAttachments = [],
}: {
  entries: PortalRevisionEntry[];
  loading?: boolean;
  error?: string | null;
  /** The submission's live attachments. Fallback only: a url for a file a past
   *  version shares with the current one, when the snapshot entry carries none. */
  currentAttachments?: PortalAttachment[];
}) {
  const [preview, setPreview] = useState<{
    items: AttachmentPreviewItem[];
    index: number;
  } | null>(null);
  // The full form of one revision, opened read-only from its history entry.
  const [snapshotEntry, setSnapshotEntry] = useState<PortalRevisionEntry | null>(null);

  const urlByAttachmentId = useMemo(() => {
    const out: Record<string, string> = {};
    for (const a of currentAttachments) {
      if (a.attachment_id && a.url) out[a.attachment_id] = a.url;
    }
    return out;
  }, [currentAttachments]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Revision history</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="mt-1 size-3.5 rounded-full" />
                <div className="flex-1 space-y-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="text-sm text-destructive break-words">{error}</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">Original submission only.</p>
        ) : (
          <ol className="relative">
            {entries.map((entry, index) => {
              const files = entry.attachments ?? [];
              const items = files.map((f) => toHistoryPreviewItem(f, urlByAttachmentId));
              const when = formatWhen(entry.submitted_at);
              return (
                <li
                  key={entry.id}
                  className="relative flex gap-3 pb-6 last:pb-0"
                  data-testid="revision-entry"
                >
                  {index < entries.length - 1 && (
                    <span
                      aria-hidden
                      className="absolute start-[7px] top-4 h-full w-px bg-border"
                    />
                  )}
                  <span
                    aria-hidden
                    className="relative mt-1 size-3.5 shrink-0 rounded-full bg-primary/70"
                  />
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                      <p className="text-sm font-medium break-words">{entry.label}</p>
                      {when && (
                        <p className="shrink-0 text-xs text-muted-foreground tabular-nums">
                          {when}
                        </p>
                      )}
                    </div>
                    {entry.submitted_by && (
                      <p className="text-xs text-muted-foreground break-words">
                        {entry.submitted_by}
                      </p>
                    )}
                    {entry.reason && (
                      <p className="text-sm whitespace-pre-wrap break-words">
                        {entry.reason}
                      </p>
                    )}
                    {entry.changes.length > 0 && (
                      <ul className="space-y-1">
                        {entry.changes.map((change, i) => (
                          <li
                            key={`${entry.id}-${change.field}-${i}`}
                            className="text-xs break-words"
                            data-testid="revision-change"
                          >
                            <span className="text-muted-foreground">{change.label}: </span>
                            <span className="text-muted-foreground line-through">
                              {formatValue(change.from)}
                            </span>
                            <span className="px-1" aria-hidden>
                              →
                            </span>
                            <span className="font-medium">{formatValue(change.to)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {supersededRows(entry.invalidated).map((row) => (
                      <p
                        key={`${entry.id}-${row.label}`}
                        className="text-xs break-words"
                        data-testid="revision-superseded"
                      >
                        <span className="text-muted-foreground">{row.label}: </span>
                        {row.value}
                      </p>
                    ))}
                    {/* Every stage this revision stopped, not just the newest: a
                        request can sit with two stages open, and both handlers were
                        told to stop. Label on the first line only. */}
                    {resolveVoidedStages(entry).map((stage, stageIndex) => (
                      <p
                        key={`${entry.id}-voided-${stage.code}-${stageIndex}`}
                        className="text-xs text-muted-foreground break-words"
                        data-testid="revision-voided-stage"
                      >
                        {stageIndex === 0 ? 'Stopped: ' : ''}
                        {stage.code.replace(/_/g, ' ')}
                        {stage.name ? ` (${stage.name})` : ''}
                      </p>
                    ))}
                    {files.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-0.5">
                        {files.map((file, fileIndex) => (
                          <Badge
                            key={`${entry.id}-${file.attachment_id}`}
                            variant="secondary"
                            asChild
                          >
                            <button
                              type="button"
                              onClick={() => setPreview({ items, index: fileIndex })}
                              aria-label={`Preview ${file.filename || 'attachment'}`}
                              className="max-w-full"
                            >
                              <Paperclip className="h-3 w-3 mr-1 shrink-0" />
                              <span className="truncate">
                                {file.filename || 'Attachment'}
                              </span>
                            </button>
                          </Badge>
                        ))}
                      </div>
                    )}

                    {/* The complete form at this version, not only the change
                        summary. Only offered when the payload carries the
                        labeled snapshot. */}
                    {(entry.snapshot_fields?.length ?? 0) > 0 && (
                      <div className="pt-0.5">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setSnapshotEntry(entry)}
                          data-testid="revision-view-form"
                        >
                          View full form
                        </Button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>

      <AttachmentPreviewModal
        open={Boolean(preview)}
        onOpenChange={(open) => !open && setPreview(null)}
        items={preview?.items ?? []}
        startIndex={preview?.index ?? 0}
        fetchBytes={portalFetchBytes}
      />

      {/* The portal has no JWT session, so the dialog's preview reads bytes
          through the same token-authenticated path this page already uses. */}
      <RevisionSnapshotDialog
        entry={snapshotEntry}
        onOpenChange={(open) => !open && setSnapshotEntry(null)}
        fetchBytes={portalFetchBytes}
        attachmentDownloadUrl={portalAttachmentDownloadUrl}
      />
    </Card>
  );
}
