'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X } from 'lucide-react';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatDateTime } from '@/lib/helpers';
import { useAuditLogs } from '../hooks/useAuditLogs';
import type { AuditLog } from '../types/auditLog.types';

const ACTION_ALL = '__all__';

function actionBadgeVariant(action: string): 'success' | 'warning' | 'destructive' | 'secondary' {
  switch (action.toUpperCase()) {
    case 'INSERT':
    case 'CREATE':
      return 'success';
    case 'UPDATE':
      return 'warning';
    case 'DELETE':
      return 'destructive';
    default:
      return 'secondary';
  }
}

function prettyJson(value: Record<string, unknown> | null | undefined): string {
  if (value == null) return '—';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function AuditLogsList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState(ACTION_ALL);
  const [userId, setUserId] = useState('');
  const [entityId, setEntityId] = useState('');
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useAuditLogs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    entity_type: entityType || undefined,
    entity_id: entityId || undefined,
    user_id: userId || undefined,
    action: action !== ACTION_ALL ? action : undefined,
  });

  const activeFilterCount =
    (entityType ? 1 : 0) + (action !== ACTION_ALL ? 1 : 0) + (userId ? 1 : 0);

  const columns = useMemo<ColumnDef<AuditLog>[]>(
    () => [
      {
        accessorKey: 'changed_at',
        header: ({ column }) => <DataGridColumnHeader title="Changed At" column={column} />,
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-sm">
            {formatDateTime(new Date(row.original.changed_at))}
          </span>
        ),
        size: 180,
        meta: { headerTitle: 'Changed At', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'entity_type',
        header: ({ column }) => <DataGridColumnHeader title="Entity Type" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="light">
            {row.original.entity_type}
          </Badge>
        ),
        size: 150,
        meta: { headerTitle: 'Entity Type' },
      },
      {
        accessorKey: 'entity_id',
        header: ({ column }) => <DataGridColumnHeader title="Entity ID" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-xs text-muted-foreground" title={row.original.entity_id}>
            {row.original.entity_id}
          </span>
        ),
        size: 160,
        meta: { headerTitle: 'Entity ID' },
      },
      {
        accessorKey: 'action',
        header: ({ column }) => <DataGridColumnHeader title="Action" column={column} />,
        cell: ({ row }) => (
          <Badge variant={actionBadgeVariant(row.original.action)} appearance="light">
            {row.original.action}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Action' },
      },
      {
        accessorKey: 'user_display_name',
        header: ({ column }) => <DataGridColumnHeader title="User" column={column} />,
        cell: ({ row }) => {
          const name = row.original.user_display_name;
          return (
            <span className="block truncate text-sm" title={name || 'System'}>
              {name || (row.original.user_id ? '—' : 'System')}
            </span>
          );
        },
        size: 170,
        meta: { headerTitle: 'User' },
      },
      {
        accessorKey: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const desc = row.original.description || '—';
          return (
            <span className="block truncate text-sm text-muted-foreground" title={desc}>
              {desc}
            </span>
          );
        },
        size: 260,
        meta: { headerTitle: 'Description' },
      },
      {
        accessorKey: 'ip_address',
        header: ({ column }) => <DataGridColumnHeader title="IP" column={column} />,
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground">{row.original.ip_address || '—'}</span>
        ),
        size: 130,
        meta: { headerTitle: 'IP' },
      },
      {
        id: 'details',
        header: () => <span className="sr-only">Details</span>,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedLog(row.original);
            }}
          >
            Details
          </Button>
        ),
        size: 100,
        meta: { headerTitle: 'Details' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
  });

  const clearFilters = () => {
    setEntityType('');
    setAction(ACTION_ALL);
    setUserId('');
  };

  if (isError) {
    return (
      <Card>
        <CardTable>
          <div className="p-8 text-center text-muted-foreground">
            <p className="font-medium text-destructive">Failed to load audit logs.</p>
            <p className="text-sm mt-1">
              {error instanceof Error ? error.message : 'Please try again.'}
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => void refetch()}>
              Retry
            </Button>
          </div>
        </CardTable>
      </Card>
    );
  }

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        emptyMessage="No audit log entries found."
        onRowClick={(row) => setSelectedLog(row)}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search by entity ID..."
                    value={entityId}
                    onChange={(e) => setEntityId(e.target.value)}
                    className="ps-9 w-72"
                  />
                  {entityId && (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                      onClick={() => setEntityId('')}
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              filters={{
                kind: 'custom',
                active: activeFilterCount > 0,
                activeCount: activeFilterCount,
                content: (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Entity type</label>
                      <Input
                        placeholder="e.g. complaint, purchase_request"
                        value={entityType}
                        onChange={(e) => setEntityType(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Action</label>
                      <Select value={action} onValueChange={setAction}>
                        <SelectTrigger>
                          <SelectValue placeholder="Action" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={ACTION_ALL}>All actions</SelectItem>
                          <SelectItem value="INSERT">Insert</SelectItem>
                          <SelectItem value="CREATE">Create</SelectItem>
                          <SelectItem value="UPDATE">Update</SelectItem>
                          <SelectItem value="DELETE">Delete</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">User ID</label>
                      <Input
                        placeholder="Filter by user ID"
                        value={userId}
                        onChange={(e) => setUserId(e.target.value)}
                      />
                    </div>
                    {activeFilterCount > 0 && (
                      <Button variant="ghost" size="sm" className="w-full" onClick={clearFilters}>
                        Clear filters
                      </Button>
                    )}
                  </div>
                ),
              }}
              exportConfig={{ filename: 'audit_logs_export.xlsx' }}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
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
      </DataGrid>

      <Dialog open={selectedLog !== null} onOpenChange={(open) => !open && setSelectedLog(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Audit entry details</DialogTitle>
            <DialogDescription>
              {selectedLog
                ? `${selectedLog.action} on ${selectedLog.entity_type} · ${formatDateTime(
                    new Date(selectedLog.changed_at),
                  )}`
                : ''}
            </DialogDescription>
          </DialogHeader>
          {selectedLog && (
            <DialogBody className="space-y-4">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-xs font-medium text-muted-foreground">Entity type</dt>
                  <dd>{selectedLog.entity_type}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-muted-foreground">Entity ID</dt>
                  <dd className="break-all">{selectedLog.entity_id}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-muted-foreground">User</dt>
                  <dd>{selectedLog.user_display_name || (selectedLog.user_id ? '—' : 'System')}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-muted-foreground">IP address</dt>
                  <dd>{selectedLog.ip_address || '—'}</dd>
                </div>
                {selectedLog.description && (
                  <div className="col-span-2">
                    <dt className="text-xs font-medium text-muted-foreground">Description</dt>
                    <dd>{selectedLog.description}</dd>
                  </div>
                )}
              </dl>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Old values</p>
                  <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
                    {prettyJson(selectedLog.old_values)}
                  </pre>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">New values</p>
                  <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
                    {prettyJson(selectedLog.new_values)}
                  </pre>
                </div>
              </div>
            </DialogBody>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
