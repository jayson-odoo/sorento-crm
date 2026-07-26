'use client';

import * as React from 'react';
import { AlertTriangle, Lock, Pencil, Plus, Trash2, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  useQuotationLineMutations,
  useQuotationLines,
  useQuotationVersions,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  ProjectQuotation,
  QuotationLine,
} from '../../_shared/types/project.types';
import { QuotationLineDialog } from './QuotationLineDialog';
import { ReviseQuotationDialog } from './ReviseQuotationDialog';
import { formatMyr } from './QuotationsPanel';

const FLOOR_LEVEL_LABELS: Record<string, string> = {
  product: 'this product',
  category: 'its category',
  category_ancestor: 'a parent category',
  system: 'the company default',
};

/**
 * The versions of one scope, and the lines of whichever version is being looked at.
 *
 * Only the newest version is editable, and the editor works that out from the server's
 * `is_current` rather than from a local guess. Everything below it is history the
 * customer already holds (AC-E3), so an older version renders read-only with the reason
 * stated, not merely with its buttons missing.
 */
export function QuotationVersionEditor({
  project,
  quotation,
}: {
  project: Project;
  quotation: ProjectQuotation;
}) {
  const versions = useQuotationVersions(quotation.id);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [revising, setRevising] = React.useState(false);
  const [addingLine, setAddingLine] = React.useState(false);
  const [editingLine, setEditingLine] = React.useState<QuotationLine | null>(null);
  const [deletingLine, setDeletingLine] = React.useState<QuotationLine | null>(null);

  const rows = React.useMemo(
    () => [...(versions.data ?? [])].sort((a, b) => b.version_no - a.version_no),
    [versions.data],
  );
  const current = rows.find((version) => version.is_current) ?? null;
  const selected = rows.find((version) => version.id === selectedId) ?? current;

  const lines = useQuotationLines(selected?.id);
  const lineMutations = useQuotationLineMutations(project.id, selected?.id ?? '');

  const editable = Boolean(selected?.is_current) && project.can_edit;
  const sortedLines = React.useMemo(
    () => [...(lines.data ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [lines.data],
  );
  const nextSortOrder =
    sortedLines.length === 0
      ? 0
      : Math.max(...sortedLines.map((line) => line.sort_order)) + 10;

  if (versions.isLoading) return <Skeleton className="h-24 w-full" />;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          {rows.map((version) => (
            <button
              key={version.id}
              type="button"
              onClick={() => setSelectedId(version.id)}
              aria-current={selected?.id === version.id}
              className={
                selected?.id === version.id
                  ? 'rounded-md border border-primary bg-primary/10 px-2.5 py-1 text-xs font-medium'
                  : 'rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted'
              }
            >
              {`v${version.version_no}`}
              {version.is_current ? '' : ' (frozen)'}
            </button>
          ))}
        </div>

        {project.can_edit && current && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setRevising(true)}
          >
            {`Revise to v${current.version_no + 1}`}
          </Button>
        )}
      </div>

      {selected && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">
            {formatMyr(selected.total_amount)}
          </span>
          {selected.issued_by_name && <span>Issued by {selected.issued_by_name}</span>}
          {selected.created_at && (
            <span>Opened {formatDateTimeInMalaysia(selected.created_at)}</span>
          )}
          {!selected.is_current && selected.frozen_at && (
            <span className="flex items-center gap-1">
              <Lock className="size-3" aria-hidden />
              Frozen {formatDateTimeInMalaysia(selected.frozen_at)}
            </span>
          )}
        </div>
      )}

      {selected && !selected.is_current && (
        <p className="text-xs text-muted-foreground">
          This version is history. Editing it would change a quotation the customer
          already holds, so make changes on{' '}
          {current ? `v${current.version_no}` : 'the current version'} instead.
        </p>
      )}

      {lines.isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : sortedLines.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-6 py-8 text-center">
          <h4 className="text-sm font-semibold">No lines yet</h4>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {editable
              ? 'Add what is being quoted. Picking a product freezes its code, description and list price onto the line.'
              : 'This version was frozen without any lines.'}
          </p>
          {editable && (
            <Button
              type="button"
              size="sm"
              className="mt-3"
              onClick={() => setAddingLine(true)}
            >
              <Plus className="size-4" aria-hidden />
              Add the first line
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="py-1.5 pe-3 text-start font-medium">Item</th>
                <th className="py-1.5 pe-3 text-end font-medium">Qty</th>
                <th className="py-1.5 pe-3 text-end font-medium">Unit price</th>
                <th className="py-1.5 pe-3 text-end font-medium">Total</th>
                {editable && <th className="py-1.5 w-20" />}
              </tr>
            </thead>
            <tbody>
              {sortedLines.map((line) => (
                <tr key={line.id} className="border-b border-border/60 align-top">
                  <td className="py-2 pe-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {line.product_code ? (
                        <span className="font-medium">{line.product_code}</span>
                      ) : (
                        <Badge variant="outline" className="text-[11px]">
                          Off-catalog
                        </Badge>
                      )}
                      {line.is_below_floor && (
                        <Badge
                          variant="destructive"
                          className="gap-1 text-[11px]"
                          title={describeFloor(line)}
                        >
                          <AlertTriangle className="size-3" aria-hidden />
                          Below floor
                        </Badge>
                      )}
                      {line.is_non_standard && (
                        <Badge
                          variant="secondary"
                          className="gap-1 text-[11px]"
                          title="Outside the series this scope is quoted from"
                        >
                          <TriangleAlert className="size-3" aria-hidden />
                          Non-standard
                        </Badge>
                      )}
                    </div>
                    <div
                      className="mt-0.5 max-w-md truncate text-xs text-muted-foreground"
                      title={line.description ?? undefined}
                    >
                      {line.description ?? 'No description'}
                    </div>
                    {line.is_below_floor && (
                      <div className="mt-0.5 text-xs text-destructive">
                        {describeFloor(line)}
                      </div>
                    )}
                  </td>
                  <td className="py-2 pe-3 text-end whitespace-nowrap">
                    {trimAmount(line.quantity)}
                    {line.uom ? ` ${line.uom}` : ''}
                  </td>
                  <td className="py-2 pe-3 text-end whitespace-nowrap">
                    {formatMyr(line.unit_price)}
                    {line.list_price && (
                      <span className="block text-xs text-muted-foreground">
                        {`List ${formatMyr(line.list_price)}`}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pe-3 text-end font-medium whitespace-nowrap">
                    {formatMyr(line.line_total)}
                  </td>
                  {editable && (
                    <td className="py-2">
                      <div className="flex items-center justify-end gap-0.5">
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingLine(line)}
                          aria-label={`Edit ${line.product_code ?? 'line'}`}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeletingLine(line)}
                          aria-label={`Remove ${line.product_code ?? 'line'}`}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editable && sortedLines.length > 0 && (
        <Button type="button" size="sm" variant="outline" onClick={() => setAddingLine(true)}>
          <Plus className="size-4" aria-hidden />
          Add line
        </Button>
      )}

      {(addingLine || editingLine) && selected && (
        <QuotationLineDialog
          projectId={project.id}
          versionId={selected.id}
          line={editingLine}
          nextSortOrder={nextSortOrder}
          onDone={() => {
            setAddingLine(false);
            setEditingLine(null);
          }}
        />
      )}

      {revising && current && (
        <ReviseQuotationDialog
          projectId={project.id}
          quotation={quotation}
          currentVersionNo={current.version_no}
          lineCount={sortedLines.length}
          onDone={(newVersionId) => {
            setRevising(false);
            // Land on the version that was just opened, not the one being read a moment ago.
            if (newVersionId) setSelectedId(newVersionId);
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deletingLine)}
        onOpenChange={(next) => !next && setDeletingLine(null)}
        title="Confirm delete"
        description={
          deletingLine
            ? `Remove "${deletingLine.product_code ?? deletingLine.description}" from v${selected?.version_no}? This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (!deletingLine) return;
          await lineMutations.remove.mutateAsync(deletingLine.id);
        }}
        onSuccess={() => setDeletingLine(null)}
        successMessage="Line removed"
      />
    </div>
  );
}

/** Says which rule bit, so the salesperson knows whose policy to argue with. */
function describeFloor(line: QuotationLine): string {
  if (!line.floor_value_applied) return 'Below the floor for this item.';
  const level = line.floor_level_applied
    ? FLOOR_LEVEL_LABELS[line.floor_level_applied] ?? line.floor_level_applied
    : 'policy';
  return `Floor was ${formatMyr(line.floor_value_applied)}, set on ${level}.`;
}

/** Quantities come back as "2.00"; nobody writes two bathrooms as 2.00. */
function trimAmount(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return String(amount);
}
