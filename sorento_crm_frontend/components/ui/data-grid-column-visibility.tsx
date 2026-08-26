import { ReactNode, useContext } from 'react';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Table } from '@tanstack/react-table';
import { DataGridContext } from '@/components/ui/data-grid';

function DataGridColumnVisibility<TData>({ table, trigger }: { table: Table<TData>; trigger: ReactNode }) {
  const grid = useContext(DataGridContext);
  const columnPreferences = grid?.columnPreferences;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[150px] max-h-[60vh] overflow-y-auto">
        <DropdownMenuLabel className="font-medium">Toggle Columns</DropdownMenuLabel>
        {table
          // LEAF columns, not top-level ones: identical on a flat grid, but a grid with
          // column groups (the reports detail grid) would otherwise offer only the group,
          // which has no accessor, and so hide every column inside it from this panel.
          .getAllLeafColumns()
          .filter((column) => typeof column.accessorFn !== 'undefined' && column.getCanHide())
          .map((column) => {
            return (
              <DropdownMenuCheckboxItem
                key={column.id}
                className="capitalize"
                checked={column.getIsVisible()}
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={(value) => column.toggleVisibility(!!value)}
              >
                {column.columnDef.meta?.headerTitle || column.id}
              </DropdownMenuCheckboxItem>
            );
          })}
        {columnPreferences?.resetToDefaults && <DropdownMenuSeparator />}
        {columnPreferences?.resetToDefaults && (
          <DropdownMenuItem
            onClick={(e) => {
              e.preventDefault();
              void columnPreferences.resetToDefaults?.();
            }}
          >
            Reset columns
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export { DataGridColumnVisibility };
