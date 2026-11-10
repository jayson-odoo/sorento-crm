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
 * Every leaf column, group members and hidden columns included, in the order the grid DRAWS
 * them: left-pinned, then the centre in the reader's column order, then right-pinned.
 *
 * The Columns menu reads top to bottom exactly as the grid reads left to right, so it is the
 * truth about the screen (COLUMNS-TOGGLE-TRUTH, 10 Nov 2026). It used to list DEFINITION
 * order, so a column the reader's saved order had moved sat ticked at the top of the menu
 * while the grid drew it far right, off-screen: Products' Type, Variant Of and Variants,
 * parked past Updated by the old append-at-the-end merge, read as "ticked but not shown".
 * A hidden column keeps its slot, so ticking it back shows it where the menu said it was.
 */
export function leafColumnsInScreenOrder<TData>(table: Table<TData>): Column<TData, unknown>[] {
  return [
    ...table.getLeftLeafColumns(),
    ...table.getCenterLeafColumns(),
    ...table.getRightLeafColumns(),
  ];
}

/**
 * The menu's checkbox rows, shared by every Columns menu (the toolbar button here and the
 * column header's own submenu), so no two menus can disagree about the grid.
 */
export function DataGridColumnVisibilityItems<TData>({ table }: { table: Table<TData> }) {
  return (
    <>
      {leafColumnsInScreenOrder(table)
        .filter((column) => typeof column.accessorFn !== 'undefined' && column.getCanHide())
        .map((column) => (
          <DropdownMenuCheckboxItem
            key={column.id}
            className="capitalize"
            checked={column.getIsVisible()}
            onSelect={(event) => event.preventDefault()}
            onCheckedChange={(value) => column.toggleVisibility(!!value)}
          >
            {column.columnDef.meta?.headerTitle || column.id}
          </DropdownMenuCheckboxItem>
        ))}
    </>
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
        <DataGridColumnVisibilityItems table={table} />
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
