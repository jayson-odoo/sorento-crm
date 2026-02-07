'use client';

import { useState, useMemo } from 'react';
import {
  ColumnDef,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Plus, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CardContent } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useSLAPolicyTiers, useDeleteSLAPolicyTier } from '../hooks/useSLAPolicies';
import SLAPolicyTierDialog from './SLAPolicyTierDialog';
import SLAPolicyTierDeleteDialog from './sla-policy-tier-delete-dialog';
import type { SLAPolicyTier } from '../types/slaPolicy.types';

interface SLAPolicyTiersTableProps {
  policyId: string;
}

export default function SLAPolicyTiersTable({ policyId }: SLAPolicyTiersTableProps) {
  const { data: tiers, isLoading, error } = useSLAPolicyTiers(policyId);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTier, setEditingTier] = useState<SLAPolicyTier | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [tierToDelete, setTierToDelete] = useState<SLAPolicyTier | null>(null);

  const handleAdd = () => {
    setEditingTier(null);
    setDialogOpen(true);
  };

  const handleEdit = (tier: SLAPolicyTier) => {
    setEditingTier(tier);
    setDialogOpen(true);
  };

  const handleDelete = (tier: SLAPolicyTier) => {
    setTierToDelete(tier);
    setDeleteDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setEditingTier(null);
  };

  const columns = useMemo<ColumnDef<SLAPolicyTier>[]>(
    () => [
      {
        accessorKey: 'tier_level',
        header: ({ column }) => <DataGridColumnHeader title="Tier Level" column={column} />,
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'tier_name',
        header: ({ column }) => <DataGridColumnHeader title="Tier Name" column={column} />,
        size: 250,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'response_hours',
        header: ({ column }) => <DataGridColumnHeader title="Response Hours" column={column} />,
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'resolution_hours',
        header: ({ column }) => <DataGridColumnHeader title="Resolution Hours" column={column} />,
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                handleEdit(row.original);
              }}
            >
              <Edit className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(row.original);
              }}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
        size: 100,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: tiers || [],
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <>
      <div className="flex items-center gap-2 mb-4">
        <Button onClick={handleAdd} size="sm">
          <Plus className="size-4" />
          Add Tier
        </Button>
      </div>

      <CardContent>
        {isLoading ? (
          <div className="text-center py-8 text-muted-foreground">Loading tiers...</div>
        ) : error ? (
          <div className="text-center py-8">
            <p className="text-destructive">Failed to load tiers</p>
            <p className="text-sm text-muted-foreground mt-2">
              {error instanceof Error ? error.message : 'An error occurred'}
            </p>
          </div>
        ) : (
          <DataGrid table={table} recordCount={tiers?.length || 0} isLoading={isLoading}>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </DataGrid>
        )}
      </CardContent>

      {/* Add/Edit Dialog */}
      <SLAPolicyTierDialog
        open={dialogOpen}
        onOpenChange={handleDialogClose}
        policyId={policyId}
        tier={editingTier}
      />

      {/* Delete Dialog */}
      {tierToDelete && (
        <SLAPolicyTierDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => {
            setDeleteDialogOpen(false);
            setTierToDelete(null);
          }}
          policyId={policyId}
          tier={tierToDelete}
        />
      )}
    </>
  );
}
