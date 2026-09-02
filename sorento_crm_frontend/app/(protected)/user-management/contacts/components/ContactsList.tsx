'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { extractApiError } from '@/lib/api-client';

import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Copy, MessageCircle, MessageCircleOff, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
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
import ContactOutboundCell from '@/components/contacts/ContactOutboundCell';
import ContactOutboundDisableDialog from '@/components/contacts/ContactOutboundDisableDialog';
import ContactOutboundSummary from '@/components/contacts/ContactOutboundSummary';
import { useRespondContactOutboundMutations } from '@/hooks/useRespondContactOutbound';


import { buildDetailSearch } from '@/lib/listNavQuery';
import { contactsListQueryKey, fetchContactsPage } from '../lib/listQuery';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { contactActions } from '../actions';
import { ContactImpersonateDialog } from './ContactImpersonateDialog';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export default function ContactsList() {
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();

  // Back hands the list its own query string back, and the pager keeps
  // rewriting it, so the list reads it (S3-01). One hook, every list.
  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearch(state.searchQuery);
  });

  // A search brings the reader back to page 0 to see the matches; the mounted
  // guard keeps the URL-restored page from being clobbered on first render.
  const searchMounted = useRef(false);
  useEffect(() => {
    if (!searchMounted.current) {
      searchMounted.current = true;
      return;
    }
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [searchQuery]);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [contactToDelete, setContactToDelete] = useState<RespondContact | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkCopyDialogOpen, setBulkCopyDialogOpen] = useState(false);
  const [impersonateTarget, setImpersonateTarget] = useState<RespondContact | null>(null);
  const [bulkDisableOutboundOpen, setBulkDisableOutboundOpen] = useState(false);

  // The list query, built through the shared key + fetch so the detail shell's
  // pager reads THIS cache entry instead of its own 100 newest contacts.
  const listParams = useMemo(
    () => ({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      filters: {},
    }),
    [pagination, sorting, searchQuery],
  );

  const { data, isLoading, isPlaceholderData, refetch, isFetching } = useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: contactsListQueryKey(listParams),
    queryFn: () => fetchContactsPage(listParams),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });

  const pageContacts = useMemo(() => data?.data ?? [], [data]);
  const selectedContactIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);
  const selectedContacts = useMemo(
    () => pageContacts.filter((c) => rowSelection[c.id]),
    [pageContacts, rowSelection],
  );

  // One row here is one contact, so the outbound switch is 1:1 with the row and
  // the selection needs no de-duplication (unlike the contact x agent grants grid).
  const { setOne: setOutboundOne, setBulk: setOutboundBulk } =
    useRespondContactOutboundMutations();
  // Only the BULK write blocks the switches. The per-row one is optimistic
  // (S7-01), so it has already moved the switch and can be flipped straight back.
  const outboundBusy = setOutboundBulk.isPending;
  const outboundCounts = useMemo(() => {
    let reachable = 0;
    let silenced = 0;
    for (const contact of pageContacts) {
      if (contact.outbound_enabled === false) silenced += 1;
      else if (contact.outbound_enabled === true) reachable += 1;
    }
    return { reachable, silenced };
  }, [pageContacts]);

  function contactSyncErrorMessage(response: Response): Promise<string> {
    return extractApiError(response, `Sync failed (${response.status})`);
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

  // The whole row opens the record, carrying the list query the pager rebuilds
  // its key from.
  const rowHref = (contact: RespondContact) => {
    const search = buildDetailSearch(listParams);
    return `/user-management/contacts/${contact.id}${search ? `?${search}` : ''}`;
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
          row.original.first_name || <span className="text-muted-foreground"> - </span>,
        meta: { headerTitle: 'First name', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'last_name',
        header: ({ column }) => <DataGridColumnHeader title="Last name" column={column} />,
        size: 160,
        cell: ({ row }) =>
          row.original.last_name || <span className="text-muted-foreground"> - </span>,
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
            return <span className="text-muted-foreground"> - </span>;
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
        accessorKey: 'outbound_enabled',
        header: ({ column }) => <DataGridColumnHeader title="Outbound" column={column} />,
        enableSorting: false,
        cell: ({ row }) => (
          <ContactOutboundCell
            enabled={row.original.outbound_enabled}
            contactLabel={row.original.name || row.original.phone_number}
            disabled={outboundBusy}
            onChange={(enabled) =>
              setOutboundOne.mutate({ contactId: row.original.id, enabled })
            }
          />
        ),
        size: 210,
        meta: { headerTitle: 'Outbound', skeleton: <Skeleton className="h-5 w-28" /> },
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
          <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            <PortalLinkButton
              contactId={row.original.id}
              contactLabel={row.original.name ?? row.original.phone_number ?? row.original.id}
              canSendViaRespondIo={!!row.original.respond_io_id}
              variant="icon"
            />
            {/* The record's own set, in the row's "..." (D15). */}
            <RowActionsMenu
              ariaLabel="contact"
              actions={contactActions(row.original, {
                impersonate: () => setImpersonateTarget(row.original),
                remove: () => {
                  setContactToDelete(row.original);
                  setDeleteDialogOpen(true);
                },
              })}
            />
          </div>
        ),
        size: 90,
      },
    ],
    [
      syncContactMutation.isPending,
      syncContactMutation.variables,
      bulkSyncMutation.isPending,
      outboundBusy,
      setOutboundOne,
    ],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination?.total || 0) / pagination.pageSize),
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
  });

  const clearSelection = () => setRowSelection({});

  const runOutboundBulk = (enabled: boolean) =>
    setOutboundBulk.mutate(
      { enabled, contactIds: selectedContactIds },
      { onSuccess: clearSelection },
    );

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button onClick={() => setCreateDialogOpen(true)}>
      <Plus className="size-4 mr-2" />
      Create Contact
    </Button>
  );

  return (
    <DataGrid
      table={table}
      tableLayout={{ columnsVisibility: true }}
      recordCount={data?.pagination?.total || 0}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      rowHref={rowHref}
      emptyAction={listPrimaryAction}
    >
      <Card>
        <CardHeader className="block">
          <ContactOutboundSummary
            reachable={outboundCounts.reachable}
            silenced={outboundCounts.silenced}
          />
        </CardHeader>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={searchInput}
                onChange={setSearchInput}
                isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                placeholder="Search contacts..."
                className="w-64"
              />
            }
            exportConfig={{ filename: 'contacts_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={listPrimaryAction}
            bulkActions={[
              {
                key: 'outbound-enable',
                label: `Enable messaging (${selectedContactIds.length})`,
                icon: MessageCircle,
                disabled: outboundBusy,
                onClick: () => runOutboundBulk(true),
              },
              {
                key: 'outbound-disable',
                label: `Disable messaging (${selectedContactIds.length})`,
                icon: MessageCircleOff,
                destructive: true,
                disabled: outboundBusy,
                onClick: () => setBulkDisableOutboundOpen(true),
              },
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
          <DataGridTable />
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

      <ContactOutboundDisableDialog
        open={bulkDisableOutboundOpen}
        onOpenChange={setBulkDisableOutboundOpen}
        contactCount={selectedContactIds.length}
        busy={outboundBusy}
        onConfirm={() => {
          setBulkDisableOutboundOpen(false);
          runOutboundBulk(false);
        }}
      />

      <BulkCopySettingsFromContactDialog
        open={bulkCopyDialogOpen}
        onOpenChange={setBulkCopyDialogOpen}
        targetContacts={selectedContacts}
        onSuccess={clearSelection}
      />

      <ContactImpersonateDialog
        contact={impersonateTarget}
        onClose={() => setImpersonateTarget(null)}
      />
    </DataGrid>
  );
}
