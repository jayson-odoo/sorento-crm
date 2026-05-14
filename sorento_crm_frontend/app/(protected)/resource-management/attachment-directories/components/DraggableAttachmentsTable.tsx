'use client';

import { Fragment } from 'react';
import { useDraggable } from '@dnd-kit/core';
import { flexRender, type Cell, type HeaderGroup, type Row } from '@tanstack/react-table';
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
  DataGridTableHead,
  DataGridTableHeadRow,
  DataGridTableHeadRowCell,
  DataGridTableHeadRowCellResize,
  DataGridTableRowSpacer,
} from '@/components/ui/data-grid-table';
import type { Attachment } from '../../attachments/types/attachment.types';

const DRAG_ID_PREFIX = 'attachment-';

function DraggableAttachmentRow({
  row,
  currentDirectoryId,
  selectedIds,
}: {
  row: Row<Attachment>;
  currentDirectoryId: string | null;
  selectedIds: string[];
}) {
  const attachment = row.original;
  const isInSelection = selectedIds.includes(attachment.id);
  const batchIds = isInSelection && selectedIds.length > 1 ? selectedIds : [attachment.id];
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `${DRAG_ID_PREFIX}${attachment.id}`,
    data: {
      type: 'attachment',
      attachmentId: attachment.id,
      attachmentName: attachment.original_filename,
      currentDirectoryId: currentDirectoryId ?? null,
      attachmentIds: batchIds,
    },
  });

  return (
    <DataGridTableBodyRow
      row={row}
      dndRef={setNodeRef}
      dndStyle={{
        opacity: isDragging ? 0.5 : 1,
        cursor: 'grab',
        touchAction: 'none',
      }}
      dndAttributes={attributes as unknown as Record<string, unknown>}
      dndListeners={listeners as unknown as Record<string, unknown>}
    >
      {row.getVisibleCells().map((cell: Cell<Attachment, unknown>, colIndex) => (
        <DataGridTableBodyRowCell cell={cell} key={colIndex}>
          {flexRender(cell.column.columnDef.cell, cell.getContext())}
        </DataGridTableBodyRowCell>
      ))}
    </DataGridTableBodyRow>
  );
}

export function DraggableAttachmentsTable({
  currentDirectoryId,
  selectedIds,
  draggable,
}: {
  currentDirectoryId: string | null;
  selectedIds: string[];
  /** Disable drag (e.g. in trash view) so rows stay normal. */
  draggable: boolean;
}) {
  const { props, table, isLoading } = useDataGrid();
  const pagination = table.getState().pagination;

  return (
    <div className="relative">
      <DataGridTableBase>
        <DataGridTableHead>
          {table.getHeaderGroups().map((headerGroup: HeaderGroup<Attachment>, index) => (
            <DataGridTableHeadRow headerGroup={headerGroup} key={index}>
              {headerGroup.headers.map((header, hIndex) => {
                const { column } = header;
                return (
                  <DataGridTableHeadRowCell header={header} key={hIndex}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                    {props.tableLayout?.columnsResizable && column.getCanResize() && (
                      <DataGridTableHeadRowCellResize header={header} />
                    )}
                  </DataGridTableHeadRowCell>
                );
              })}
            </DataGridTableHeadRow>
          ))}
        </DataGridTableHead>

        {(props.tableLayout?.stripped || !props.tableLayout?.rowBorder) && <DataGridTableRowSpacer />}

        <DataGridTableBody>
          {props.loadingMode === 'skeleton' && isLoading && pagination?.pageSize ? (
            Array.from({ length: pagination.pageSize }).map((_, rowIndex) => (
              <DataGridTableBodyRowSkeleton key={rowIndex}>
                {table.getVisibleFlatColumns().map((column, colIndex) => (
                  <DataGridTableBodyRowSkeletonCell column={column} key={colIndex}>
                    {column.columnDef.meta?.skeleton}
                  </DataGridTableBodyRowSkeletonCell>
                ))}
              </DataGridTableBodyRowSkeleton>
            ))
          ) : table.getRowModel().rows.length ? (
            table.getRowModel().rows.map((row: Row<Attachment>) => (
              <Fragment key={row.id}>
                {draggable ? (
                  <DraggableAttachmentRow
                    row={row}
                    currentDirectoryId={currentDirectoryId}
                    selectedIds={selectedIds}
                  />
                ) : (
                  <DataGridTableBodyRow row={row}>
                    {row.getVisibleCells().map((cell: Cell<Attachment, unknown>, colIndex) => (
                      <DataGridTableBodyRowCell cell={cell} key={colIndex}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </DataGridTableBodyRowCell>
                    ))}
                  </DataGridTableBodyRow>
                )}
                {row.getIsExpanded() && <DataGridTableBodyRowExpandded row={row} />}
              </Fragment>
            ))
          ) : (
            <DataGridTableEmpty />
          )}
        </DataGridTableBody>
      </DataGridTableBase>
    </div>
  );
}
