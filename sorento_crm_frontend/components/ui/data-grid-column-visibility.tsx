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
import { isFixedUtilityColumn } from '@/components/ui/data-grid-table-dnd';
import { Lock } from 'lucide-react';

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

/** A column's own name: `meta.headerTitle`, else a plain-string header. Empty for chrome. */
function columnTitle<TData>(column: Column<TData, unknown>): string {
  const title = column.columnDef.meta?.headerTitle;
  if (typeof title === 'string' && title.trim()) return title;
  const header = column.columnDef.header;
  return typeof header === 'string' ? header.trim() : '';
}

/**
 * True for every column the reader sees as DATA - each one is a menu row, so the menu lists
 * everything the grid can show (owner rule, 10 Nov 2026). Grid chrome is left out: the
 * fixed utility columns (row select, expanders: `isFixedUtilityColumn`), the trailing
 * row-actions column, and any locked column with no name of its own to list.
 */
export function isColumnsMenuColumn<TData>(column: Column<TData, unknown>): boolean {
  if (isFixedUtilityColumn(column.columnDef) || column.id === 'select' || column.id === 'actions') {
    return false;
  }
  if (columnTitle(column)) return true;
  // A hideable data column with no title keeps its row, labelled by its id, as before.
  return column.getCanHide() && typeof column.accessorFn !== 'undefined';
}

/**
 * The menu's checkbox rows, shared by every Columns menu (the toolbar button here and the
 * column header's own submenu), so no two menus can disagree about the grid.
 *
 * A column the list locks (`enableHiding: false`, the one identifying key column per list)
 * is still a row: ticked, disabled, with a lock - so the menu never omits a column the grid
 * draws.
 */
export function DataGridColumnVisibilityItems<TData>({ table }: { table: Table<TData> }) {
  return (
    <>
      {leafColumnsInScreenOrder(table)
        .filter(isColumnsMenuColumn)
        .map((column) => {
          const locked = !column.getCanHide();
          return (
            <DropdownMenuCheckboxItem
              key={column.id}
              className="capitalize"
              checked={locked || column.getIsVisible()}
              disabled={locked}
              onSelect={(event) => event.preventDefault()}
              onCheckedChange={(value) => {
                if (!locked) column.toggleVisibility(!!value);
              }}
            >
              {columnTitle(column) || column.id}
              {locked && (
                <Lock aria-hidden="true" data-testid="column-locked" className="ms-auto size-3.5 opacity-60" />
              )}
            </DropdownMenuCheckboxItem>
          );
        })}
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
