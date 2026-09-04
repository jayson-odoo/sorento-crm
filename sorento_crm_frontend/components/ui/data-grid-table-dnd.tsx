import { CSSProperties, Fragment, useId } from 'react';
import { useDataGrid } from '@/components/ui/data-grid';
import {
  DataGridTableBase,
  DataGridTableBody,
  DataGridTableBodyRow,
  DataGridTableBodyRowCell,
  DataGridTableBodyRowExpandded,
  DataGridTableBodyRowSkeleton,
  DataGridTableBodyRowSkeletonCell,
  DataGridTableEmpty,
  DataGridTableFoot,
  DataGridTableFootRowCell,
  footerGroupsWithContent,
  DataGridTableHead,
  DataGridTableHeadRow,
  DataGridTableHeadRowCell,
  DataGridTableHeadRowCellResize,
  DataGridTableRowSpacer,
  headerRowSpan,
  useBodySkeleton,
  skipMergedLeafHeader,
} from '@/components/ui/data-grid-table';
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { restrictToParentElement } from '@dnd-kit/modifiers';
import { horizontalListSortingStrategy, SortableContext, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Cell, flexRender, Header, HeaderGroup, Row } from '@tanstack/react-table';
import { mergeColumnOrderWithLeafColumns } from '@/lib/listing-column-preferences/mergeColumnOrder';
import { GripVertical } from 'lucide-react';

function DataGridTableDndHeader<TData>({
  header,
  rowSpan,
}: {
  header: Header<TData, unknown>;
  rowSpan: number;
}) {
  const { props } = useDataGrid();
  const { column } = header;

  // A GROUP header is not draggable: dragging it would mean dragging its members as a
  // block, and dnd-kit is registered on leaf ids. A PLACEHOLDER is the opposite - it IS
  // the single-level column's only header now that it spans both rows (the leaf it stands
  // in for is not rendered), so it stays draggable and each id registers exactly once.
  // Grids without column groups never take either branch.
  const isGroupHeader = !header.isPlaceholder && header.subHeaders.length > 0;

  const { attributes, isDragging, listeners, setNodeRef, transform, transition } = useSortable({
    id: header.column.id,
    disabled: isGroupHeader,
  });

  const style: CSSProperties = {
    opacity: isDragging ? 0.8 : 1,
    position: 'relative',
    transform: CSS.Translate.toString(transform),
    transition,
    whiteSpace: 'nowrap',
    width: header.column.getSize(),
    zIndex: isDragging ? 1 : 0,
  };

  if (isGroupHeader) {
    return (
      <DataGridTableHeadRowCell header={header}>
        <div className="flex w-full items-center justify-center text-center">
          {flexRender(header.column.columnDef.header, header.getContext())}
        </div>
      </DataGridTableHeadRowCell>
    );
  }

  return (
    <DataGridTableHeadRowCell
      header={header}
      dndStyle={style}
      dndDragging={isDragging}
      dndRef={setNodeRef}
      rowSpan={rowSpan}
    >
      <div
        className="flex items-center justify-start gap-0.5 w-full cursor-grab select-none"
        {...attributes}
        {...listeners}
        aria-label="Drag column to reorder"
      >
        {/* Keeping the grip icon purely visual (drag is on the entire header area). */}
        <GripVertical className="size-4 opacity-35 ms-1" aria-hidden="true" />
        {flexRender(header.column.columnDef.header, header.getContext())}
        {props.tableLayout?.columnsResizable && column.getCanResize() && (
          <DataGridTableHeadRowCellResize header={header} />
        )}
      </div>
    </DataGridTableHeadRowCell>
  );
}

function DataGridTableDndCell<TData>({ cell }: { cell: Cell<TData, unknown> }) {
  const { isDragging, setNodeRef, transform, transition } = useSortable({
    id: cell.column.id,
  });

  const style: CSSProperties = {
    opacity: isDragging ? 0.8 : 1,
    position: 'relative',
    transform: CSS.Translate.toString(transform),
    transition,
    width: cell.column.getSize(),
    zIndex: isDragging ? 1 : 0,
  };

  return (
    <DataGridTableBodyRowCell
      cell={cell}
      dndStyle={style}
      dndDragging={isDragging}
      dndRef={setNodeRef}
    >
      {flexRender(cell.column.columnDef.cell, cell.getContext())}
    </DataGridTableBodyRowCell>
  );
}

function DataGridTableDnd<TData>({ handleDragEnd }: { handleDragEnd: (event: DragEndEvent) => void }) {
  const { table, props } = useDataGrid();
  const pagination = table.getState().pagination;
  const showBodySkeleton = useBodySkeleton();

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
    useSensor(KeyboardSensor, {}),
  );

  const leafIds = table.getAllLeafColumns().map((c) => c.id);
  const rawOrder =
    Array.isArray(table.getState().columnOrder) && table.getState().columnOrder.length > 0
      ? (table.getState().columnOrder as string[])
      : leafIds;
  const orderedIds = mergeColumnOrderWithLeafColumns(rawOrder, leafIds);

  return (
    <DndContext
      id={useId()}
      collisionDetection={closestCenter}
      modifiers={[restrictToParentElement]}
      onDragEnd={handleDragEnd}
      sensors={sensors}
    >
      <div className="relative">
        <DataGridTableBase>
          <DataGridTableHead>
            {table.getHeaderGroups().map((headerGroup: HeaderGroup<TData>, index) => {
              const rowCount = table.getHeaderGroups().length;
              return (
                <DataGridTableHeadRow headerGroup={headerGroup} key={index}>
                  <SortableContext items={orderedIds} strategy={horizontalListSortingStrategy}>
                    {headerGroup.headers
                      .filter((header) => !skipMergedLeafHeader(header, rowCount))
                      .map((header, index) => (
                        <DataGridTableDndHeader
                          header={header}
                          rowSpan={headerRowSpan(header, rowCount)}
                          key={index}
                        />
                      ))}
                  </SortableContext>
                </DataGridTableHeadRow>
              );
            })}
          </DataGridTableHead>

          {(props.tableLayout?.stripped || !props.tableLayout?.rowBorder) && <DataGridTableRowSpacer />}

          <DataGridTableBody>
            {showBodySkeleton ? (
              Array.from({ length: pagination.pageSize }).map((_, rowIndex) => (
                <DataGridTableBodyRowSkeleton key={rowIndex}>
                  {/* LEAF columns, as in DataGridTable: the flat list includes a group
                      PARENT, which is not a cell. */}
                  {table.getVisibleLeafColumns().map((column, colIndex) => {
                    return (
                      <DataGridTableBodyRowSkeletonCell column={column} key={colIndex}>
                        {column.columnDef.meta?.skeleton}
                      </DataGridTableBodyRowSkeletonCell>
                    );
                  })}
                </DataGridTableBodyRowSkeleton>
              ))
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row: Row<TData>, index) => {
                // Same optional grouping as the non-draggable DataGridTable.
                // Both branches need it: columnsDraggable defaults to TRUE, so
                // this component - not the other one - is what most listings
                // actually render through.
                const groupHeader = props.renderGroupHeader?.(
                  row.original as TData,
                  index === 0 ? null : (table.getRowModel().rows[index - 1].original as TData),
                );
                return (
                  <Fragment key={row.id}>
                    {groupHeader != null && (
                      <tr className="bg-muted/50" data-testid="data-grid-group-header">
                        <td
                          colSpan={row.getVisibleCells().length}
                          className="px-4 py-2 text-xs font-medium text-muted-foreground"
                        >
                          {groupHeader}
                        </td>
                      </tr>
                    )}
                    <DataGridTableBodyRow row={row} key={index}>
                      {row.getVisibleCells().map((cell: Cell<TData, unknown>) => {
                        return (
                          <SortableContext
                            key={cell.id}
                            items={orderedIds}
                            strategy={horizontalListSortingStrategy}
                          >
                            <DataGridTableDndCell cell={cell} />
                          </SortableContext>
                        );
                      })}
                    </DataGridTableBodyRow>
                    {row.getIsExpanded() && <DataGridTableBodyRowExpandded row={row} />}
                  </Fragment>
                );
              })
            ) : (
              <DataGridTableEmpty />
            )}
          </DataGridTableBody>

          {/* Same totals row as the non-draggable branch. `columnsDraggable` defaults to TRUE,
              so this component is what a listing actually renders through, and a footer added
              only to the other branch would never appear. */}
          {table.getVisibleFlatColumns().some((column) => Boolean(column.columnDef.footer)) && (
            <DataGridTableFoot>
              {footerGroupsWithContent(table).map((footerGroup) => (
                <tr key={footerGroup.id}>
                  {footerGroup.headers.map((header) => (
                    <DataGridTableFootRowCell key={header.id} header={header}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.footer, header.getContext())}
                    </DataGridTableFootRowCell>
                  ))}
                </tr>
              ))}
            </DataGridTableFoot>
          )}
        </DataGridTableBase>
      </div>
    </DndContext>
  );
}

export { DataGridTableDnd };
