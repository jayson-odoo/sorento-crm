'use client';

import { useMemo, useState } from 'react';
import { redirect } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ColumnDef,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronRight, LoaderCircleIcon, Plus, Search, Settings, Trash2, UserCheck, UserX, X } from 'lucide-react';
import { apiFetch } from '@/lib/api';
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
import { formatDateSafe, formatDateTimeSafe, getInitials } from '@/lib/helpers';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge, BadgeDot, BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable, CardToolbar } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  DataGrid,
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import {
  DataGridTable,
  DataGridTableRowSelect,
  DataGridTableRowSelectAll,
} from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { User, UserStatus } from '@/app/models/user';
import { useRoleSelectQuery } from '../../roles/hooks/use-role-select-query';
import { getUserStatusProps, UserStatusProps } from '../constants/status';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import UserInviteDialog from './user-add-dialog';
import { toast } from 'sonner';

const UserList = () => {
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'createdAt', desc: true },
  ]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string | null>('all');
  const [selectedTrashed, setSelectedTrashed] = useState<string>('exclude');
  const [bulkActionPending, setBulkActionPending] = useState(false);
  const [bulkConfirmOpen, setBulkConfirmOpen] = useState(false);
  const [bulkConfirmAction, setBulkConfirmAction] = useState<'delete' | 'activate' | 'deactivate' | 'permanent_delete' | null>(null);

  // Role select query
  const { data: roleList } = useRoleSelectQuery();

  // Fetch users from the server API
  const fetchUsers = async ({
    pageIndex,
    pageSize,
    sorting,
    searchQuery,
    selectedRole,
    selectedStatus,
    selectedTrashed,
  }: DataGridApiFetchParams & {
    selectedRole: string | null;
    selectedStatus: string | null;
    selectedTrashed: string;
  }): Promise<DataGridApiResponse<User>> => {
    const sortField = sorting?.[0]?.id || '';
    const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';

    const params = new URLSearchParams({
      page: String(pageIndex + 1),
      limit: String(pageSize),
      ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
      ...(searchQuery ? { query: searchQuery } : {}),
      ...(selectedRole && selectedRole !== 'all'
        ? { roleId: selectedRole }
        : {}),
      ...(selectedStatus && selectedStatus !== 'all'
        ? { status: selectedStatus }
        : {}),
      ...(selectedTrashed && selectedTrashed !== 'exclude'
        ? { trashed: selectedTrashed }
        : {}),
    });

    const response = await apiFetch(
      `/api/user-management/users?${params.toString()}`,
    );

    if (!response.ok) {
      throw new Error(
        'Oops! Something didn’t go as planned. Please try again in a moment.',
      );
    }

    const json = await response.json();
    if (json.data?.length) {
      json.data = json.data.map((u: Record<string, unknown>) => ({
        ...u,
        isTrashed: u.is_trashed ?? u.isTrashed,
      }));
    }
    return json;
  };

  // Users query
  const { data, isLoading } = useQuery({
    queryKey: [
      'user-users',
      pagination,
      sorting,
      searchQuery,
      selectedRole,
      selectedStatus,
      selectedTrashed,
    ],
    queryFn: () =>
      fetchUsers({
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
        selectedRole,
        selectedStatus,
        selectedTrashed,
      }),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });

  const handleRoleSelection = (roleId: string) => {
    setSelectedRole(roleId);
    setPagination({ ...pagination, pageIndex: 0 });
  };

  const handleStatusSelection = (status: string) => {
    setSelectedStatus(status);
    setPagination({ ...pagination, pageIndex: 0 });
  };

  const handleTrashedSelection = (trashed: string) => {
    setSelectedTrashed(trashed);
    setPagination({ ...pagination, pageIndex: 0 });
  };

  const handleRowClick = (row: User) => {
    const userId = row.id;
    redirect(`/user-management/users/${userId}`);
  };

  const selectedRowIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);

  const runBulkAction = (action: 'delete' | 'activate' | 'deactivate' | 'permanent_delete') => {
    if (selectedRowIds.length === 0) return;
    setBulkConfirmAction(action);
    setBulkConfirmOpen(true);
  };

  const runBulkActionConfirm = async () => {
    const action = bulkConfirmAction;
    if (!action || selectedRowIds.length === 0) return;
    setBulkActionPending(true);
    try {
      const res = await apiFetch('/api/user-management/users/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_ids: selectedRowIds,
          action: action === 'permanent_delete' ? 'permanent_delete' : action,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.message || 'Bulk action failed');
      toast.success(data.message || 'Done');
      setRowSelection({});
      setBulkConfirmOpen(false);
      setBulkConfirmAction(null);
      queryClient.invalidateQueries({ queryKey: ['user-users'] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Bulk action failed');
    } finally {
      setBulkActionPending(false);
    }
  };

  const bulkConfirmConfig =
    bulkConfirmAction === 'delete'
      ? {
          title: 'Confirm delete',
          description: `Are you sure you want to trash ${selectedRowIds.length} user(s)? They can be restored from the Trashed filter.`,
          actionLabel: 'Trash',
        }
      : bulkConfirmAction === 'permanent_delete'
        ? {
            title: 'Permanently delete users',
            description: `Are you sure you want to permanently delete ${selectedRowIds.length} trashed user(s)? This cannot be undone.`,
            actionLabel: 'Permanently delete',
          }
        : bulkConfirmAction === 'activate'
          ? {
              title: 'Confirm activate',
              description: `Are you sure you want to activate ${selectedRowIds.length} user(s)?`,
              actionLabel: 'Activate',
            }
          : bulkConfirmAction === 'deactivate'
            ? {
                title: 'Confirm deactivate',
                description: `Are you sure you want to deactivate ${selectedRowIds.length} user(s)?`,
                actionLabel: 'Deactivate',
              }
            : { title: '', description: '', actionLabel: '' };

  const columns = useMemo<ColumnDef<User>[]>(
    () => [
      {
        id: 'select',
        header: () => <DataGridTableRowSelectAll />,
        cell: ({ row }) => <DataGridTableRowSelect row={row} />,
        size: 40,
        enableSorting: false,
        meta: { skeleton: <Skeleton className="size-5" /> },
        enableResizing: false,
      },
      {
        accessorKey: 'name',
        id: 'name',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="User"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          const user = row.original;
          const avatarUrl = user.avatar || null;
          const initials = getInitials(user.name || user.email);

          return (
            <div className="flex items-center gap-3">
              <Avatar className="size-8">
                {avatarUrl && (
                  <AvatarImage src={avatarUrl} alt={user.name || ''} />
                )}
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
              <div className="space-y-px">
                <div className="font-medium text-sm">{user.name}</div>
                <div className="text-muted-foreground text-xs">
                  {user.email}
                </div>
              </div>
            </div>
          );
        },
        size: 300,
        meta: {
          headerTitle: 'Name',
          skeleton: (
            <div className="flex items-center gap-3">
              <Skeleton className="size-8 rounded-full" />
              <div className="space-y-1">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-4 w-24" />
              </div>
            </div>
          ),
        },
        enableSorting: true,
        enableHiding: false,
      },
      {
        accessorKey: 'role_name',
        id: 'roles',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Roles"
            visibility={true}
            column={column}
          />
        ),
        size: 180,
        cell: ({ row }) => {
          const roles = row.original.roles ?? [];
          if (!roles.length) return <span className="text-muted-foreground">—</span>;
          return (
            <span className="inline-flex flex-wrap gap-1">
              {roles.map((r: { id: string; name: string }) => (
                <Badge key={r.id} variant="secondary">{r.name}</Badge>
              ))}
            </span>
          );
        },
        meta: {
          headerTitle: 'Roles',
          skeleton: <Skeleton className="w-28 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'status',
        id: 'status',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Status"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          const statusProps = getUserStatusProps(
            row.original.status as UserStatus,
          );
          const isTrashed = row.original.isTrashed;
          const variant = getStatusBadgeVariant(row.original.status);

          return (
            <div className="inline-flex gap-2.5">
              <Badge variant={variant} appearance="ghost">
                <BadgeDot />
                {statusProps.label}
              </Badge>
              {isTrashed && (
                <Badge variant="destructive" appearance="light">
                  Trashed
                </Badge>
              )}
            </div>
          );
        },
        size: 125,
        meta: {
          headerTitle: 'Status',
          skeleton: <Skeleton className="w-14 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'createdAt',
        id: 'createdAt',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Joined"
            visibility={true}
            column={column}
          />
        ),
        cell: (info) => formatDateSafe(info.getValue() as string | null),
        size: 150,
        meta: {
          headerTitle: 'Joined',
          skeleton: <Skeleton className="w-20 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'lastSignInAt',
        id: 'lastSignInAt',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Last Sign In"
            visibility={true}
            column={column}
          />
        ),
        cell: (info) =>
          formatDateTimeSafe(info.getValue() as string | null, 'Never'),
        size: 175,
        meta: {
          headerTitle: 'Last Sign In',
          skeleton: <Skeleton className="w-20 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => (
          <ChevronRight className="text-muted-foreground/70 size-3.5" />
        ),
        meta: {
          skeleton: <Skeleton className="size-4" />,
        },
        size: 40,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    [],
  );

  const [columnOrder, setColumnOrder] = useState<string[]>(() =>
    columns.map((column) => column.id as string),
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row: User) => row.id,
    state: {
      pagination,
      sorting,
      columnOrder,
      rowSelection,
    },
    columnResizeMode: 'onChange',
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onColumnOrderChange: setColumnOrder,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  const DataGridToolbar = () => {
    const [inputValue, setInputValue] = useState(searchQuery);

    const handleSearch = () => {
      setSearchQuery(inputValue);
      setPagination({ ...pagination, pageIndex: 0 });
    };

    return (
      <CardHeader className="flex-col flex-wrap sm:flex-row items-stretch sm:items-center py-5">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search users"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              disabled={isLoading}
              className="ps-9 w-full sm:40 md:w-64"
            />
            {searchQuery.length > 0 && (
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
          <Select
            onValueChange={handleRoleSelection}
            value={selectedRole || 'all'}
            defaultValue="all"
            disabled={isLoading}
          >
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="Filter by role" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All roles</SelectItem>
              {roleList?.map((role: User) => (
                <SelectItem key={role.id} value={role.id}>
                  {role.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            onValueChange={handleStatusSelection}
            value={selectedStatus || 'all'}
            defaultValue="all"
            disabled={isLoading}
          >
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All users</SelectItem>
              {Object.entries(UserStatusProps).map(([status, { label }]) => (
                <SelectItem key={status} value={status}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            onValueChange={handleTrashedSelection}
            value={selectedTrashed}
            disabled={isLoading}
          >
            <SelectTrigger className="w-full sm:w-40">
              <SelectValue placeholder="Trashed" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="exclude">Active only</SelectItem>
              <SelectItem value="only">Trashed only</SelectItem>
              <SelectItem value="all">All</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <CardToolbar className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                disabled={isLoading || bulkActionPending || selectedRowIds.length === 0}
                title={selectedRowIds.length === 0 ? 'Select users to perform bulk actions' : 'Bulk actions'}
              >
                <Settings className="size-4" />
                {selectedRowIds.length > 0 && (
                  <span className="ml-1.5">({selectedRowIds.length})</span>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={() => runBulkAction('activate')}
                disabled={bulkActionPending || selectedTrashed === 'only'}
              >
                <UserCheck className="size-4" />
                Bulk activate
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => runBulkAction('deactivate')}
                disabled={bulkActionPending || selectedTrashed === 'only'}
              >
                <UserX className="size-4" />
                Bulk deactivate
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => runBulkAction('delete')}
                disabled={bulkActionPending || selectedTrashed === 'only'}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="size-4" />
                Trash
              </DropdownMenuItem>
              {selectedTrashed === 'only' && (
                <DropdownMenuItem
                  onClick={() => runBulkAction('permanent_delete')}
                  disabled={bulkActionPending}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="size-4" />
                  Permanently delete
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            disabled={isLoading && true}
            onClick={() => {
              setInviteDialogOpen(true);
            }}
          >
            <Plus />
            Add user
          </Button>
        </CardToolbar>
      </CardHeader>
    );
  };

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        onRowClick={handleRowClick}
        tableLayout={{
          columnsResizable: true,
          columnsPinnable: true,
          columnsMovable: true,
          columnsVisibility: true,
        }}
        tableClassNames={{
          edgeCell: 'px-5',
        }}
      >
        <Card>
          <DataGridToolbar />
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
      </DataGrid>

      <UserInviteDialog
        open={inviteDialogOpen}
        closeDialog={() => setInviteDialogOpen(false)}
      />

      <AlertDialog
        open={bulkConfirmOpen}
        onOpenChange={(open) => {
          if (!open) setBulkConfirmAction(null);
          setBulkConfirmOpen(open);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{bulkConfirmConfig.title}</AlertDialogTitle>
            <AlertDialogDescription>
              {bulkConfirmConfig.description}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={bulkActionPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                runBulkActionConfirm();
              }}
              disabled={bulkActionPending}
              className={
                bulkConfirmAction === 'delete' || bulkConfirmAction === 'permanent_delete'
                  ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                  : undefined
              }
            >
              {bulkActionPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  {bulkConfirmConfig.actionLabel}...
                </>
              ) : (
                bulkConfirmConfig.actionLabel
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export default UserList;
