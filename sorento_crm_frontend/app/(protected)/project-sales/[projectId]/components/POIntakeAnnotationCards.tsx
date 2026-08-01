'use client';

import * as React from 'react';
import { Check, ImageOff, Loader2, Pencil, X } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type {
  POAnnotation,
  POAnnotationEditBody,
  POVersionLine,
} from '../../_shared/types/poIntake.types';
import {
  PO_ANNOTATION_STATE_LABELS,
  PO_INTERPRETATION_LABELS,
} from '../../_shared/types/poIntake.types';
import { POIntakeAnnotationEditDialog } from './POIntakeAnnotationEditDialog';
import { formatMyrExact, formatQty } from './POIntakeMoney';

/**
 * One card per pencil note (AC-D4, D11).
 *
 * A strike-through on the paper does not cancel a line. Accepting the card does, and the
 * card says which lines it will change before the person commits to it. A rejected card is
 * recorded as rejected with its reason, never deleted.
 */
export function POIntakeAnnotationCards({
  annotations,
  lines,
  readOnly,
  savingAnnotationIds,
  onShowPage,
  onFocusLineNo,
  onAccept,
  onEdit,
  onReject,
}: {
  annotations: POAnnotation[];
  lines: POVersionLine[];
  readOnly: boolean;
  savingAnnotationIds: string[];
  onShowPage: (page: number) => void;
  onFocusLineNo: (lineNo: number) => void;
  onAccept: (annotationId: string, note?: string | null) => Promise<void>;
  onEdit: (annotationId: string, body: POAnnotationEditBody) => Promise<void>;
  onReject: (annotationId: string, note: string) => Promise<void>;
}) {
  const [accepting, setAccepting] = React.useState<POAnnotation | null>(null);
  const [rejecting, setRejecting] = React.useState<POAnnotation | null>(null);
  const [editing, setEditing] = React.useState<POAnnotation | null>(null);
  const [rejectNote, setRejectNote] = React.useState('');

  if (annotations.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border px-6 py-8 text-center">
        <h3 className="text-sm font-semibold">No handwriting was found on this scan</h3>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          If there is pencil on the paper, page through the scan on the left and check it
          before you confirm.
        </p>
      </div>
    );
  }

  return (
    <>
      <ul className="grid gap-3 lg:grid-cols-2">
        {annotations.map((annotation) => {
          const saving = savingAnnotationIds.includes(annotation.id);
          const effect = describeAnnotationEffect(annotation, lines);
          const destructive = annotation.interpretation === 'cancel_line';
          return (
            <li
              key={annotation.id}
              className="flex min-w-0 flex-col gap-3 rounded-lg border border-border p-3"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge
                  variant={annotation.state === 'proposed' ? 'warning' : 'secondary'}
                >
                  {PO_ANNOTATION_STATE_LABELS[annotation.state]}
                </Badge>
                <Badge variant="outline">
                  {PO_INTERPRETATION_LABELS[annotation.interpretation]}
                </Badge>
                {annotation.written_date && (
                  <span className="text-xs text-muted-foreground">
                    {annotation.written_date}
                  </span>
                )}
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="ml-auto text-xs"
                  onClick={() => onShowPage(annotation.page_no)}
                >
                  {`Page ${annotation.page_no}`}
                </Button>
              </div>

              {annotation.crop_url ? (
                <img
                  src={annotation.crop_url}
                  alt={annotation.raw_text ?? `Handwriting on page ${annotation.page_no}`}
                  className="max-h-32 w-full rounded border border-border bg-white object-contain"
                />
              ) : (
                <div className="flex items-center gap-2 rounded border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
                  <ImageOff className="size-4 shrink-0" aria-hidden />
                  No crop of this handwriting was captured.
                </div>
              )}

              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium break-words">
                  {annotation.raw_text || 'Nothing legible was read'}
                </p>
                <p className="text-xs text-muted-foreground break-words">{effect}</p>
              </div>

              {annotation.refers_to_lines.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {annotation.refers_to_lines.map((lineNo) => (
                    <Button
                      key={lineNo}
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => onFocusLineNo(lineNo)}
                    >
                      {`Line ${lineNo}`}
                    </Button>
                  ))}
                </div>
              )}

              {annotation.state !== 'proposed' && (
                <div className="min-w-0 space-y-0.5">
                  <p className="text-xs text-muted-foreground break-words">
                    {[
                      annotation.actioned_by_name
                        ? `By ${annotation.actioned_by_name}`
                        : null,
                      annotation.actioned_at
                        ? formatDateTimeInMalaysia(annotation.actioned_at)
                        : null,
                    ]
                      .filter(Boolean)
                      .join(' · ') || 'Reviewed'}
                  </p>
                  {annotation.action_note && (
                    <p className="text-xs text-muted-foreground break-words">
                      {annotation.action_note}
                    </p>
                  )}
                </div>
              )}

              {!readOnly && annotation.state === 'proposed' && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={saving}
                    onClick={() => setAccepting(annotation)}
                  >
                    {saving ? (
                      <Loader2 className="size-3.5 animate-spin" aria-hidden />
                    ) : (
                      <Check className="size-3.5" aria-hidden />
                    )}
                    Accept
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={saving}
                    onClick={() => setEditing(annotation)}
                  >
                    <Pencil className="size-3.5" aria-hidden />
                    Edit the reading
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={saving}
                    onClick={() => {
                      setRejectNote('');
                      setRejecting(annotation);
                    }}
                  >
                    <X className="size-3.5" aria-hidden />
                    Reject
                  </Button>
                </div>
              )}

              {destructive && annotation.state === 'proposed' && (
                <p className="text-xs font-medium text-destructive">
                  This line is still live until you accept.
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <AlertDialog
        open={Boolean(accepting)}
        onOpenChange={(next) => !next && setAccepting(null)}
      >
        <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle>Accept this note?</AlertDialogTitle>
            <AlertDialogDescription>
              {accepting ? describeAnnotationEffect(accepting, lines) : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Not yet</AlertDialogCancel>
            <AlertDialogAction
              className={
                accepting?.interpretation === 'cancel_line'
                  ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                  : undefined
              }
              onClick={() => {
                if (accepting) void onAccept(accepting.id);
                setAccepting(null);
              }}
            >
              {accepting?.interpretation === 'cancel_line'
                ? 'Accept and cancel'
                : 'Accept'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={Boolean(rejecting)}
        onOpenChange={(next) => !next && setRejecting(null)}
      >
        <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle>Reject this note?</AlertDialogTitle>
            <AlertDialogDescription>
              Nothing is applied. The note stays on the record as rejected, with your
              reason.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1.5">
            <label className="text-xs font-medium" htmlFor="po-annot-reject-note">
              Reason
            </label>
            <Textarea
              id="po-annot-reject-note"
              rows={3}
              value={rejectNote}
              onChange={(event) => setRejectNote(event.target.value)}
              placeholder="Why this does not change the PO"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it open</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={!rejectNote.trim()}
              onClick={() => {
                if (rejecting) void onReject(rejecting.id, rejectNote.trim());
                setRejecting(null);
              }}
            >
              Reject the note
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {editing && (
        <POIntakeAnnotationEditDialog
          annotation={editing}
          saving={savingAnnotationIds.includes(editing.id)}
          onClose={() => setEditing(null)}
          onSubmit={async (body) => {
            await onEdit(editing.id, body);
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

/** What accepting this card will do, in the line numbers and money on this document. */
export function describeAnnotationEffect(
  annotation: POAnnotation,
  lines: POVersionLine[],
): string {
  const json = (annotation.interpretation_json ?? {}) as Record<string, unknown>;
  const lineNos = Array.isArray(json.line_nos)
    ? (json.line_nos as unknown[]).map(Number).filter((value) => Number.isFinite(value))
    : annotation.refers_to_lines;
  const list = joinLineNos(lineNos);

  switch (annotation.interpretation) {
    case 'cancel_line': {
      if (lineNos.length === 0)
        return 'Cancels a line, but the line number was not read.';
      const named = lines.filter((line) => lineNos.includes(line.line_no));
      const detail = named
        .map(
          (line) =>
            `line ${line.line_no} (${line.stock_code_raw ?? 'no code'}, ${formatQty(line.qty)} ${line.uom_raw ?? ''}`.trim() +
            `, ${formatMyrExact(line.amount)})`,
        )
        .join('; ');
      return `Cancels ${detail || list}. The line stays on the record, marked cancelled, and drops out of our total.`;
    }
    case 'amend_code': {
      const code = typeof json.code === 'string' ? json.code : '';
      return code
        ? `Changes the code on ${list} to ${code}.`
        : `Changes the code on ${list}, but the new code was not read.`;
    }
    case 'amend_description': {
      const description = typeof json.description === 'string' ? json.description : '';
      return description
        ? `Changes the description on ${list} to "${description}".`
        : `Changes the description on ${list}, but the new wording was not read.`;
    }
    case 'successor_po': {
      const poNumber = typeof json.po_number === 'string' ? json.po_number : '';
      return poNumber
        ? `Records ${poNumber} as the PO that replaces this one. The link is made when that PO is uploaded.`
        : 'Names a replacement PO, but the number was not read.';
    }
    case 'signature':
      return 'Recorded as a signature. No line changes.';
    default:
      return 'Recorded as written. No line changes.';
  }
}

function joinLineNos(lineNos: number[]): string {
  if (lineNos.length === 0) return 'no lines';
  if (lineNos.length === 1) return `line ${lineNos[0]}`;
  const head = lineNos.slice(0, -1).join(', ');
  return `lines ${head} and ${lineNos[lineNos.length - 1]}`;
}
