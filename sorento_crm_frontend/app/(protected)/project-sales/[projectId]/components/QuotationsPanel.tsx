'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import type { ColumnDef } from '@tanstack/react-table';
import { AlertTriangle, FileStack, Plus, Trash2, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useProjectQuotationVersions,
  useQuotationMutations,
  useQuotations,
} from '../../_shared/hooks/useProjects';
import { OutcomePill } from '../../_shared/components/OutcomePill';
import type {
  Project,
  ProjectQuotation,
  QuotationVersion,
} from '../../_shared/types/project.types';
import { QuotationDialog } from './QuotationDialog';
import { QuotationOutcomeDialog } from './QuotationOutcomeDialog';

/**
 * Every quotation issued on this project, one row per REVISION.
 *
 * The list used to hold one row per scope showing only its current price, which hid the
 * thing people come here to read: what we quoted, when, and how it moved. The client's words
 * were "in this list i can see a list of quotation for this project which includes all those
 * revisions". So v1 and v2 of House Units are two rows, and the scope is a column.
 *
 * Scope-per-quotation is still the model, not a convenience: House Units and Common Area are
 * won or lost separately, which is why the PROJECT's outcome is derived rather than set
 * (AC-E10). A project with a won house-unit scope and an open common-area scope is still live.
 */
type RevisionRow = { quotation: ProjectQuotation; version: QuotationVersion };

export function QuotationsPanel({ project }: { project: Project }) {
  const router = useRouter();
  const quotations = useQuotations(project.id);
  const { remove } = useQuotationMutations(project.id);

  const [creating, setCreating] = React.useState(false);
  const [editing, setEditing] = React.useState<ProjectQuotation | null>(null);
  const [deciding, setDeciding] = React.useState<ProjectQuotation | null>(null);
  const [deleting, setDeleting] = React.useState<ProjectQuotation | null>(null);

  const rows = React.useMemo(() => quotations.data ?? [], [quotations.data]);


  const totalBelowFloor = rows.reduce((sum, row) => sum + row.below_floor_count, 0);
  const totalNonStandard = rows.reduce((sum, row) => sum + row.non_standard_count, 0);

  const revisions = useProjectQuotationVersions(quotations.data);

  // Newest first, grouped by scope: a reader scans down one scope's history, and the scopes
  // keep the order the list gives them.
  const revisionRows = React.useMemo(
    () =>
      [...revisions.rows].sort(
        (a, b) =>
          a.quotation.scope_label.localeCompare(b.quotation.scope_label) ||
          b.version.version_no - a.version.version_no,
      ),
    [revisions.rows],
  );

  const columns = React.useMemo<ColumnDef<RevisionRow>[]>(
    () => [
      {
        id: 'scope_label',
        accessorFn: (row) => row.quotation.scope_label,
        header: ({ column }) => <DataGridColumnHeader title="Scope" column={column} />,
        cell: ({ row }) => (
          <span
            className="truncate text-sm font-medium"
            title={row.original.quotation.scope_label}
          >
            {row.original.quotation.scope_label}
          </span>
        ),
        size: 190,
        meta: { headerTitle: 'Scope' },
      },
      {
        id: 'version_no',
        accessorFn: (row) => row.version.version_no,
        header: ({ column }) => <DataGridColumnHeader title="Revision" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center gap-1.5">
            <FileStack className="size-3 shrink-0 text-muted-foreground" aria-hidden />
            <span className="text-sm">{`v${row.original.version.version_no}`}</span>
            {/* Said outright, not implied by a missing badge: quoting off a frozen version
                is the expensive mistake. */}
            <Badge
              variant={row.original.version.is_current ? 'secondary' : 'warning'}
              appearance="light"
              className="shrink-0 text-[11px]"
            >
              {row.original.version.is_current ? 'Current' : 'Frozen'}
            </Badge>
          </div>
        ),
        size: 170,
        meta: { headerTitle: 'Revision' },
      },
      {
        id: 'total_amount',
        accessorFn: (row) => Number(row.version.total_amount ?? 0),
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium">
            {formatMyr(row.original.version.total_amount)}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Total' },
      },
      {
        id: 'outcome',
        accessorFn: (row) => row.quotation.outcome,
        header: ({ column }) => <DataGridColumnHeader title="Outcome" column={column} />,
        // The outcome belongs to the SCOPE, not to one revision, so it repeats down a
        // scope's rows. That is honest: v1 and v2 were not won separately.
        cell: ({ row }) => <OutcomePill outcome={row.original.quotation.outcome} />,
        size: 120,
        meta: { headerTitle: 'Outcome' },
      },
      {
        id: 'issued_by_name',
        accessorFn: (row) => row.version.issued_by_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Issued by" column={column} />,
        cell: ({ row }) =>
          row.original.version.issued_by_name ? (
            <span className="truncate text-sm">{row.original.version.issued_by_name}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 170,
        meta: { headerTitle: 'Issued by' },
      },
      {
        id: 'issued_on',
        accessorFn: (row) => row.version.issued_on ?? row.version.created_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Issued" column={column} />,
        cell: ({ row }) => {
          const at = row.original.version.issued_on ?? row.original.version.created_at;
          return at ? (
            <span className="truncate text-sm">{formatDateInMalaysia(at)}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          );
        },
        size: 130,
        meta: { headerTitle: 'Issued' },
      },
      {
        id: 'alerts',
        accessorFn: (row) =>
          row.quotation.below_floor_count + row.quotation.non_standard_count,
        // Readable WITHOUT opening the scope: the guardrail is the whole point of the tab.
        header: ({ column }) => <DataGridColumnHeader title="Alerts" column={column} />,
        cell: ({ row }) => {
          const { below_floor_count: floor, non_standard_count: nonStandard } =
            row.original.quotation;
          if (floor === 0 && nonStandard === 0) {
            return <span className="text-muted-foreground">-</span>;
          }
          return (
            <div className="flex min-w-0 flex-wrap gap-1">
              {floor > 0 && (
                <Badge variant="destructive" appearance="light" className="text-[11px]">
                  {`${floor} below floor`}
                </Badge>
              )}
              {nonStandard > 0 && (
                <Badge variant="warning" appearance="light" className="text-[11px]">
                  {`${nonStandard} non-standard`}
                </Badge>
              )}
            </div>
          );
        },
        size: 200,
        meta: { headerTitle: 'Alerts' },
      },
      {
        id: 'series_name',
        accessorFn: (row) => row.quotation.series_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Series" column={column} />,
        cell: ({ row }) =>
          row.original.quotation.series_name ? (
            <span className="truncate text-sm" title={row.original.quotation.series_name}>
              {row.original.quotation.series_name}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 140,
        meta: { headerTitle: 'Series' },
      },
      {
        id: 'loss_reason_label',
        accessorFn: (row) => row.quotation.loss_reason_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Lost because" column={column} />,
        cell: ({ row }) =>
          row.original.quotation.loss_reason_label ? (
            <span
              className="truncate text-sm"
              title={row.original.quotation.loss_reason_label}
            >
              {row.original.quotation.loss_reason_label}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 160,
        meta: { headerTitle: 'Lost because' },
      },
      ...(project.can_edit
        ? [
            {
              id: 'actions',
              header: () => <span className="sr-only">Actions</span>,
              cell: ({ row }: { row: { original: RevisionRow } }) => (
                <div
                  className="flex flex-wrap items-center justify-end gap-1.5"
                  onClick={(event) => event.stopPropagation()}
                >
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setDeciding(row.original.quotation)}
                  >
                    {row.original.quotation.outcome === 'open'
                      ? 'Record outcome'
                      : 'Change outcome'}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(row.original.quotation)}
                  >
                    Edit
                  </Button>
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleting(row.original.quotation)}
                    aria-label={`Delete ${row.original.quotation.scope_label}`}
                  >
                    <Trash2 className="size-3.5 text-destructive" />
                  </Button>
                </div>
              ),
              size: 250,
              enableResizing: false,
              meta: { headerTitle: 'Actions' },
            } as ColumnDef<RevisionRow>,
          ]
        : []),
    ],
    [project.can_edit],
  );


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
                Add a quotation
              </Button>
            )}
          </>
        }
        columns={columns}
        rows={revisionRows}
        getRowId={(row) => row.version.id}
        // Suffixed `-revisions` on purpose: the column SET changed when the list went from
        // one row per scope to one row per revision, and a saved per-user order for the old
        // set appends the new columns to the end, which reads as scrambled.
        listingKey="projects.projects.view::project-quotation-revisions"
        isLoading={quotations.isLoading || revisions.isLoading}
        error={
          quotations.isError
            ? quotations.error
            : revisions.isError
              ? revisions.error
              : undefined
        }
        emptyTitle="Nothing priced yet"
        searchPlaceholder="Search revisions"
        searchOf={(row) =>
          [
            row.quotation.scope_label,
            `v${row.version.version_no}`,
            row.quotation.series_name,
            row.version.issued_by_name,
            row.quotation.loss_reason_label,
          ]
            .filter(Boolean)
            .join(' ')
        }
        pageSize={15}
        // The row is the way in, and it goes to the scope's own page: a list answers "what
        // do we have", a form answers "what is in this one", and stacking them cramps both.
        onRowClick={(row) =>
          router.push(`/project-sales/${project.id}/quotations/${row.quotation.id}`)
        }
      />


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
