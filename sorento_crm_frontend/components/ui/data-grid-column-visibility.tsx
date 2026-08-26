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
import { Column, Table } from '@tanstack/react-table';
import { DataGridContext } from '@/components/ui/data-grid';

/**
 * Every leaf column, group members included, in the order the grid DECLARES them.
 *
 * `getAllLeafColumns()` is the same list in VISUAL order, so on any listing where the user
 * had dragged a column this panel silently re-sorted itself and the checkbox they were
 * looking for had moved. `getAllColumns()` keeps definition order but stops at a group,
 * whose members would then be unreachable, so it is flattened here instead.
 */
export function leafColumnsInDefinitionOrder<TData>(
  columns: Column<TData, unknown>[],
): Column<TData, unknown>[] {
  return columns.flatMap((column) =>
    column.columns?.length ? leafColumnsInDefinitionOrder(column.columns) : [column],
  );
}

function DataGridColumnVisibility<TData>({ table, trigger }: { table: Table<TData>; trigger: ReactNode }) {
  const grid = useContext(DataGridContext);
  const columnPreferences = grid?.columnPreferences;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[150px] max-h-[60vh] overflow-y-auto">
        <DropdownMenuLabel className="font-medium">Toggle Columns</DropdownMenuLabel>
        {leafColumnsInDefinitionOrder(table.getAllColumns())
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
