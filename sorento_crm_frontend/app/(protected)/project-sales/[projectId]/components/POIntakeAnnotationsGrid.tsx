'use client';

import * as React from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Check, Loader2, Pencil, X } from 'lucide-react';
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
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
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
 * Column preferences are keyed on this rather than on the pathname the DataGrid falls back
 * to: the path carries the version id, so the fallback would write one preferences row per
 * uploaded document instead of one per person. Same rule as the lines grid.
 */
export const PO_INTAKE_ANNOTATIONS_LISTING_KEY = 'projects.projects.view::po-annotations';

/**
 * One row per pencil note (AC-D4, D11).
 *
 * A strike-through on the paper does not cancel a line. Accepting the row does, and the row
 * says which lines it will change before the person commits to it. A rejected note is
 * recorded as rejected with its reason, never deleted.
 *
 * A document can carry a dozen notes, so this is the shared DataGrid, same as every other
 * list in the product: thirteen bespoke cards were thirteen things to read down a page.
 */
export function POIntakeAnnotationsGrid({
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

  const columns = React.useMemo<ColumnDef<POAnnotation>[]>(
    () => [
      {
        id: 'note_no',
        // The notes are in the order they were read off the paper, and that is the only
        // order worth reviewing them in, so no column here offers a sort.
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs tabular-nums">{row.index + 1}</span>
        ),
        size: 56,
        minSize: 48,
        enableSorting: false,
        meta: { headerTitle: '#', skeleton: <Skeleton className="h-4 w-5" /> },
      },
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.state === 'proposed' ? 'warning' : 'secondary'}>
            {PO_ANNOTATION_STATE_LABELS[row.original.state]}
          </Badge>
        ),
        size: 140,
        minSize: 110,
        enableSorting: false,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'interpretation',
        header: ({ column }) => (
          <DataGridColumnHeader title="What we read it as" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className="block truncate text-sm"
            title={PO_INTERPRETATION_LABELS[row.original.interpretation]}
          >
            {PO_INTERPRETATION_LABELS[row.original.interpretation]}
          </span>
        ),
        size: 170,
        minSize: 130,
        enableSorting: false,
        meta: {
          headerTitle: 'What we read it as',
          skeleton: <Skeleton className="h-4 w-24" />,
        },
      },
      {
        accessorKey: 'raw_text',
        header: ({ column }) => (
          <DataGridColumnHeader title="What is written" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className="block truncate text-sm font-medium"
            title={row.original.raw_text ?? undefined}
          >
            {row.original.raw_text || <Muted>Nothing legible was read</Muted>}
          </span>
        ),
        size: 280,
        minSize: 160,
        enableSorting: false,
        meta: {
          headerTitle: 'What is written',
          skeleton: <Skeleton className="h-4 w-40" />,
        },
      },
      {
        id: 'crop',
        header: ({ column }) => (
          <DataGridColumnHeader title="Handwriting" column={column} />
        ),
        // No placeholder when there is no crop: on a document with a dozen notes an
        // apology repeated a dozen times is noise, and the row already says what the
        // pencil says.
        cell: ({ row }) =>
          row.original.crop_url ? (
            <img
              src={row.original.crop_url}
              alt={
                row.original.raw_text ?? `Handwriting on page ${row.original.page_no}`
              }
              className="max-h-12 w-full rounded border border-border bg-white object-contain"
            />
          ) : null,
        size: 150,
        minSize: 100,
        enableSorting: false,
        meta: {
          headerTitle: 'Handwriting',
          skeleton: <Skeleton className="h-8 w-24" />,
        },
      },
      {
        accessorKey: 'written_date',
        header: ({ column }) => <DataGridColumnHeader title="Dated" column={column} />,
        cell: ({ row }) => (
          <span
            className="block truncate text-sm"
            title={row.original.written_date ?? undefined}
          >
            {row.original.written_date || <Muted>Not dated</Muted>}
          </span>
        ),
        size: 110,
        minSize: 90,
        enableSorting: false,
        meta: { headerTitle: 'Dated', skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        accessorKey: 'page_no',
        header: ({ column }) => <DataGridColumnHeader title="Page" column={column} />,
        cell: ({ row }) => (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0 text-xs"
            onClick={() => onShowPage(row.original.page_no)}
          >
            {`Page ${row.original.page_no}`}
          </Button>
        ),
        size: 92,
        minSize: 80,
        enableSorting: false,
        meta: { headerTitle: 'Page', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'refers_to_lines',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        cell: ({ row }) =>
          row.original.refers_to_lines.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {row.original.refers_to_lines.map((lineNo) => (
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
          ) : (
            <Muted>No lines named</Muted>
          ),
        size: 150,
        minSize: 110,
        enableSorting: false,
        meta: { headerTitle: 'Lines', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'effect',
        header: ({ column }) => (
          <DataGridColumnHeader title="What accepting does" column={column} />
        ),
        cell: ({ row }) => {
          const effect = describeAnnotationEffect(row.original, lines);
          const stillLive =
            row.original.interpretation === 'cancel_line' &&
            row.original.state === 'proposed';
          return (
            <div className="min-w-0 space-y-1">
              <span className="block truncate text-sm" title={effect}>
                {effect}
              </span>
              {/* Never a tooltip: a person has to see, without hovering, that the pencil
                  has changed nothing yet. */}
              {stillLive && (
                <span className="block text-xs font-medium text-destructive">
                  This line is still live until you accept.
                </span>
              )}
            </div>
          );
        },
        size: 300,
        minSize: 180,
        enableSorting: false,
        meta: {
          headerTitle: 'What accepting does',
          skeleton: <Skeleton className="h-4 w-44" />,
        },
      },
      {
        id: 'actioned',
        header: ({ column }) => <DataGridColumnHeader title="Reviewed" column={column} />,
        cell: ({ row }) => {
          const annotation = row.original;
          if (annotation.state === 'proposed') return <Muted>Not yet</Muted>;
          const who =
            [
              annotation.actioned_by_name ? `By ${annotation.actioned_by_name}` : null,
              annotation.actioned_at
                ? formatDateTimeInMalaysia(annotation.actioned_at)
                : null,
            ]
              .filter(Boolean)
              .join(' · ') || 'Reviewed';
          return (
            <div className="min-w-0 space-y-0.5">
              <span className="block truncate text-sm" title={who}>
                {who}
              </span>
              {annotation.action_note && (
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={annotation.action_note}
                >
                  {annotation.action_note}
                </span>
              )}
            </div>
          );
        },
        size: 200,
        minSize: 140,
        enableSorting: false,
        meta: { headerTitle: 'Reviewed', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const annotation = row.original;
          if (readOnly || annotation.state !== 'proposed') return null;
          const saving = savingAnnotationIds.includes(annotation.id);
          const noteNo = row.index + 1;
          return (
            <div className="flex flex-wrap items-center gap-1">
              <Button
                type="button"
                size="sm"
                disabled={saving}
                aria-label={`Accept note ${noteNo}`}
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
                aria-label={`Edit the reading of note ${noteNo}`}
                onClick={() => setEditing(annotation)}
              >
                <Pencil className="size-3.5" aria-hidden />
                Edit
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={saving}
                aria-label={`Reject note ${noteNo}`}
                onClick={() => {
                  setRejectNote('');
                  setRejecting(annotation);
                }}
              >
                <X className="size-3.5" aria-hidden />
                Reject
              </Button>
            </div>
          );
        },
        size: 240,
        minSize: 180,
        enableSorting: false,
        meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-4 w-20" /> },
      },
    ],
    [lines, onFocusLineNo, onShowPage, readOnly, savingAnnotationIds],
  );

  const table = useReactTable({
    columns,
    data: annotations,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

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
      <DataGrid
        table={table}
        recordCount={annotations.length}
        isLoading={false}
        listingKey={PO_INTAKE_ANNOTATIONS_LISTING_KEY}
        tableLayout={{ width: 'fixed', columnsResizable: true, headerSticky: true }}
      >
        <div className="min-w-0 rounded-lg border border-border">
          {/* The cap sits on the scrolling viewport, not on the box: a max-height on the
              Radix root only clips, because the viewport's `h-full` has no definite
              parent height to resolve against. */}
          <ScrollArea
            type="auto"
            className="w-full"
            viewportClassName="max-h-[calc(100vh-14rem)]"
          >
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      </DataGrid>

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

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-sm text-muted-foreground">{children}</span>;
}

/** What accepting this note will do, in the line numbers and money on this document. */
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
