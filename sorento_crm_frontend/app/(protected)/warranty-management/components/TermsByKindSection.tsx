'use client';

import { useMemo, useState } from 'react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardTitle, CardToolbar } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  useCreateTerm,
  useDeleteTerm,
  useKindOptions,
  useTermsGroupedByKind,
  useUpdateTerm,
} from '../hooks/useWarrantyConfig';
import { formatCoverage, formatDefectScope } from '../lib/warrantyLabels';
import type { WarrantyTermRow, WarrantyTermWrite } from '../types/warranty-config.types';
import { TermFormDialog } from './TermFormDialog';

/**
 * AC-P4 - every Term under a Kind, together.
 *
 * A Water Closet carries three simultaneously and they disagree on all four
 * dimensions: the ceramic body is lifetime, covers cracking and leaking only and
 * includes installation; the flushing fittings and the seat cover run out on
 * different dates and exclude it. So the four dimensions are four columns, and
 * the rows are grouped by Kind through the grid's own group divider rather than
 * split across one card per Kind - a screen that shows one Term at a time cannot
 * be checked against the policy document.
 */
export function TermsByKindSection({ policyId }: { policyId: string }) {
  const { data, isLoading, isError, error } = useTermsGroupedByKind(policyId);
  const { data: kindOptions } = useKindOptions();
  const createTerm = useCreateTerm(policyId);
  const updateTerm = useUpdateTerm(policyId);
  const deleteTerm = useDeleteTerm(policyId);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<WarrantyTermRow | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WarrantyTermRow | null>(null);

  const kinds = useMemo(() => kindOptions ?? [], [kindOptions]);

  // Groups arrive contiguous from the API; flattening keeps them that way, which
  // is what the grid's group divider requires.
  const rows = useMemo<WarrantyTermRow[]>(
    () => (data?.groups ?? []).flatMap((g) => g.terms),
    [data],
  );

  const submit = async (body: WarrantyTermWrite) => {
    setFormError(null);
    try {
      if (editing) {
        await updateTerm.mutateAsync({ termId: editing.id, body });
      } else {
        await createTerm.mutateAsync(body);
      }
      setFormOpen(false);
      setEditing(null);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const columns = useMemo<ColumnDef<WarrantyTermRow>[]>(
    () => [
      {
        id: 'part_name',
        accessorFn: (row) => row.part_name,
        header: ({ column }) => <DataGridColumnHeader title="Part" column={column} />,
        size: 220,
        meta: { headerTitle: 'Part' },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.part_name}>
            {row.original.part_name}
          </span>
        ),
      },
      {
        id: 'coverage',
        accessorFn: (row) => (row.is_lifetime ? -1 : (row.duration_months ?? 0)),
        header: ({ column }) => <DataGridColumnHeader title="Cover" column={column} />,
        size: 210,
        meta: { headerTitle: 'Cover' },
        cell: ({ row }) =>
          row.original.is_lifetime ? (
            <Badge variant="success" appearance="light" size="md">
              Lifetime
            </Badge>
          ) : (
            <span className="block truncate" title={formatCoverage(row.original)}>
              {formatCoverage(row.original)}
            </span>
          ),
      },
      {
        id: 'defect_scope',
        accessorFn: (row) => formatDefectScope(row),
        header: ({ column }) => <DataGridColumnHeader title="Defect scope" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Defect scope' },
        cell: ({ row }) => (
          <span className="block truncate" title={formatDefectScope(row.original)}>
            {formatDefectScope(row.original)}
          </span>
        ),
      },
      {
        id: 'installation_included',
        accessorFn: (row) => row.installation_included,
        header: ({ column }) => <DataGridColumnHeader title="Installation" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Installation' },
        cell: ({ row }) =>
          row.original.installation_included ? (
            <Badge variant="success" appearance="light" size="md">
              Included
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="light" size="md">
              Excluded
            </Badge>
          ),
      },
      {
        id: 'qualifications',
        accessorFn: (row) => row.qualifications,
        header: ({ column }) => <DataGridColumnHeader title="Qualifications" column={column} />,
        size: 320,
        enableSorting: false,
        meta: { headerTitle: 'Qualifications' },
        cell: ({ row }) =>
          row.original.qualifications ? (
            <span className="block truncate" title={row.original.qualifications}>
              {row.original.qualifications}
            </span>
          ) : (
            <span className="text-muted-foreground">None</span>
          ),
      },
      {
        id: 'exclusions',
        accessorFn: (row) => row.exclusions,
        header: ({ column }) => <DataGridColumnHeader title="Exclusions" column={column} />,
        size: 320,
        enableSorting: false,
        meta: { headerTitle: 'Exclusions' },
        cell: ({ row }) =>
          row.original.exclusions ? (
            <span className="block truncate" title={row.original.exclusions}>
              {row.original.exclusions}
            </span>
          ) : (
            <span className="text-muted-foreground">None</span>
          ),
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 100,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Edit"
              aria-label="Edit term"
              onClick={() => {
                setFormError(null);
                setEditing(row.original);
                setFormOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Delete"
              aria-label="Delete term"
              onClick={() => setDeleteTarget(row.original)}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <>
      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load terms.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        listingKey="warranty.policies.view::terms"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={
          isError
            ? 'Terms could not be loaded.'
            : 'No terms under this policy yet. Add one to say what it covers.'
        }
        renderGroupHeader={(row: WarrantyTermRow, previous: WarrantyTermRow | null) =>
          previous && previous.kind_id === row.kind_id ? null : row.kind_name
        }
      >
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Terms by kind</CardTitle>
            </CardHeading>
            <CardToolbar>
              <Button
                onClick={() => {
                  setFormError(null);
                  setEditing(null);
                  setFormOpen(true);
                }}
              >
                <Plus className="size-4" /> Add term
              </Button>
            </CardToolbar>
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      </DataGrid>

      <TermFormDialog
        open={formOpen}
        onOpenChange={(o) => {
          setFormOpen(o);
          if (!o) {
            setEditing(null);
            setFormError(null);
          }
        }}
        initial={editing}
        kinds={kinds}
        onSubmit={submit}
        isSubmitting={createTerm.isPending || updateTerm.isPending}
        error={formError}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Confirm delete"
        description={
          <>
            This action cannot be undone. The <strong>{deleteTarget?.part_name}</strong> term for{' '}
            <strong>{deleteTarget?.kind_name}</strong> will be permanently removed.{' '}
            {deleteTarget && deleteTarget.assessment_count > 0 ? (
              <>
                <strong>{deleteTarget.assessment_count}</strong> assessment
                {deleteTarget.assessment_count === 1 ? '' : 's'} quoted it and will be kept.
              </>
            ) : (
              <>No assessment quotes it.</>
            )}
          </>
        }
        successMessage="Term deleted"
        onDelete={async () => {
          if (deleteTarget) await deleteTerm.mutateAsync(deleteTarget.id);
        }}
        onSuccess={() => setDeleteTarget(null)}
      />
    </>
  );
}
