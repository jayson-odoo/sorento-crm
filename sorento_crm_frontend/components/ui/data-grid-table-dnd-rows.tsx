import { CSSProperties, useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { useDataGrid } from '@/components/ui/data-grid';
import {
  DataGridTableBase,
  DataGridTableBody,
  DataGridTableBodyRow,
  DataGridTableBodyRowCell,
  DataGridTableBodyRowSkeleton,
  DataGridTableBodyRowSkeletonCell,
  DataGridTableEmpty,
  DataGridTableHead,
  DataGridTableHeadRow,
  DataGridTableHeadRowCell,
  DataGridTableHeadRowCellResize,
  DataGridTableRowSpacer,
  useBodySkeleton,
  useReturnedRowId,
} from '@/components/ui/data-grid-table';
import {
  closestCenter,
  defaultDropAnimation,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  UniqueIdentifier,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Cell, flexRender, HeaderGroup, Row } from '@tanstack/react-table';
import { GripHorizontal } from 'lucide-react';

function DataGridTableDndRowHandle({ rowId }: { rowId: string }) {
  const { attributes, listeners } = useSortable({
    id: rowId,
  });

  return (
    <Button variant="dim" size="sm" className="size-7" {...attributes} {...listeners}>
      <GripHorizontal />
    </Button>
  );
}

function DataGridTableDndRow<TData>({
  row,
  returnedFromId,
}: {
  row: Row<TData>;
  /** Resolved once by `DataGridTableDndRows` and passed down - see `useReturnedRowId`'s doc. */
  returnedFromId: string | null;
}) {
  const { transform, transition, setNodeRef, isDragging } = useSortable({
    id: row.id,
  });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform), //let dnd-kit do its thing
    transition: transition,
    opacity: isDragging ? 0.8 : 1,
    zIndex: isDragging ? 1 : 0,
    position: 'relative',
  };
  return (
    <DataGridTableBodyRow
      row={row}
      returnedFromId={returnedFromId}
      dndRef={setNodeRef}
      dndStyle={style}
      key={row.id}
    >
      {row.getVisibleCells().map((cell: Cell<TData, unknown>, colIndex) => {
        return (
          <DataGridTableBodyRowCell cell={cell} key={colIndex}>
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </DataGridTableBodyRowCell>
        );
      })}
    </DataGridTableBodyRow>
  );
}

function DataGridTableDndRows<TData>({
  handleDragEnd,
  dataIds,
}: {
  handleDragEnd: (event: DragEndEvent) => void;
  dataIds: UniqueIdentifier[];
}) {
  const { table, props } = useDataGrid();
  const pagination = table.getState().pagination;
  const showBodySkeleton = useBodySkeleton();
  // ONCE per grid (S5/S7, M5 review run 1) - this render path does not go through
  // `DataGridTable`, so it resolves its own, the same way that one does.
  const returnedFromId = useReturnedRowId();
  const [activeRow, setActiveRow] = useState<Row<TData> | null>(null);

  // Same activation constraint as the column reorderer (data-grid-table-dnd.tsx,
  // S8-06): without one, the handle started a drag on the very first pixel of
  // movement, so a click that merely twitched a little read as a reorder.
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
    useSensor(KeyboardSensor, {}),
  );

  const handleDragStart = (event: DragStartEvent) => {
    const row = table.getRowModel().rows.find((r) => r.id === event.active.id);
    setActiveRow(row ?? null);
  };

  const handleDragEndInternal = (event: DragEndEvent) => {
    setActiveRow(null);
    handleDragEnd(event);
  };

  return (
    <DndContext
      id={useId()}
      collisionDetection={closestCenter}
      modifiers={[restrictToVerticalAxis]}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEndInternal}
      onDragCancel={() => setActiveRow(null)}
      sensors={sensors}
    >
      <div className="relative">
        <DataGridTableBase>
          <DataGridTableHead>
            {table.getHeaderGroups().map((headerGroup: HeaderGroup<TData>, index) => {
              return (
                <DataGridTableHeadRow headerGroup={headerGroup} key={index}>
                  {headerGroup.headers.map((header, index) => {
                    const { column } = header;

                    return (
                      <DataGridTableHeadRowCell header={header} key={index}>
                        {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                        {props.tableLayout?.columnsResizable && column.getCanResize() && (
                          <DataGridTableHeadRowCellResize header={header} />
                        )}
                      </DataGridTableHeadRowCell>
                    );
                  })}
                </DataGridTableHeadRow>
              );
            })}
          </DataGridTableHead>

          {(props.tableLayout?.stripped || !props.tableLayout?.rowBorder) && <DataGridTableRowSpacer />}

          <DataGridTableBody>
            {showBodySkeleton ? (
              Array.from({ length: pagination.pageSize }).map((_, rowIndex) => (
                <DataGridTableBodyRowSkeleton key={rowIndex}>
                  {table.getVisibleFlatColumns().map((column, colIndex) => {
                    return (
                      <DataGridTableBodyRowSkeletonCell column={column} key={colIndex}>
                        {column.columnDef.meta?.skeleton}
                      </DataGridTableBodyRowSkeletonCell>
                    );
                  })}
                </DataGridTableBodyRowSkeleton>
              ))
            ) : table.getRowModel().rows.length ? (
              <SortableContext items={dataIds} strategy={verticalListSortingStrategy}>
                {table.getRowModel().rows.map((row: Row<TData>) => {
                  return (
                    <DataGridTableDndRow row={row} returnedFromId={returnedFromId} key={row.id} />
                  );
                })}
              </SortableContext>
            ) : (
              <DataGridTableEmpty />
            )}
          </DataGridTableBody>
        </DataGridTableBase>
      </div>
      {/* The row that follows the pointer while dragging, and the settle
          animation back into the list on drop (S8-06) - `useSortable`'s own
          FLIP already re-arranges the OTHER rows smoothly; this is what makes
          the dragged one itself land rather than just disappear. */}
      <DragOverlay dropAnimation={defaultDropAnimation}>
        {activeRow ? (
          // `overflow-x-auto`: the overlay has none of the real grid's width
          // constraint, so a row with more columns than fit under the pointer
          // scrolls sideways instead of being clipped.
          <div className="overflow-x-auto rounded-md border border-border bg-background shadow-lg">
            <table className="w-full caption-bottom text-sm">
              <tbody>
                {/* No `returnedFromId`: this floating clone follows the pointer, it is
                    never the settled row the reader returned to. */}
                <DataGridTableBodyRow row={activeRow}>
                  {activeRow.getVisibleCells().map((cell: Cell<TData, unknown>, colIndex) => (
                    <DataGridTableBodyRowCell cell={cell} key={colIndex}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </DataGridTableBodyRowCell>
                  ))}
                </DataGridTableBodyRow>
              </tbody>
            </table>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

export { DataGridTableDndRowHandle, DataGridTableDndRows };
