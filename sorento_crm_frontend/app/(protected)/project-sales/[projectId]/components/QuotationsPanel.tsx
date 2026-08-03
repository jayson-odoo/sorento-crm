'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { AlertTriangle, FileStack, Plus, Trash2, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
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

  const columns = React.useMemo<ColumnDef<ProjectQuotation>[]>(
    () => [
      {
        id: 'scope_label',
        accessorFn: (row) => row.scope_label,
        header: ({ column }) => <DataGridColumnHeader title="Scope" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium" title={row.original.scope_label}>
            {row.original.scope_label}
          </span>
        ),
        size: 200,
        meta: { headerTitle: 'Scope' },
      },
      {
        id: 'outcome',
        accessorFn: (row) => row.outcome,
        header: ({ column }) => <DataGridColumnHeader title="Outcome" column={column} />,
        cell: ({ row }) => <OutcomePill outcome={row.original.outcome} />,
        size: 120,
        meta: { headerTitle: 'Outcome' },
      },
      {
        id: 'version',
        accessorFn: (row) => row.current_version_no ?? 1,
        header: ({ column }) => <DataGridColumnHeader title="Version" column={column} />,
        cell: ({ row }) => (
          <span className="flex min-w-0 items-center gap-1 text-sm">
            <FileStack className="size-3 shrink-0" aria-hidden />
            {`v${row.original.current_version_no ?? 1} of ${row.original.version_count}`}
          </span>
        ),
        size: 130,
        meta: { headerTitle: 'Version' },
      },
      {
        id: 'current_total',
        accessorFn: (row) => Number(row.current_total ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        cell: ({ row }) =>
          row.original.current_total ? (
            <span className="truncate text-sm font-medium">
              {formatMyr(row.original.current_total)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 150,
        meta: { headerTitle: 'Total' },
      },
      {
        id: 'alerts',
        accessorFn: (row) => row.below_floor_count + row.non_standard_count,
        // Readable WITHOUT opening the scope: the guardrail is the whole point of the tab,
        // so a panel that only showed these once expanded would hide what management asked
        // for.
        header: ({ column }) => <DataGridColumnHeader title="Alerts" column={column} />,
        cell: ({ row }) => {
          if (row.original.below_floor_count === 0 && row.original.non_standard_count === 0) {
            return <span className="text-muted-foreground">-</span>;
          }
          return (
            <div className="flex min-w-0 flex-wrap gap-1">
              {row.original.below_floor_count > 0 && (
                <Badge variant="destructive" appearance="light" className="text-[11px]">
                  {`${row.original.below_floor_count} below floor`}
                </Badge>
              )}
              {row.original.non_standard_count > 0 && (
                <Badge variant="warning" appearance="light" className="text-[11px]">
                  {`${row.original.non_standard_count} non-standard`}
                </Badge>
              )}
            </div>
          );
        },
        size: 210,
        meta: { headerTitle: 'Alerts' },
      },
      {
        id: 'series_name',
        accessorFn: (row) => row.series_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Series" column={column} />,
        cell: ({ row }) =>
          row.original.series_name ? (
            <span className="truncate text-sm" title={row.original.series_name}>
              {row.original.series_name}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 150,
        meta: { headerTitle: 'Series' },
      },
      {
        id: 'loss_reason_label',
        accessorFn: (row) => row.loss_reason_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Lost because" column={column} />,
        cell: ({ row }) =>
          row.original.loss_reason_label ? (
            <span className="truncate text-sm" title={row.original.loss_reason_label}>
              {row.original.loss_reason_label}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 170,
        meta: { headerTitle: 'Lost because' },
      },
      ...(project.can_edit
        ? [
            {
              id: 'actions',
              header: () => <span className="sr-only">Actions</span>,
              cell: ({ row }: { row: { original: ProjectQuotation } }) => (
                <div
                  className="flex flex-wrap items-center justify-end gap-1.5"
                  onClick={(event) => event.stopPropagation()}
                >
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setDeciding(row.original)}
                  >
                    {row.original.outcome === 'open' ? 'Record outcome' : 'Change outcome'}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(row.original)}
                  >
                    Edit
                  </Button>
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleting(row.original)}
                    aria-label={`Delete ${row.original.scope_label}`}
                  >
                    <Trash2 className="size-3.5 text-destructive" />
                  </Button>
                </div>
              ),
              size: 250,
              enableResizing: false,
              meta: { headerTitle: 'Actions' },
            } as ColumnDef<ProjectQuotation>,
          ]
        : []),
    ],
    [project.can_edit],
  );

  const open = rows.find((row) => row.id === openId) ?? null;

  return (
    <>
      <PanelDataGrid
        title="Quotations"
        toolbar={
          <>
            {totalBelowFloor > 0 && (
              <Badge variant="destructive" appearance="light" className="gap-1">
                <AlertTriangle className="size-3" aria-hidden />
                {`${totalBelowFloor} below the price floor`}
              </Badge>
            )}
            {totalNonStandard > 0 && (
              <Badge variant="warning" appearance="light" className="gap-1">
                <TriangleAlert className="size-3" aria-hidden />
                {`${totalNonStandard} non-standard`}
              </Badge>
            )}
            {project.can_edit && (
              <Button type="button" size="sm" onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden />
                Add a scope
              </Button>
            )}
          </>
        }
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        listingKey="projects.projects.view::project-quotations"
        isLoading={quotations.isLoading}
        error={quotations.isError ? quotations.error : undefined}
        emptyTitle="Nothing priced yet"
        emptyAction={
          project.can_edit ? (
            <Button type="button" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden />
              Add the first scope
            </Button>
          ) : undefined
        }
        // The version editor is a full form: it opens below the list rather than inside a
        // fixed-width cell.
        onRowClick={(row) => setOpenId((previous) => (previous === row.id ? null : row.id))}
      />

      {open && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{open.scope_label}</CardTitle>
          </CardHeader>
          <CardContent>
            <QuotationVersionEditor project={project} quotation={open} />
          </CardContent>
        </Card>
      )}

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
