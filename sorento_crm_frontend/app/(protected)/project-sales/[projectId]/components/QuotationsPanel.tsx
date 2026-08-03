'use client';

import * as React from 'react';
import { AlertTriangle, FileStack, Plus, Trash2, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  useQuotationMutations,
  useQuotations,
} from '../../_shared/hooks/useProjects';
import { OutcomePill } from '../../_shared/components/OutcomePill';
import type { Project, ProjectQuotation } from '../../_shared/types/project.types';
import { QuotationDialog } from './QuotationDialog';
import { QuotationOutcomeDialog } from './QuotationOutcomeDialog';
import { QuotationVersionEditor } from './QuotationVersionEditor';

/**
 * The priced scopes of a project (AC-E1), each with its own version history.
 *
 * Scope-per-quotation is the model, not a convenience: House Units and Common Area are
 * won or lost separately, which is exactly why the PROJECT's outcome is derived rather
 * than set (AC-E10). A project with a won house-unit scope and an open common-area scope
 * is still live, and this panel has to make that readable at a glance.
 */
export function QuotationsPanel({ project }: { project: Project }) {
  const quotations = useQuotations(project.id);
  const { remove } = useQuotationMutations(project.id);

  const [creating, setCreating] = React.useState(false);
  const [editing, setEditing] = React.useState<ProjectQuotation | null>(null);
  const [deciding, setDeciding] = React.useState<ProjectQuotation | null>(null);
  const [deleting, setDeleting] = React.useState<ProjectQuotation | null>(null);
  const [openId, setOpenId] = React.useState<string | null>(null);

  const rows = React.useMemo(() => quotations.data ?? [], [quotations.data]);

  // Land on the first scope so the tab is not an accordion the user must open to see
  // anything. One click saved on the common single-scope case.
  React.useEffect(() => {
    if (!openId && rows.length > 0) setOpenId(rows[0].id);
  }, [openId, rows]);

  const totalBelowFloor = rows.reduce((sum, row) => sum + row.below_floor_count, 0);
  const totalNonStandard = rows.reduce((sum, row) => sum + row.non_standard_count, 0);

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-sm">Quotations</CardTitle>
          </div>
          {project.can_edit && (
            <Button type="button" size="sm" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden />
              Add a scope
            </Button>
          )}
        </CardHeader>

        <CardContent className="space-y-3">
          {rows.length > 0 && (totalBelowFloor > 0 || totalNonStandard > 0) && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {totalBelowFloor > 0 && (
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="size-3" aria-hidden />
                  {`${totalBelowFloor} below the price floor`}
                </Badge>
              )}
              {totalNonStandard > 0 && (
                <Badge variant="secondary" className="gap-1">
                  <TriangleAlert className="size-3" aria-hidden />
                  {`${totalNonStandard} non-standard`}
                </Badge>
              )}
            </div>
          )}

          {quotations.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : quotations.isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8 text-center">
              <h3 className="text-sm font-semibold text-destructive">
                Quotations could not be loaded
              </h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {quotations.error instanceof Error
                  ? quotations.error.message
                  : 'Try again shortly.'}
              </p>
            </div>
          ) : rows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
              <h3 className="text-sm font-semibold">Nothing priced yet</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                Add a scope, e.g. House Units or Common Area. Version 1 opens with it,
                and editing it saves in place until you revise.
              </p>
              {project.can_edit && (
                <Button type="button" className="mt-4" onClick={() => setCreating(true)}>
                  <Plus className="size-4" aria-hidden />
                  Add the first scope
                </Button>
              )}
            </div>
          ) : (
            <ul className="space-y-2">
              {rows.map((quotation) => (
                <li key={quotation.id} className="rounded-lg border border-border">
                  <div className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:gap-3">
                    <button
                      type="button"
                      onClick={() =>
                        setOpenId((previous) =>
                          previous === quotation.id ? null : quotation.id,
                        )
                      }
                      aria-expanded={openId === quotation.id}
                      className="min-w-0 flex-1 text-left"
                    >
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="truncate text-sm font-medium" title={quotation.scope_label}>
                          {quotation.scope_label}
                        </span>
                        <OutcomePill outcome={quotation.outcome} />
                        {quotation.below_floor_count > 0 && (
                          <Badge variant="destructive" className="text-[11px]">
                            {`${quotation.below_floor_count} below floor`}
                          </Badge>
                        )}
                        {quotation.non_standard_count > 0 && (
                          <Badge variant="secondary" className="text-[11px]">
                            {`${quotation.non_standard_count} non-standard`}
                          </Badge>
                        )}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <FileStack className="size-3" aria-hidden />
                          {`v${quotation.current_version_no ?? 1} of ${quotation.version_count}`}
                        </span>
                        <span>
                          {quotation.current_total
                            ? formatMyr(quotation.current_total)
                            : 'Nothing priced'}
                        </span>
                        {quotation.series_name && <span>{quotation.series_name}</span>}
                        {quotation.loss_reason_label && (
                          <span>Lost: {quotation.loss_reason_label}</span>
                        )}
                      </span>
                    </button>

                    {project.can_edit && (
                      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setDeciding(quotation)}
                        >
                          {quotation.outcome === 'open' ? 'Record outcome' : 'Change outcome'}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setEditing(quotation)}
                        >
                          Edit
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleting(quotation)}
                          aria-label={`Delete ${quotation.scope_label}`}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                    )}
                  </div>

                  {openId === quotation.id && (
                    <div className="border-t border-border p-3">
                      <QuotationVersionEditor
                        project={project}
                        quotation={quotation}
                      />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {(creating || editing) && (
        <QuotationDialog
          project={project}
          quotation={editing}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      {deciding && (
        <QuotationOutcomeDialog
          project={project}
          quotation={deciding}
          onDone={() => setDeciding(null)}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Confirm delete"
        description={
          deleting
            ? `Delete the "${deleting.scope_label}" quotation and all ${deleting.version_count} of its versions? This action cannot be undone, and the project's outcome will be recalculated without it.`
            : ''
        }
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
        successMessage="Quotation deleted"
      />
    </>
  );
}

export function formatMyr(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return `RM ${amount.toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
