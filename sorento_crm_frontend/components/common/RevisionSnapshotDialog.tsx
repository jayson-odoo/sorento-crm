'use client';

import { useEffect, useRef, useState } from 'react';
import { Paperclip } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type {
  FormRevisionEntry,
  RevisionAttachment,
  RevisionSnapshotField,
} from './RevisionTimeline';

/**
 * The whole form as it stood at one revision, read only.
 *
 * Rendered from the revision's own `snapshot_fields` - labeled by the backend
 * from the same adapter field list that drives the diff, never reconstructed
 * from the live row - so what the reader sees is the form AS IT WAS at that
 * version, not today's values. Shared by the office Revisions panel and the
 * contact's portal history so the two sides cannot present the same version
 * differently.
 *
 * Attachments open in the shared `AttachmentPreviewModal`, exactly as they do on
 * a live form. The two sides authenticate differently - the portal has a contact
 * token and no JWT session, the office has the session - so each supplies its own
 * `fetchBytes` and `attachmentDownloadUrl` rather than this component learning
 * about either. An earlier note here claimed both surfaces already offered
 * preview on the entry the dialog opens from; that was true of the portal only,
 * so the office had no preview of a historical file at all.
 */

/** The line-item keys the backend snapshots per product row, in form order. */
const PRODUCT_COLUMNS: { key: string; label: string }[] = [
  { key: 'item_code', label: 'Item code' },
  { key: 'quantity', label: 'Quantity' },
  { key: 'unit_price', label: 'Unit price' },
  { key: 'total', label: 'Total' },
  { key: 'remark', label: 'Remark' },
];

function isProductRows(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every((v) => v !== null && typeof v === 'object');
}

function formatScalar(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.map((v) => formatScalar(v)).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function FieldRow({ field }: { field: RevisionSnapshotField }) {
  // The backend owns presentation: it resolves a lookup code to its option label
  // and a snapshotted date to DD/MM/YYYY, so both surfaces read identically and
  // nothing here has to guess what a value means from its shape. The raw value is
  // the fallback for every field the server had nothing to add to.
  const text = field.display || formatScalar(field.value);
  return (
    <div className="min-w-0" data-testid="snapshot-field">
      <p className="text-xs text-muted-foreground">{field.label}</p>
      {text ? (
        <p className="text-sm break-words whitespace-pre-wrap">{text}</p>
      ) : (
        <p className="text-sm text-muted-foreground/70 italic">Not provided</p>
      )}
    </div>
  );
}

function ProductsTable({ rows }: { rows: Record<string, unknown>[] }) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-start">
            {PRODUCT_COLUMNS.map((col) => (
              <th key={col.key} className="px-3 py-2 text-start text-xs font-medium">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b last:border-0" data-testid="snapshot-product-row">
              {PRODUCT_COLUMNS.map((col) => (
                <td key={col.key} className="px-3 py-2 align-top break-words">
                  {formatScalar(row[col.key]) || <span className="text-muted-foreground/70">-</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * One snapshotted file as a preview item.
 *
 * The entry's own signed `url` is what makes an image or a PDF render inline -
 * the modal only embeds an absolute http/blob/data url, because an `<img>` cannot
 * send an auth header. `downloadUrl` is per-side (the office JWT route, the portal
 * token route), so it is supplied by the caller; with neither the modal still
 * opens and shows its fallback card.
 */
export function revisionAttachmentPreviewItem(
  attachment: RevisionAttachment,
  attachmentDownloadUrl?: (attachmentId: string) => string,
): AttachmentPreviewItem {
  return {
    id: attachment.attachment_id,
    name: attachment.filename || 'Attachment',
    url: attachment.url ?? '',
    downloadUrl: attachment.attachment_id
      ? attachmentDownloadUrl?.(attachment.attachment_id)
      : undefined,
    sizeBytes: attachment.size ?? null,
  };
}

export interface RevisionSnapshotDialogProps {
  /** The revision whose form is being read; null closes the dialog. */
  entry: FormRevisionEntry | null;
  onOpenChange: (open: boolean) => void;
  /**
   * How to read an attachment's bytes (Download button, Excel inline preview).
   * Omit on the office side - the modal's default `apiFetch` carries the JWT
   * session. The portal passes its token-authenticated fetch, which is the only
   * way bytes are readable there.
   */
  fetchBytes?: (item: AttachmentPreviewItem) => Promise<Response>;
  /** The side's own byte route for an attachment id. Keyed on the attachment,
   *  never on a link: a file dropped by a later revision has no link row left. */
  attachmentDownloadUrl?: (attachmentId: string) => string;
}

export function RevisionSnapshotDialog({
  entry,
  onOpenChange,
  fetchBytes,
  attachmentDownloadUrl,
}: RevisionSnapshotDialogProps) {
  // The dialog closes by `entry` going null, but it stays mounted through the
  // close animation - reading straight off `entry` would blank the title and every
  // value for the length of that fade. Keep the last one and render from it.
  const lastEntry = useRef<FormRevisionEntry | null>(entry);
  useEffect(() => {
    if (entry) lastEntry.current = entry;
  }, [entry]);
  const shown = entry ?? lastEntry.current;

  const fields = shown?.snapshot_fields ?? [];
  const scalarFields = fields.filter((f) => f.field !== 'products');
  const productField = fields.find((f) => f.field === 'products');
  const productRows = productField && isProductRows(productField.value) ? productField.value : [];
  // The files as they stood at THIS version, off the same snapshot row - a file
  // a later revision removed is still listed here, which is the point.
  const attachments = shown?.attachments ?? [];
  const previewItems = attachments.map((attachment) =>
    revisionAttachmentPreviewItem(attachment, attachmentDownloadUrl),
  );

  // Which file the reader opened, or null. Cleared when this dialog closes, so a
  // preview left open on one version never reappears over the next one.
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  useEffect(() => {
    if (!entry) setPreviewIndex(null);
  }, [entry]);

  const when = shown?.submitted_at ? formatDateTimeInMalaysia(shown.submitted_at) : '';

  return (
    <>
      <Dialog open={Boolean(entry)} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{shown?.label ?? ''}</DialogTitle>
            <DialogDescription>
              The form as it was at this version
              {when ? `, sent ${when}` : ''}
              {shown?.submitted_by ? ` by ${shown.submitted_by}` : ''}.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[65vh] space-y-3 overflow-y-auto">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {scalarFields.map((field) => (
                <FieldRow key={field.field} field={field} />
              ))}
            </div>

            {productField && (
              <div className="space-y-1.5">
                <p className="text-xs text-muted-foreground">{productField.label}</p>
                {productRows.length > 0 ? (
                  <ProductsTable rows={productRows} />
                ) : (
                  <p className="text-sm text-muted-foreground/70 italic">Not provided</p>
                )}
              </div>
            )}

            <div className="space-y-1.5">
              <p className="text-xs text-muted-foreground">Attachments</p>
              {attachments.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {attachments.map((attachment, i) => (
                    <Badge
                      key={`${attachment.attachment_id ?? i}`}
                      variant="secondary"
                      className="max-w-[220px]"
                      asChild
                    >
                      <button
                        type="button"
                        onClick={() => setPreviewIndex(i)}
                        aria-label={`Preview ${attachment.filename || 'attachment'}`}
                        className="max-w-full"
                        data-testid="snapshot-attachment"
                      >
                        <Paperclip className="h-3 w-3 mr-1 shrink-0" />
                        <span className="truncate" title={attachment.filename ?? undefined}>
                          {attachment.filename ?? 'Attachment'}
                        </span>
                      </button>
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground/70 italic">None</p>
              )}
            </div>
          </DialogBody>
        </DialogContent>
      </Dialog>

      {/* Sibling of the dialog, not a child of its content: the content unmounts
          on close, and the preview must survive its own close animation. Radix
          stacks the two, so Escape closes the preview first and the version
          stays open underneath - the reader lands back where they were. */}
      <AttachmentPreviewModal
        open={previewIndex !== null}
        onOpenChange={(open) => !open && setPreviewIndex(null)}
        items={previewItems}
        startIndex={previewIndex ?? 0}
        {...(fetchBytes ? { fetchBytes } : {})}
      />
    </>
  );
}
