'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { History, Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { useSampleMutations, useSamples } from '../../_shared/hooks/useProjects';
import type { Project, ProjectSample } from '../../_shared/types/project.types';
import { SampleDialog } from './SampleDialog';

/**
 * Samples sent to the developer, each against the version it was priced from (AC-F1).
 *
 * The version is shown on every row, not tucked away: a sample approved against v1 when
 * the customer now holds v3 is the single most expensive thing to discover late, and
 * "superseded" is stated rather than implied by a missing badge.
 */
export function SamplesPanel({ project }: { project: Project }) {
  const samples = useSamples(project.id);
  const { remove } = useSampleMutations(project.id);

  const [creating, setCreating] = React.useState(false);
  const [editing, setEditing] = React.useState<ProjectSample | null>(null);
  const [deleting, setDeleting] = React.useState<ProjectSample | null>(null);

  const rows = React.useMemo(() => samples.data ?? [], [samples.data]);
  const supersededCount = rows.filter((row) => !row.is_version_current).length;

  const columns = React.useMemo<ColumnDef<ProjectSample>[]>(
    () => [
      {
        id: 'scope',
        accessorFn: (row) => row.scope_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Scope" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm font-medium" title={row.original.scope_label ?? ''}>
            {row.original.scope_label ?? '-'}
          </span>
        ),
        size: 200,
        meta: { headerTitle: 'Scope' },
      },
      {
        id: 'version',
        accessorFn: (row) => row.version_no ?? 0,
        // Stated on every row, never implied by a missing badge: a sample approved against
        // v1 while the customer holds v3 is the most expensive thing to find out late.
        header: ({ column }) => <DataGridColumnHeader title="Priced from" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="text-sm">
              {row.original.version_no ? `v${row.original.version_no}` : '-'}
            </span>
            <Badge
              variant={row.original.is_version_current ? 'secondary' : 'warning'}
              appearance="light"
              className="shrink-0 text-[11px]"
            >
              {row.original.is_version_current ? 'Current' : 'Superseded'}
            </Badge>
          </div>
        ),
        size: 170,
        meta: { headerTitle: 'Priced from' },
      },
      {
        id: 'submitted_on',
        accessorFn: (row) => row.submitted_on ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Sent" column={column} />,
        cell: ({ row }) =>
          row.original.submitted_on ? (
            <span className="truncate text-sm">
              {formatDateInMalaysia(row.original.submitted_on)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 130,
        meta: { headerTitle: 'Sent' },
      },
      {
        id: 'submitted_by_name',
        accessorFn: (row) => row.submitted_by_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="By" column={column} />,
        cell: ({ row }) =>
          row.original.submitted_by_name ? (
            <span className="truncate text-sm">{row.original.submitted_by_name}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 160,
        meta: { headerTitle: 'By' },
      },
      {
        id: 'developer_feedback',
        accessorFn: (row) => row.developer_feedback ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Developer said" column={column} />
        ),
        cell: ({ row }) =>
          row.original.developer_feedback ? (
            <span className="truncate text-sm" title={row.original.developer_feedback}>
              {row.original.developer_feedback}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 260,
        meta: { headerTitle: 'Developer said' },
      },
      {
        id: 'salesperson_notes',
        accessorFn: (row) => row.salesperson_notes ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Our notes" column={column} />,
        cell: ({ row }) =>
          row.original.salesperson_notes ? (
            <span className="truncate text-sm" title={row.original.salesperson_notes}>
              {row.original.salesperson_notes}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 220,
        meta: { headerTitle: 'Our notes' },
      },
      ...(project.can_edit
        ? [
            {
              id: 'actions',
              header: () => <span className="sr-only">Actions</span>,
              cell: ({ row }: { row: { original: ProjectSample } }) => (
                <div className="flex justify-end gap-1">
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditing(row.original)}
                    aria-label={`Edit the ${row.original.scope_label ?? 'sample'} submission`}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleting(row.original)}
                    aria-label={`Delete the ${row.original.scope_label ?? 'sample'} submission`}
                  >
                    <Trash2 className="size-3.5 text-destructive" />
                  </Button>
                </div>
              ),
              size: 90,
              enableResizing: false,
              meta: { headerTitle: 'Actions' },
            } as ColumnDef<ProjectSample>,
          ]
        : []),
    ],
    [project.can_edit],
  );

  return (
    <>
      <PanelDataGrid
        title="Sample submissions"
        toolbar={
          <>
            {supersededCount > 0 && (
              <Badge variant="warning" appearance="light" className="gap-1">
                <History className="size-3" aria-hidden />
                {`${supersededCount} against a superseded version`}
              </Badge>
            )}
            {project.can_edit && (
              <Button type="button" size="sm" onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden />
                Record a sample
              </Button>
            )}
          </>
        }
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        listingKey="projects.projects.view::project-samples"
        isLoading={samples.isLoading}
        error={samples.isError ? samples.error : undefined}
        emptyTitle="No samples sent yet"
      />

      {(creating || editing) && (
        <SampleDialog
          project={project}
          sample={editing}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Confirm delete"
        description={
          deleting
            ? `Delete this sample submission and the developer feedback recorded on it? This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
        successMessage="Sample deleted"
      />
    </>
  );
}
