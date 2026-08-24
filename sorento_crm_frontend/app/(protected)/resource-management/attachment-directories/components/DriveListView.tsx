'use client';

import {
  Fragment,
  forwardRef,
  useCallback,
  type CSSProperties,
  type ReactNode,
  type Ref,
} from 'react';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import { flexRender, type Cell, type HeaderGroup, type Row } from '@tanstack/react-table';
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from '@/components/ui/context-menu';
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
} from '@/components/ui/data-grid-table';
import { isFolderItem, type DriveItem } from '../../attachments/services/driveService';

const DND_ID_ATTACHMENT_PREFIX = 'attachment-';
// Grid folders use a DISTINCT prefix from the tree's `folder-` so a folder shown
// in BOTH panes doesn't register duplicate dnd-kit ids (must match
// DND_ID_GRID_FOLDER_PREFIX in AttachmentDirectoriesView).
const DND_ID_GRID_FOLDER_PREFIX = 'gridfolder-';

function setRefs<T>(...refs: Array<Ref<T> | undefined>) {
  return (el: T | null) => {
    for (const ref of refs) {
      if (!ref) continue;
      if (typeof ref === 'function') ref(el);
      else (ref as { current: T | null }).current = el;
    }
  };
}

/**
 * Bridges the Radix ContextMenuTrigger (which clones with `asChild` and injects
 * its own ref + onContextMenu/onPointer* handlers) into `DataGridTableBodyRow`,
 * whose `<tr>` only forwards `dndRef` + spread `dndAttributes`. We compose the
 * Radix ref with the dnd ref and merge the Radix handlers into `dndAttributes`
 * so right-click / long-press actually anchors to the row.
 */
interface ContextMenuRowProps {
  row: Row<DriveItem>;
  dndRef: (el: HTMLElement | null) => void;
  dndStyle: CSSProperties;
  dndAttributes?: Record<string, unknown>;
  dndListeners?: Record<string, unknown>;
}

const ContextMenuRow = forwardRef<HTMLTableRowElement, ContextMenuRowProps>(
  function ContextMenuRow(props, radixRef) {
    const { row, dndRef, dndStyle, dndAttributes, dndListeners, ...radixProps } =
      props as ContextMenuRowProps & Record<string, unknown>;
    return (
      <DataGridTableBodyRow
        row={row}
        dndRef={setRefs<HTMLTableRowElement>(dndRef, radixRef)}
        dndStyle={dndStyle}
        dndAttributes={{ ...(dndAttributes ?? {}), ...radixProps }}
        dndListeners={dndListeners}
      >
        {row.getVisibleCells().map((cell: Cell<DriveItem, unknown>, colIndex) => (
          <DataGridTableBodyRowCell cell={cell} key={colIndex}>
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </DataGridTableBodyRowCell>
        ))}
      </DataGridTableBodyRow>
    );
  }
);

function itemLabel(item: DriveItem): string {
  return isFolderItem(item)
    ? item.name
    : item.stored_filename || item.original_filename;
}

/**
 * One Drive row. Files are draggable into folders; folders are draggable AND
 * drop targets (so a file/folder can be dropped onto a folder row - UAC E1).
 */
function DriveRow({
  row,
  draggable,
  currentDirectoryId,
  selectedIds,
  renderRowContextMenu,
}: {
  row: Row<DriveItem>;
  draggable: boolean;
  currentDirectoryId: string | null;
  selectedIds: string[];
  /** Builds the right-click / long-press context-menu items for this item. */
  renderRowContextMenu?: (item: DriveItem) => ReactNode;
}) {
  const item = row.original;
  const isFolder = isFolderItem(item);
  const dndId = isFolder
    ? `${DND_ID_GRID_FOLDER_PREFIX}${item.id}`
    : `${DND_ID_ATTACHMENT_PREFIX}${item.id}`;

  const isInSelection = selectedIds.includes(item.id);
  const batchIds = isInSelection && selectedIds.length > 1 ? selectedIds : [item.id];

  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: dndId,
    disabled: !draggable,
    data: isFolder
      ? { type: 'folder', directoryId: item.id, folderName: item.name }
      : {
          type: 'attachment',
          attachmentId: item.id,
          attachmentName: itemLabel(item),
          currentDirectoryId: currentDirectoryId ?? null,
          attachmentIds: batchIds,
        },
  });

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: dndId,
    data: { type: 'folder', directoryId: item.id },
    disabled: !isFolder,
  });

  const setRef = useCallback(
    (el: HTMLElement | null) => {
      if (draggable) setDragRef(el);
      if (isFolder) setDropRef(el);
    },
    [draggable, isFolder, setDragRef, setDropRef]
  );

  // A folder row that a drag is currently hovering = the drop target. Highlight
  // it strongly (ring + tinted bg) so it's unmistakable which folder receives
  // the drop (review item E). Non-folder rows never become drop targets.
  const dropActive = isFolder && isOver;
  const dndStyle: CSSProperties = {
    opacity: isDragging ? 0.5 : 1,
    cursor: draggable ? 'grab' : 'default',
    touchAction: draggable ? 'none' : undefined,
    ...(dropActive
      ? {
          outline: '2px solid var(--primary)',
          outlineOffset: '-2px',
          backgroundColor: 'color-mix(in oklab, var(--primary) 12%, transparent)',
        }
      : {}),
  };
  const dndAttributes = draggable
    ? (attributes as unknown as Record<string, unknown>)
    : undefined;
  const dndListeners = draggable
    ? (listeners as unknown as Record<string, unknown>)
    : undefined;

  // No context menu (or render prop) -> plain row.
  if (!renderRowContextMenu) {
    return (
      <DataGridTableBodyRow
        row={row}
        dndRef={setRef}
        dndStyle={dndStyle}
        dndAttributes={dndAttributes}
        dndListeners={dndListeners}
      >
        {row.getVisibleCells().map((cell: Cell<DriveItem, unknown>, colIndex) => (
          <DataGridTableBodyRowCell cell={cell} key={colIndex}>
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </DataGridTableBodyRowCell>
        ))}
      </DataGridTableBodyRow>
    );
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <ContextMenuRow
          row={row}
          dndRef={setRef}
          dndStyle={dndStyle}
          dndAttributes={dndAttributes}
          dndListeners={dndListeners}
        />
      </ContextMenuTrigger>
      <ContextMenuContent className="w-52">{renderRowContextMenu(item)}</ContextMenuContent>
    </ContextMenu>
  );
}

/**
 * Unified Drive list view (UAC A3): folders + files in ONE react-table, with
 * drag-move, folder-row drop targets, and the standard DataGrid resizable/fixed
 * layout. The owning panel builds the columns (incl. the search-only Location
 * column and folder "-" fallbacks).
 */
export default function DriveListView({
  draggable,
  currentDirectoryId,
  selectedIds,
  renderRowContextMenu,
}: {
  draggable: boolean;
  currentDirectoryId: string | null;
  selectedIds: string[];
  /** Builds the right-click / long-press context-menu items per row. */
  renderRowContextMenu?: (item: DriveItem) => ReactNode;
}) {
  const { props, table, isLoading } = useDataGrid();
  const pagination = table.getState().pagination;

  return (
    <div className="relative">
      <DataGridTableBase>
        <DataGridTableHead>
          {table.getHeaderGroups().map((headerGroup: HeaderGroup<DriveItem>, index) => (
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

        {(props.tableLayout?.stripped || !props.tableLayout?.rowBorder) && (
          <DataGridTableRowSpacer />
        )}

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
            table.getRowModel().rows.map((row: Row<DriveItem>) => (
              <Fragment key={row.id}>
                <DriveRow
                  row={row}
                  draggable={draggable}
                  currentDirectoryId={currentDirectoryId}
                  selectedIds={selectedIds}
                  renderRowContextMenu={renderRowContextMenu}
                />
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
