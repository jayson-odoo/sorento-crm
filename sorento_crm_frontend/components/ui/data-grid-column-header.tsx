import { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useDataGrid } from '@/components/ui/data-grid';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Column } from '@tanstack/react-table';
import {
  ArrowDown,
  ArrowLeft,
  ArrowLeftToLine,
  ArrowRight,
  ArrowRightToLine,
  ArrowUp,
  Check,
  ChevronsUpDown,
  PinOff,
  Settings2,
} from 'lucide-react';
import { mergeColumnOrderWithLeafColumns } from '@/lib/listing-column-preferences/mergeColumnOrder';

interface DataGridColumnHeaderProps<TData, TValue> extends HTMLAttributes<HTMLDivElement> {
  column: Column<TData, TValue>;
  title?: string;
  icon?: ReactNode;
  pinnable?: boolean;
  filter?: ReactNode;
  visibility?: boolean;
}

/**
 * Whether `columnId` can move one step in `direction`, given an ALREADY-RESOLVED order
 * (S4, M5 review run 1). Exported and pure so it can be unit-tested directly: the render
 * path that would otherwise exercise it (`headerControls` below, the Move to Left/Right
 * menu items) is not currently mounted - see the module doc on `headerControls`.
 */
export function canMoveColumnInOrder(
  order: string[],
  columnId: string,
  direction: 'left' | 'right',
): boolean {
  const index = order.indexOf(columnId);
  if (index === -1) return false;
  return direction === 'left' ? index > 0 : index < order.length - 1;
}

/** The reorder `moveColumn` below applies, as a pure function of an already-resolved order. */
export function moveColumnInOrder(
  order: string[],
  columnId: string,
  direction: 'left' | 'right',
): string[] {
  const index = order.indexOf(columnId);
  if (index === -1) return order;
  if (direction === 'left' && index === 0) return order;
  if (direction === 'right' && index === order.length - 1) return order;
  const next = [...order];
  const [moved] = next.splice(index, 1);
  next.splice(direction === 'left' ? index - 1 : index + 1, 0, moved);
  return next;
}

function DataGridColumnHeader<TData, TValue>({
  column,
  title = '',
  icon,
  className,
  filter,
  visibility = true,
}: DataGridColumnHeaderProps<TData, TValue>) {
  const { table, props, recordCount, columnPreferences } = useDataGrid();

  // `table.getState().columnOrder` starts as `[]` until a caller sets it explicitly, which
  // most grids never do (`useListingColumnPreferences` only calls `setColumnOrder` once
  // personalization loads). Reading that raw, possibly-empty state gave `indexOf(column.id)
  // === -1` on every column, so Move to Left/Right read as permanently disabled on the ~200
  // grids without column-order state (S4, M5 review run 1). Falls back to the leaf column
  // order exactly as the DnD drag handler already does (`data-grid-table.tsx`'s
  // `handleDragEnd`).
  const effectiveColumnOrder = (): string[] => {
    const columnOrderState = table.getState().columnOrder as string[] | undefined;
    const leafIds = table.getAllLeafColumns().map((c) => c.id);
    const rawOrder =
      Array.isArray(columnOrderState) && columnOrderState.length > 0 ? columnOrderState : leafIds;
    return mergeColumnOrderWithLeafColumns(rawOrder, leafIds);
  };

  const moveColumn = (direction: 'left' | 'right') => {
    const currentOrder = effectiveColumnOrder();
    const nextOrder = moveColumnInOrder(currentOrder, column.id, direction);
    if (nextOrder === currentOrder) return;
    table.setColumnOrder(nextOrder);
  };

  const canMove = (direction: 'left' | 'right'): boolean =>
    canMoveColumnInOrder(effectiveColumnOrder(), column.id, direction);

  const headerLabel = () => {
    return (
      <div
        className={cn(
          'text-accent-foreground font-normal inline-flex h-full items-center gap-1.5 text-[0.8125rem] leading-[calc(1.125/0.8125)] [&_svg]:size-3.5 [&_svg]:opacity-60',
          className,
        )}
      >
        {icon && icon}
        {title}
      </div>
    );
  };

  const headerButton = () => {
    return (
      <Button
        variant="ghost"
        className={cn(
          'text-secondary-foreground rounded-md font-normal -ms-2 px-2 h-7 hover:bg-secondary data-[state=open]:bg-secondary hover:text-foreground data-[state=open]:text-foreground',
          className,
        )}
        // Not `isLoading`: sorting is exactly what the reader reaches for while
        // the next page is on its way, and a header that goes dead on every
        // refetch is the latency they feel (M4-05).
        disabled={recordCount === 0}
        onClick={() => {
          if (!column.getCanSort()) return;
          const isSorted = column.getIsSorted();
          if (isSorted === 'asc') {
            column.toggleSorting(true);
          } else if (isSorted === 'desc') {
            column.clearSorting();
          } else {
            column.toggleSorting(false);
          }
        }}
        onPointerDown={(e) => {
          // Prevent dnd-kit column drag listeners from interfering with sorting clicks.
          e.stopPropagation();
        }}
      >
        {icon && icon}
        {title}

        {column.getCanSort() &&
          (column.getIsSorted() === 'desc' ? (
            <ArrowDown className="size-[0.7rem]! mt-px" />
          ) : column.getIsSorted() === 'asc' ? (
            <ArrowUp className="size-[0.7rem]! mt-px" />
          ) : (
            <ChevronsUpDown className="size-[0.7rem]! mt-px" />
          ))}
      </Button>
    );
  };

  const headerPin = () => {
    return (
      <Button
        mode="icon"
        size="sm"
        variant="ghost"
        className="-me-1 size-7 rounded-md"
        onClick={() => column.pin(false)}
        aria-label={`Unpin ${title} column`}
        title={`Unpin ${title} column`}
      >
        <PinOff className="size-3.5! opacity-50!" aria-hidden="true" />
      </Button>
    );
  };

  const headerControls = () => {
    return (
      <div className="flex items-center h-full gap-1.5 justify-between">
        {column.getCanSort() ? headerButton() : headerLabel()}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              mode="icon"
              size="sm"
              variant="ghost"
              className="rounded-md h-7 w-7"
              aria-label={`Column options for ${title || column.id}`}
              title={`Column options for ${title || column.id}`}
            >
              <Settings2 className="size-4 opacity-70" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-40" align="start">
            {filter && <DropdownMenuLabel>{filter}</DropdownMenuLabel>}

            {filter && (column.getCanSort() || column.getCanPin() || visibility) && <DropdownMenuSeparator />}

            {column.getCanSort() && (
              <>
                <DropdownMenuItem
                  onClick={() => {
                    if (column.getIsSorted() === 'asc') {
                      column.clearSorting();
                    } else {
                      column.toggleSorting(false);
                    }
                  }}
                  disabled={!column.getCanSort()}
                >
                  <ArrowUp className="size-3.5!" />
                  <span className="grow">Asc</span>
                  {column.getIsSorted() === 'asc' && <Check className="size-4 opacity-100! text-primary" />}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    if (column.getIsSorted() === 'desc') {
                      column.clearSorting();
                    } else {
                      column.toggleSorting(true);
                    }
                  }}
                  disabled={!column.getCanSort()}
                >
                  <ArrowDown className="size-3.5!" />
                  <span className="grow">Desc</span>
                  {column.getIsSorted() === 'desc' && <Check className="size-4 opacity-100! text-primary" />}
                </DropdownMenuItem>
              </>
            )}

            {(filter || column.getCanSort()) && (column.getCanSort() || column.getCanPin() || visibility) && (
              <DropdownMenuSeparator />
            )}

            {props.tableLayout?.columnsPinnable && column.getCanPin() && (
              <>
                <DropdownMenuItem onClick={() => column.pin(column.getIsPinned() === 'left' ? false : 'left')}>
                  <ArrowLeftToLine className="size-3.5!" aria-hidden="true" />
                  <span className="grow">Pin to left</span>
                  {column.getIsPinned() === 'left' && <Check className="size-4 opacity-100! text-primary" />}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => column.pin(column.getIsPinned() === 'right' ? false : 'right')}>
                  <ArrowRightToLine className="size-3.5!" aria-hidden="true" />
                  <span className="grow">Pin to right</span>
                  {column.getIsPinned() === 'right' && <Check className="size-4 opacity-100! text-primary" />}
                </DropdownMenuItem>
              </>
            )}

            {props.tableLayout?.columnsMovable && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => moveColumn('left')}
                  disabled={!canMove('left') || column.getIsPinned() !== false}
                >
                  <ArrowLeft className="size-3.5!" aria-hidden="true" />
                  <span>Move to Left</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => moveColumn('right')}
                  disabled={!canMove('right') || column.getIsPinned() !== false}
                >
                  <ArrowRight className="size-3.5!" aria-hidden="true" />
                  <span>Move to Right</span>
                </DropdownMenuItem>
              </>
            )}

            {props.tableLayout?.columnsVisibility &&
              visibility &&
              (column.getCanSort() || column.getCanPin() || filter) && <DropdownMenuSeparator />}

            {props.tableLayout?.columnsVisibility && visibility && (
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <Settings2 className="size-3.5!" />
                  <span>Columns</span>
                </DropdownMenuSubTrigger>
                <DropdownMenuPortal>
                  <DropdownMenuSubContent>
                    {table
                      .getAllColumns()
                      .filter((col) => typeof col.accessorFn !== 'undefined' && col.getCanHide())
                      .map((col) => {
                        return (
                          <DropdownMenuCheckboxItem
                            key={col.id}
                            checked={col.getIsVisible()}
                            onSelect={(event) => event.preventDefault()}
                            onCheckedChange={(value) => col.toggleVisibility(!!value)}
                            className="capitalize"
                          >
                            {col.columnDef.meta?.headerTitle || col.id}
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
                  </DropdownMenuSubContent>
                </DropdownMenuPortal>
              </DropdownMenuSub>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
        {props.tableLayout?.columnsPinnable && column.getCanPin() && column.getIsPinned() && headerPin()}
      </div>
    );
  };

  // Used only by legacy dropdown mode (we currently render only sorting).
  // Keeps eslint from flagging the function as unused.
  //
  // M5 review run 1 (S4) found this the hard way: `headerControls` is where Move to
  // Left/Right, Pin and per-column Hide live, and NONE of it renders anywhere today - the
  // return below only ever produces `headerButton()` or `headerLabel()`. M5-05's own
  // "Move to Left/Right on every header by default" default (`data-grid.tsx`) therefore has
  // no visible effect on current main. `moveColumn`/`canMove` above got the real logic bug
  // fixed (the empty-`columnOrder` fallback) because it was cheap and correct regardless,
  // but wiring `headerControls` into the render tree is a separate, materially bigger
  // change - a settings icon and dropdown appearing on every column header across ~200
  // grids - and needs its own design call, not a side effect of this fix.
  void headerControls;

  if (column.getCanSort() || (props.tableLayout?.columnsResizable && column.getCanResize())) {
    return <div className="flex items-center h-full">{headerButton()}</div>;
  }

  return headerLabel();
}

export { DataGridColumnHeader, type DataGridColumnHeaderProps };
