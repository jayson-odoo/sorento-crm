'use client';

import { useState, useMemo } from 'react';
import {
  ColumnDef,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Plus, Edit, Trash2, Users } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { CardContent } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useSLAPolicyTiers } from '../hooks/useSLAPolicies';
import SLAPolicyTierDialog from './SLAPolicyTierDialog';
import SLAPolicyTierDeleteDialog from './sla-policy-tier-delete-dialog';
import type { SLAPolicyTier } from '../types/slaPolicy.types';

interface SLAPolicyTiersTableProps {
  policyId: string;
}

/** Hours come from the backend as a Decimal string ("0.50"); show trimmed (0.5, 24). */
function formatHours(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(v);
  return Number.isFinite(n) ? String(n) : String(v);
}

/** Group users by tier for display in the tiers table */
function useUsersByTier(tierLevels: number[]) {
  const tierParam = tierLevels.length ? tierLevels.join(',') : '';
  const { data } = useQuery({
    queryKey: ['users-by-tier', tierParam],
    queryFn: async () => {
      if (!tierParam) return { data: [] };
      const params = new URLSearchParams({ tier: tierParam, limit: '500' });
      const res = await apiFetch(`/api/user-management/users?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch users');
      return res.json() as Promise<{ data: Array<{ id: string; name?: string | null; email: string; tier?: number | null }> }>;
    },
    enabled: tierParam.length > 0,
  });
  return useMemo(() => {
    const byTier: Record<number, Array<{ id: string; name?: string | null; email: string }>> = {};
    for (const level of tierLevels) {
      byTier[level] = [];
    }
    for (const u of data?.data ?? []) {
      const t = u.tier;
      if (t != null && byTier[t] !== undefined) {
        byTier[t].push({ id: u.id, name: u.name ?? null, email: u.email });
      }
    }
    return byTier;
  }, [data?.data, tierLevels]);
}

/** Fetches and lists users for a single tier in the sheet */
function TierUsersSheetContent({ tierLevel }: { tierLevel: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['users-by-tier-single', tierLevel],
    queryFn: async () => {
      const params = new URLSearchParams({ tier: String(tierLevel), limit: '500' });
      const res = await apiFetch(`/api/user-management/users?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch users');
      return res.json() as Promise<{ data: Array<{ id: string; name?: string | null; email: string }> }>;
    },
    enabled: true,
  });
  const users = data?.data ?? [];

  return (
    <div className="flex-1 overflow-auto py-4">
      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading users...</div>
      ) : error ? (
        <div className="text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load users'}
        </div>
      ) : users.length === 0 ? (
        <p className="text-sm text-muted-foreground">No users assigned to this tier.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.name?.trim() || '-'}</TableCell>
                <TableCell className="text-muted-foreground">{u.email}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

export default function SLAPolicyTiersTable({ policyId }: SLAPolicyTiersTableProps) {
  const { data: tiers, isLoading, error } = useSLAPolicyTiers(policyId);
  const tierLevels = useMemo(() => (tiers ?? []).map((t) => t.tier_level), [tiers]);
  const usersByTier = useUsersByTier(tierLevels);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTier, setEditingTier] = useState<SLAPolicyTier | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [tierToDelete, setTierToDelete] = useState<SLAPolicyTier | null>(null);
  const [usersSheetTier, setUsersSheetTier] = useState<{ level: number; name: string } | null>(null);

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
        cell: ({ row }) => formatHours(row.original.response_hours),
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'resolution_hours',
        header: ({ column }) => <DataGridColumnHeader title="Resolution Hours" column={column} />,
        cell: ({ row }) => formatHours(row.original.resolution_hours),
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'users',
        header: ({ column }) => <DataGridColumnHeader title="Users" column={column} />,
        size: 280,
        cell: ({ row }) => {
          const level = row.original.tier_level;
          const tierName = row.original.tier_name ?? `Tier ${level}`;
          const users = usersByTier[level] ?? [];
          const count = users.length;
          return (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 font-normal"
              onClick={(e) => {
                e.stopPropagation();
                setUsersSheetTier({ level, name: tierName });
              }}
            >
              <Users className="size-4 text-muted-foreground" />
              Users
              {count > 0 && (
                <span className="text-muted-foreground">({count})</span>
              )}
            </Button>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
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
    [usersByTier],
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
            <DataGridTable />
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

      {/* Users in tier sheet */}
      <Sheet open={!!usersSheetTier} onOpenChange={(open) => !open && setUsersSheetTier(null)}>
        <SheetContent className="flex flex-col sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>
              {usersSheetTier ? `Users in Tier ${usersSheetTier.level} - ${usersSheetTier.name}` : 'Users'}
            </SheetTitle>
          </SheetHeader>
          {usersSheetTier && (
            <TierUsersSheetContent tierLevel={usersSheetTier.level} />
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
