'use client';

/**
 * A proposal / quotation's History (QUOTE-AUTOSAVE, card rule 5).
 *
 * Lifted from the tag designer's `components/dealer-kit/RequestVersionsSheet.tsx`: newest first,
 * who and when, View draws the entry read-only, Restore loads it back. Restore runs at once with
 * no confirmation, the tag designer's rule: the server first keeps the state being left as
 * "Before restore to version N", then puts the entry into the DRAFT, so nothing is destroyed and
 * the record changes only on Save.
 */

import * as React from 'react';
import { Eye, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/lib/toast';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { formatMyrExact } from '../../../../_shared/lib/money';
import {
  getQuotationHistoryEntry,
  listQuotationHistory,
  type QuotationHistoryEntry,
  type QuotationHistoryEntryDetail,
  type QuotationHistoryKind,
} from '../../../../_shared/services/quotationDocumentService';

export const HISTORY_KIND_LABEL: Record<QuotationHistoryKind, string> = {
  saved: 'Saved',
  before_restore: 'Before restore',
  conflict: 'Not saved: opened in another tab',
};

/** "Version 3", and its note on the line under it, the tag designer's own History row. */
function entryNote(entry: QuotationHistoryEntry): string {
  return entry.note || HISTORY_KIND_LABEL[entry.kind];
}

export function QuotationHistorySheet({
  open,
  onOpenChange,
  projectId,
  documentId,
  documentNo,
  onRestore,
  readOnly = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  documentId: string;
  documentNo: string;
  onRestore: (entryId: string) => Promise<void>;
  /** A view-only tab (Q4) can look, not restore. */
  readOnly?: boolean;
}) {
  const [entries, setEntries] = React.useState<QuotationHistoryEntry[] | null>(null);
  const [restoring, setRestoring] = React.useState<string | null>(null);
  const [viewing, setViewing] = React.useState<QuotationHistoryEntryDetail | null>(null);

  const reload = React.useCallback(() => {
    setEntries(null);
    listQuotationHistory(projectId, documentId)
      .then(setEntries)
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : 'Failed to load the history');
        setEntries([]);
      });
  }, [projectId, documentId]);

  React.useEffect(() => {
    if (open) reload();
  }, [open, reload]);

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>History / {documentNo}</SheetTitle>
            <SheetDescription>Every save of this document, newest first.</SheetDescription>
          </SheetHeader>
          <SheetBody className="space-y-1 overflow-y-auto">
            {entries === null && (
              <div className="space-y-2 p-4">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            )}

            {entries?.length === 0 && (
              <div className="p-4">
                <h3 className="text-sm font-semibold">No history yet</h3>
                <p className="mt-1 text-sm text-muted-foreground">Each save adds an entry here.</p>
              </div>
            )}

            {entries?.map((entry) => (
              <div
                key={entry.id}
                className="flex flex-col gap-2 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                data-testid={`quotation-history-${entry.id}`}
              >
                <div className="min-w-0">
                  <span className="text-sm font-medium">Version {entry.version}</span>
                  <p className="text-sm text-muted-foreground">{entryNote(entry)}</p>
                  {entry.grand_total !== null && (
                    <p className="text-sm text-muted-foreground">
                      {formatMyrExact(entry.grand_total)}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {entry.created_by_name || 'Unknown'}
                    {entry.created_at ? ` / ${formatDateTimeInMalaysia(entry.created_at)}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void getQuotationHistoryEntry(projectId, documentId, entry.id)
                        .then(setViewing)
                        .catch(() => toast.error('Could not open that entry'));
                    }}
                  >
                    <Eye className="size-3.5" />
                    View
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={readOnly || restoring === entry.id}
                    onClick={async () => {
                      setRestoring(entry.id);
                      try {
                        await onRestore(entry.id);
                        reload();
                      } finally {
                        setRestoring(null);
                      }
                    }}
                  >
                    <RotateCcw className="size-3.5" />
                    {restoring === entry.id ? 'Restoring...' : 'Restore'}
                  </Button>
                </div>
              </div>
            ))}
          </SheetBody>
        </SheetContent>
      </Sheet>

      <Dialog open={viewing !== null} onOpenChange={(next) => !next && setViewing(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          {viewing && <HistoryEntryView entry={viewing} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** One entry, read-only: the header it held and every line staged in it. */
function HistoryEntryView({ entry }: { entry: QuotationHistoryEntryDetail }) {
  // Stored client JSON: read defensively, so a malformed entry shows less rather than crashing.
  const header = entry.doc?.header ?? {};
  const scopes = Array.isArray(entry.doc?.scopes) ? entry.doc.scopes : [];
  const staged = entry.doc?.staged ?? {};
  const stored = entry.doc?.record_lines ?? {};
  return (
    <>
      <DialogHeader>
        <DialogTitle>Version {entry.version}</DialogTitle>
        <DialogDescription>
          {entryNote(entry)} / {entry.created_by_name || 'Unknown'}
          {entry.created_at ? ` / ${formatDateTimeInMalaysia(entry.created_at)}` : ''}
          {entry.grand_total !== null ? ` / ${formatMyrExact(entry.grand_total)}` : ''}
        </DialogDescription>
      </DialogHeader>
      <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Project title</dt>
        <dd className="min-w-0 break-words">{header.subject_title || '-'}</dd>
        <dt className="text-muted-foreground">Attn</dt>
        <dd className="min-w-0 break-words">{header.attn_name || '-'}</dd>
        <dt className="text-muted-foreground">Date</dt>
        <dd>{header.doc_date || '-'}</dd>
      </dl>
      {scopes.map((scope, index) => {
        const stagedLines = staged[scope.key]?.lines;
        // Staged lines when the entry has them, else the lines the record held at that moment.
        const lines: { key: string; code: string; qty: string; price: string; title: string }[] =
          Array.isArray(stagedLines)
            ? stagedLines
                .filter((line) => line && !line.removed)
                .map((line) => ({
                  key: line.key,
                  code: line.draft?.picked_code || line.draft?.description || 'Line',
                  qty: line.draft?.quantity ?? '',
                  price: line.draft?.unit_price ?? '',
                  title: line.draft?.description ?? '',
                }))
            : (Array.isArray(stored[scope.key]?.lines) ? stored[scope.key].lines : []).map(
                (line, index) => ({
                  key: line.id ?? `stored-${index}`,
                  code: line.description || 'Line',
                  qty: String(line.quantity ?? ''),
                  price: String(line.unit_price ?? ''),
                  title: line.description ?? '',
                }),
              );
        return (
          <section key={scope.key} className="mt-3 min-w-0">
            <h3 className="text-sm font-semibold">{scope.scope_label || `Scope ${index + 1}`}</h3>
            {lines.length === 0 ? (
              <p className="text-sm text-muted-foreground">No lines.</p>
            ) : (
              <ul className="mt-1 divide-y text-sm">
                {lines.map((line) => (
                  <li key={line.key} className="flex justify-between gap-3 py-1">
                    <span className="min-w-0 truncate" title={line.title}>
                      {line.code}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {line.qty || '-'} x {line.price || '-'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </>
  );
}
