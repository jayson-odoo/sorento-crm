'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Columns3, Edit2, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import type { PublicHoliday } from '../types/workCalendar.types';
import { usePublicHolidays } from '../hooks/useWorkCalendar';
import PublicHolidayFormDialog from './PublicHolidayFormDialog';
import PublicHolidayDeleteDialog from './PublicHolidayDeleteDialog';

export default function PublicHolidaysList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'date', desc: false }]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [selectedHoliday, setSelectedHoliday] = useState<PublicHoliday | null>(null);

  const { data, isLoading, refetch, isFetching } = usePublicHolidays({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
  });

  const columns = useMemo<ColumnDef<PublicHoliday>[]>(
    () => [
      {
        accessorKey: 'date',
        header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />,
        cell: ({ row }) => row.original.date,
        size: 140,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Holiday" column={column} />,
        size: 220,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        size: 300,
        cell: ({ row }) => row.original.description || '-',
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedHoliday(row.original);
                setIsFormOpen(true);
              }}
            >
              <Edit2 className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedHoliday(row.original);
                setIsDeleteOpen(true);
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
    data: data?.data || [],
    columns,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    pageCount: data ? Math.ceil(data.pagination.total / pagination.pageSize) : 0,
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
      tableLayout={{ columnsVisibility: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
      >
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <h3 className="text-base font-semibold">Public Holidays</h3>
              <p className="text-sm text-muted-foreground">Dates excluded from delivery calculations.</p>
            </div>
            <div className="flex items-center gap-2">
              <DataGridColumnVisibility
                table={table}
                trigger={
                  <Button variant="outline" size="sm" className="gap-1">
                    <Columns3 className="size-4" />
                    Columns
                  </Button>
                }
              />
              <Button
                onClick={() => {
                setSelectedHoliday(null);
                setIsFormOpen(true);
              }}
            >
              <Plus className="size-4 mr-2" />
              Add Holiday
              </Button>
            </div>
          </CardHeader>
          <CardTable>
            <ScrollArea className="w-full">
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <PublicHolidayFormDialog
        open={isFormOpen}
        onOpenChange={setIsFormOpen}
        holiday={selectedHoliday}
      />
      <PublicHolidayDeleteDialog
        open={isDeleteOpen}
        onOpenChange={setIsDeleteOpen}
        holiday={selectedHoliday}
      />
    </>
  );
}
