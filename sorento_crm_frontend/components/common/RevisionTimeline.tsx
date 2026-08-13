'use client';

import { useState, type ReactNode } from 'react';
import { Paperclip } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { RevisionSnapshotDialog, revisionAttachmentPreviewItem } from './RevisionSnapshotDialog';

/**
 * The lineage of a revisable portal submission, as one vertical timeline
 * (UAC G4 / G8 / H3).
 *
 * Built on the same shape as the packing-list clearance timeline
 * (`ClearanceDeliveryCard`): an ordered list, a dot per entry, a hairline
 * connector that stops after the last one. Same visual language for the same
 * idea, rather than a second one.
 *
 * Read-only on both sides - the office never creates, edits or deletes a
 * revision (UAC G5 / H5).
 */

export interface RevisionChange {
  field: string;
  label: string;
  from: unknown;
  to: unknown;
}

export interface RevisionAttachment {
  attachment_id: string;
  link_id?: string | null;
  filename?: string | null;
  size?: number | null;
  mime?: string | null;
  /** Signed url for the file as this version carried it, resolved by the backend
   *  at read time (`_attachment_urls`) - including for a file whose link a later
   *  revision removed. Without it the preview can only offer its download card:
   *  `<img>`/`<video>`/`<iframe>` cannot send an auth header, so the modal renders
   *  inline only for an absolute http/blob/data url. */
  url?: string | null;
}

/** One stage a revision voided, and who was working it. */
export interface RevisionVoidedStage {
  stage_code?: string | null;
  assignee_name?: string | null;
}

/** One labeled field of a revision's snapshot, in form order - the backend
 *  renders these from the adapter's own field list so neither side keeps a
 *  second copy that could drift. `products` carries the line-item list. */
export interface RevisionSnapshotField {
  field: string;
  label: string;
  value: unknown;
  /** Server-rendered presentation of `value` (a lookup option's label, a
   *  DD/MM/YYYY date). Null when the raw value already reads correctly. */
  display?: string | null;
}

export interface FormRevisionEntry {
  id: string;
  version_no: number;
  revision_no: number;
  kind: string;
  label: string;
  reason?: string | null;
  submitted_at?: string | null;
  submitted_by?: string | null;
  is_reconstructed?: boolean;
  snapshot?: Record<string, unknown> | null;
  attachments?: RevisionAttachment[] | null;
  invalidated?: Record<string, unknown> | null;
  voided_stage_code?: string | null;
  voided_assignee_name?: string | null;
  /** EVERY stage this revision voided, newest first. Optional: a revision row
   *  written before `voided_stages_json` existed carries only the scalar pair
   *  above, which `resolveVoidedStages` falls back to. */
  voided_stages?: RevisionVoidedStage[] | null;
  changes?: RevisionChange[] | null;
  /** The whole form at this version, labeled and ordered. Optional: absent on a
   *  payload from a backend that predates the full-form viewer. */
  snapshot_fields?: RevisionSnapshotField[] | null;
}

/**
 * Every stage one revision voided, newest first.
 *
 * A form can sit with two stages open at once (a purchase request with project
 * sales and approval), and a revision voids all of them and tells all of their
 * handlers. Rendering the scalar `voided_stage_code` alone therefore names one
 * person while two were told to stop.
 *
 * The list wins where present; the scalar pair is the fallback for a row written
 * before the column existed. Shared by the office timeline and the contact's
 * history so the two sides cannot report different stages for the same event.
 */
export function resolveVoidedStages(entry: {
  voided_stages?: RevisionVoidedStage[] | null;
  voided_stage_code?: string | null;
  voided_assignee_name?: string | null;
}): { code: string; name: string }[] {
  const normalize = (code: unknown, name: unknown) => ({
    code: String(code ?? '').trim(),
    name: String(name ?? '').trim(),
  });
  const listed = (entry.voided_stages ?? [])
    .map((stage) => normalize(stage?.stage_code, stage?.assignee_name))
    .filter((stage) => stage.code.length > 0);
  if (listed.length > 0) return listed;
  const scalar = normalize(entry.voided_stage_code, entry.voided_assignee_name);
  return scalar.code ? [scalar] : [];
}

/** Stage output that a revision superseded, by column name. Anything not listed
 *  is skipped: the remaining invalidated columns hold ids and timestamps, and an
 *  id has no place on screen. */
const INVALIDATED_LABELS: Record<string, string> = {
  purchasing_response: 'Purchasing response',
  approval_comments: 'Approval comments',
  approval_status: 'Approval status',
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'blank';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function humanizeStage(code: string): string {
  return code.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Where the office reads an attachment's bytes.
 *
 * This timeline is office-only (the portal has its own history component), so the
 * route is stated here rather than pushed onto every mounting page. Keyed on the
 * ATTACHMENT id, not a link id - the same route the stock inquiry and purchase
 * request attachment sections use - because a file dropped by a later revision has
 * no `EntityAttachmentLink` left, and that is exactly the file history exists to
 * show.
 */
const officeAttachmentDownloadUrl = (attachmentId: string) =>
  `/api/v1/resource-management/attachments/${attachmentId}/download`;

export interface RevisionTimelineProps {
  entries: FormRevisionEntry[];
  /** Office side additionally shows which stage each revision voided (UAC H3). */
  showVoidedStage?: boolean;
  /**
   * Extra actions for one entry, rendered beside "View full form" (round 6, 6.3).
   *
   * A render prop rather than built-in buttons: exporting a revision needs the
   * form type, the live record and the export mutations, none of which belong in
   * a shared presentation component that the contact portal mounts siblings of.
   * Absent - as it is on the portal - and the row is exactly what it was.
   */
  entryActions?: (entry: FormRevisionEntry) => ReactNode;
}

export function RevisionTimeline({
  entries,
  showVoidedStage = false,
  entryActions,
}: RevisionTimelineProps) {
  // The full form of one revision, opened read-only from its timeline entry.
  const [snapshotEntry, setSnapshotEntry] = useState<FormRevisionEntry | null>(null);
  // A file as one version carried it, opened in the shared preview - the same
  // thing the contact gets on the portal, and the same thing the office gets on
  // the live form's attachment list.
  const [preview, setPreview] = useState<{
    items: AttachmentPreviewItem[];
    index: number;
  } | null>(null);

  return (
    <>
      <ol className="relative">
        {entries.map((entry, index) => {
          const changes = entry.changes ?? [];
          const attachments = entry.attachments ?? [];
          const invalidated = Object.entries(entry.invalidated ?? {}).filter(
            ([key, value]) => INVALIDATED_LABELS[key] && value !== null && value !== '',
          );
          const voidedStages = resolveVoidedStages(entry);

          return (
            <li key={entry.id} className="relative flex gap-4 pb-6 last:pb-0">
              {index < entries.length - 1 && (
                <span aria-hidden className="absolute start-[7px] top-4 h-full w-px bg-border" />
              )}
              <span
                aria-hidden
                className="relative mt-1 size-3.5 shrink-0 rounded-full bg-primary/70"
              />
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
                  <p className="text-sm font-medium break-words">{entry.label}</p>
                  {entry.submitted_at && (
                    <p className="shrink-0 text-sm text-muted-foreground tabular-nums">
                      {formatDateTimeInMalaysia(entry.submitted_at)}
                    </p>
                  )}
                </div>

                {entry.submitted_by && (
                  <p className="text-sm text-muted-foreground break-words">{entry.submitted_by}</p>
                )}

                {entry.reason ? (
                  <p className="text-sm break-words whitespace-pre-wrap">{entry.reason}</p>
                ) : null}

                {showVoidedStage && voidedStages.length > 0 ? (
                  <ul>
                    {voidedStages.map((stage, stageIndex) => (
                      <li
                        key={`${entry.id}-voided-${stage.code}-${stageIndex}`}
                        className="text-sm text-muted-foreground break-words"
                        data-testid="revision-voided-stage"
                      >
                        {/* The label sits on the first line only, pluralised when a
                            revision stopped more than one stage. One stage per line
                            so a two-stage cancellation still reads at 375px. */}
                        {stageIndex === 0
                          ? `Voided stage${voidedStages.length > 1 ? 's' : ''}: `
                          : ''}
                        {humanizeStage(stage.code)}
                        {stage.name ? ` · ${stage.name}` : ''}
                      </li>
                    ))}
                  </ul>
                ) : null}

                {changes.length > 0 && (
                  <ul className="space-y-1">
                    {changes.map((change) => (
                      <li key={`${entry.id}-${change.field}`} className="text-sm break-words">
                        <span className="text-muted-foreground">{change.label}: </span>
                        <span className="line-through">{formatValue(change.from)}</span>
                        <span className="text-muted-foreground"> to </span>
                        <span className="font-medium">{formatValue(change.to)}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {invalidated.length > 0 && (
                  <ul className="space-y-1">
                    {invalidated.map(([key, value]) => (
                      <li key={`${entry.id}-inv-${key}`} className="text-sm break-words">
                        <span className="text-muted-foreground">
                          {INVALIDATED_LABELS[key]} (superseded):{' '}
                        </span>
                        <span className="whitespace-pre-wrap">{formatValue(value)}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {attachments.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {attachments.map((attachment, fileIndex) => (
                      <Badge
                        key={`${entry.id}-${attachment.attachment_id}`}
                        variant="secondary"
                        className="max-w-[220px]"
                        asChild
                      >
                        <button
                          type="button"
                          onClick={() =>
                            setPreview({
                              items: attachments.map((file) =>
                                revisionAttachmentPreviewItem(file, officeAttachmentDownloadUrl),
                              ),
                              index: fileIndex,
                            })
                          }
                          aria-label={`Preview ${attachment.filename || 'attachment'}`}
                          // Tailwind's preflight gives a button `cursor: default`,
                          // so an openable file has to say so itself.
                          className="max-w-full cursor-pointer transition-colors hover:bg-secondary/80"
                          data-testid="revision-attachment"
                        >
                          <Paperclip className="h-3 w-3 mr-1 shrink-0" />
                          <span className="truncate" title={attachment.filename ?? undefined}>
                            {attachment.filename ?? 'Attachment'}
                          </span>
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}

                {/* The complete form at this version, not only the diff above,
                    plus whatever the mounting page offers for one version. Wraps
                    at 375px rather than pushing the row off the screen. */}
                {((entry.snapshot_fields?.length ?? 0) > 0 || entryActions) && (
                  <div className="flex flex-wrap items-center gap-2">
                    {(entry.snapshot_fields?.length ?? 0) > 0 && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setSnapshotEntry(entry)}
                        data-testid="revision-view-form"
                      >
                        View full form
                      </Button>
                    )}
                    {entryActions?.(entry)}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {/* No `fetchBytes`: the office has a JWT session, so the modal's default
          `apiFetch` is the correct reader. */}
      <RevisionSnapshotDialog
        entry={snapshotEntry}
        onOpenChange={(open) => !open && setSnapshotEntry(null)}
        attachmentDownloadUrl={officeAttachmentDownloadUrl}
      />

      <AttachmentPreviewModal
        open={Boolean(preview)}
        onOpenChange={(open) => !open && setPreview(null)}
        items={preview?.items ?? []}
        startIndex={preview?.index ?? 0}
      />
    </>
  );
}
