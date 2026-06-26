'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { ChevronRight, Copy, LoaderCircleIcon, Plus, RefreshCw, Search, Trash2, UserCog, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import type { RespondContact } from '../types/contact.types';
import { formatDate } from '@/lib/helpers';
import { toast } from 'sonner';
import ContactCreateDialog from './ContactCreateDialog';
import ContactDeleteDialog from './ContactDeleteDialog';
import ContactBulkDeleteDialog from './ContactBulkDeleteDialog';
import BulkCopySettingsFromContactDialog from './BulkCopySettingsFromContactDialog';
import PortalLinkButton from '@/components/contacts/PortalLinkButton';
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
import { startContactImpersonation } from '@/services/contactImpersonationService';

interface ContactsListProps {
  pageIndex?: number;
  pageSize?: number;
  sorting?: SortingState;
  searchQuery?: string;
}

export default function ContactsList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [contactToDelete, setContactToDelete] = useState<RespondContact | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkCopyDialogOpen, setBulkCopyDialogOpen] = useState(false);
  const [impersonateTarget, setImpersonateTarget] = useState<RespondContact | null>(null);
  const [impersonateStarting, setImpersonateStarting] = useState(false);

  const fetchContacts = async (): Promise<DataGridApiResponse<RespondContact>> => {
    const sortField = sorting?.[0]?.id || 'created_at';
    const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
    const params = new URLSearchParams({
      page: String(pagination.pageIndex + 1),
      limit: String(pagination.pageSize),
      sort: sortField,
      dir: sortDirection,
      ...(searchQuery ? { query: searchQuery } : {}),
    });
    const response = await apiFetch(`/api/user-management/contacts?${params.toString()}`);
    if (!response.ok) throw new Error('Failed to fetch contacts');
    return response.json();
  };

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['respond-contacts', pagination, sorting, searchQuery],
    queryFn: fetchContacts,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const pageContacts = data?.data ?? [];
  const selectedContactIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);
  const selectedContacts = useMemo(
    () => pageContacts.filter((c) => rowSelection[c.id]),
    [pageContacts, rowSelection],
  );

  async function contactSyncErrorMessage(response: Response): Promise<string> {
    const err = await response.json().catch(() => ({} as Record<string, unknown>));
    const d = err.detail as Record<string, unknown> | string | undefined;
    if (d && typeof d === 'object' && d.message != null) return String(d.message);
    if (typeof d === 'string') return d;
    if (err.message != null) return String(err.message);
    return `Sync failed (${response.status})`;
  }

  const syncContactMutation = useMutation({
    mutationFn: async (contactId: string) => {
      const response = await apiFetch(`/api/user-management/contacts/${contactId}/sync`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error(await contactSyncErrorMessage(response));
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      toast.success('Contact synced successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to sync contact');
    },
  });

  const bulkSyncMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      const response = await apiFetch('/api/user-management/contacts/bulk-sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      if (!response.ok) throw new Error(await contactSyncErrorMessage(response));
      return response.json() as Promise<{ succeeded: number; failed: number; errors: { id: string; message: string }[] }>;
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      if (result.failed > 0) {
        toast.warning(`Synced ${result.succeeded}, ${result.failed} failed`);
      } else {
        toast.success(`Synced ${result.succeeded} contact(s) from Respond.io`);
      }
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Bulk sync failed');
    },
  });

  const handleSync = (contactId: string) => {
    syncContactMutation.mutate(contactId);
  };

  const handleBulkSync = () => {
    if (selectedContactIds.length === 0) return;
    bulkSyncMutation.mutate(selectedContactIds);
  };

  const handleRowClick = (contact: RespondContact) => {
    router.push(`/user-management/contacts/${contact.id}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, contact: RespondContact) => {
    e.stopPropagation();
    setContactToDelete(contact);
    setDeleteDialogOpen(true);
  };

  const columns = useMemo<ColumnDef<RespondContact>[]>(
    () => [
      buildSelectColumn<RespondContact>(),
      {
        accessorKey: 'phone_number',
        header: ({ column }) => <DataGridColumnHeader title="Phone Number" column={column} />,
        size: 200,
        meta: { headerTitle: 'Phone Number', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <span className="font-medium font-mono">{row.original.phone_number}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                handleSync(row.original.id);
              }}
              disabled={bulkSyncMutation.isPending || syncContactMutation.isPending}
              title="Sync from Respond.io"
            >
              <RefreshCw
                className={`size-4 ${
                  syncContactMutation.isPending && syncContactMutation.variables === row.original.id
                    ? 'animate-spin'
                    : ''
                }`}
              />
            </Button>
          </div>
        ),
      },
      {
        accessorKey: 'first_name',
        header: ({ column }) => <DataGridColumnHeader title="First name" column={column} />,
        size: 160,
        cell: ({ row }) =>
          row.original.first_name || <span className="text-muted-foreground">—</span>,
        meta: { headerTitle: 'First name', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'last_name',
        header: ({ column }) => <DataGridColumnHeader title="Last name" column={column} />,
        size: 160,
        cell: ({ row }) =>
          row.original.last_name || <span className="text-muted-foreground">—</span>,
        meta: { headerTitle: 'Last name', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'access_types',
        accessorFn: (row) => row.access_type_codes?.join(',') ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Access types" column={column} />,
        size: 220,
        enableSorting: false,
        cell: ({ row }) => {
          const types = row.original.access_types ?? [];
          if (types.length === 0) {
            return <span className="text-muted-foreground">—</span>;
          }
          return (
            <div className="flex flex-wrap gap-1">
              {types.map((t) => (
                <Badge key={t.code} variant="secondary" className="font-normal">
                  {t.name}
                </Badge>
              ))}
            </div>
          );
        },
        meta: { headerTitle: 'Access types', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.created_at)),
        size: 150,
        meta: { headerTitle: 'Created At' },
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated At" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.updated_at)),
        size: 150,
        meta: { headerTitle: 'Updated At' },
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        cell: ({ row }) => (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <PortalLinkButton
              contactId={row.original.id}
              contactLabel={row.original.name ?? row.original.phone_number ?? row.original.id}
              canSendViaRespondIo={!!row.original.respond_io_id}
              variant="icon"
            />
            <Button
              variant="ghost"
              size="sm"
              title="Impersonate in portal"
              onClick={(e) => {
                e.stopPropagation();
                setImpersonateTarget(row.original);
              }}
            >
              <UserCog className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              title="Delete contact"
              onClick={(e) => handleDeleteClick(e, row.original)}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                handleRowClick(row.original);
              }}
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        ),
        size: 90,
      },
    ],
    [syncContactMutation.isPending, syncContactMutation.variables, bulkSyncMutation.isPending],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    enableRowSelection: true,
    meta: {
      onRowClick: handleRowClick,
    },
  });

  const clearSelection = () => setRowSelection({});

  return (
    <DataGrid
      table={table}
      tableLayout={{ columnsVisibility: true }}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search contacts..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            exportConfig={{ filename: 'contacts_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button onClick={() => setCreateDialogOpen(true)}>
                <Plus className="size-4 mr-2" />
                Create Contact
              </Button>
            }
            bulkActions={[
              {
                key: 'sync',
                label: `Sync from Respond (${selectedContactIds.length})`,
                icon: RefreshCw,
                disabled: bulkSyncMutation.isPending || syncContactMutation.isPending,
                onClick: handleBulkSync,
              },
              {
                key: 'copy-settings',
                label: `Copy settings to ${selectedContactIds.length} user${selectedContactIds.length !== 1 ? 's' : ''}`,
                icon: Copy,
                onClick: () => setBulkCopyDialogOpen(true),
              },
              {
                key: 'delete',
                label: `Delete (${selectedContactIds.length})`,
                icon: Trash2,
                destructive: true,
                onClick: () => setBulkDeleteDialogOpen(true),
              },
            ]}
          />
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <ContactCreateDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />

      <ContactDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        contact={contactToDelete}
      />

      <ContactBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        contactIds={selectedContactIds}
        onSuccess={clearSelection}
      />

      <BulkCopySettingsFromContactDialog
        open={bulkCopyDialogOpen}
        onOpenChange={setBulkCopyDialogOpen}
        targetContacts={selectedContacts}
        onSuccess={clearSelection}
      />

      <AlertDialog
        open={!!impersonateTarget}
        onOpenChange={(open) => {
          if (!open && !impersonateStarting) setImpersonateTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Impersonation</AlertDialogTitle>
            <AlertDialogDescription>
              You will browse the portal as{' '}
              <strong>
                {impersonateTarget?.name ||
                  impersonateTarget?.phone_number ||
                  impersonateTarget?.id ||
                  ''}
              </strong>{' '}
              with their access rights. All records you create or modify will
              still be attributed to you. Continue?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={impersonateStarting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={impersonateStarting}
              onClick={async (e) => {
                e.preventDefault();
                if (!impersonateTarget) return;
                setImpersonateStarting(true);
                try {
                  const session = await startContactImpersonation(impersonateTarget.id);
                  toast.success(
                    `Now impersonating ${
                      impersonateTarget.name || impersonateTarget.phone_number || impersonateTarget.id
                    }`,
                  );
                  setImpersonateTarget(null);
                  if (typeof window !== 'undefined') {
                    window.open(session.portalUrl, '_blank', 'noopener,noreferrer');
                  }
                } catch (err) {
                  toast.error(
                    err instanceof Error ? err.message : 'Failed to start impersonation',
                  );
                } finally {
                  setImpersonateStarting(false);
                }
              }}
            >
              {impersonateStarting ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Starting...
                </>
              ) : (
                'Impersonate'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DataGrid>
  );
}
