'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Search, X, RefreshCw, ChevronRight, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
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

  const { data, isLoading } = useQuery({
    queryKey: ['respond-contacts', pagination, sorting, searchQuery],
    queryFn: fetchContacts,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const syncContactMutation = useMutation({
    mutationFn: async (contactId: string) => {
      const response = await apiFetch(`/api/user-management/contacts/${contactId}/sync`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to sync contact');
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

  const handleSync = (contactId: string) => {
    syncContactMutation.mutate(contactId);
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
      {
        accessorKey: 'phone_number',
        header: ({ column }) => <DataGridColumnHeader title="Phone Number" column={column} />,
        size: 200,
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
              disabled={syncContactMutation.isPending}
            >
              <RefreshCw className={`size-4 ${syncContactMutation.isPending ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 250,
        cell: ({ row }) => row.original.name || <span className="text-muted-foreground">Not set</span>,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'user_type',
        header: ({ column }) => <DataGridColumnHeader title="User Type" column={column} />,
        size: 150,
        cell: ({ row }) => row.original.user_type || <span className="text-muted-foreground">—</span>,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.created_at)),
        size: 150,
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated At" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.updated_at)),
        size: 150,
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
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
    [syncContactMutation.isPending],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    meta: {
      onRowClick: handleRowClick,
    },
  });

  return (
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}>
      <Card>
        <CardHeader className="flex-row items-center justify-between">
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
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="size-4 mr-2" />
            Create Contact
          </Button>
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
    </DataGrid>
  );
}
