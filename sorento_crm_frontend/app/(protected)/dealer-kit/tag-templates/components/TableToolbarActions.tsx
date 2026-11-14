'use client';

/**
 * SPEC-SHEET-PARITY-B2 v3 (AC-C1.4, AC-C4.1): a selected table's actions in the toolbar row, the
 * same in the template designer and on a spec sheet page: Add row (below the picked cell), Add
 * column (to its right), Merge right, Header row (on / off) and Insert field.
 * Every change goes through `onChange` with the whole new props, so it is one undo step.
 */

import { BetweenHorizontalEnd, BetweenVerticalEnd, Braces, PanelTop, TableCellsMerge } from 'lucide-react';

import { cellAnchor, insertColumn, insertRow, mergeCells } from '@/lib/dealer-kit/table-layout';
import type { TableLayerProps } from '@/lib/dealer-kit/tag-template-types';

import { ToolbarButton } from './CanvasToolbar';

export function TableToolbarActions({
  props,
  cell,
  onChange,
  onInsertField,
}: {
  props: TableLayerProps;
  /** The picked cell; the first one when none is picked yet. */
  cell: { row: number; col: number } | null;
  onChange: (next: TableLayerProps) => void;
  onInsertField?: () => void;
}) {
  const at = () => {
    const { row, col } = cellAnchor(props, cell?.row ?? 0, cell?.col ?? 0);
    const anchor = props.cells[row]?.[col];
    return { row, col, rowSpan: Math.max(1, anchor?.rowSpan ?? 1), colSpan: Math.max(1, anchor?.colSpan ?? 1) };
  };
  const now = at();
  const canMerge = now.col + now.colSpan < props.columns.length;
  // Icon buttons (the toolbar's own), named for screen readers and tooltips: the row keeps room
  // for zoom, full screen and the save state at 1280 (v3 browser F2).
  return (
    <div role="group" aria-label="Table" className="flex shrink-0 items-center gap-1">
      <ToolbarButton
        icon={BetweenHorizontalEnd}
        label="Add row"
        onClick={() => {
          const { row, rowSpan } = at();
          onChange(insertRow(props, row + rowSpan));
        }}
      />
      <ToolbarButton
        icon={BetweenVerticalEnd}
        label="Add column"
        onClick={() => {
          const { col, colSpan } = at();
          onChange(insertColumn(props, col + colSpan));
        }}
      />
      <ToolbarButton
        icon={TableCellsMerge}
        label="Merge right"
        disabled={!canMerge}
        onClick={() => {
          const { row, col, rowSpan, colSpan } = at();
          if (col + colSpan < props.columns.length) {
            onChange(mergeCells(props, row, col, row + rowSpan - 1, col + colSpan));
          }
        }}
      />
      <ToolbarButton
        icon={PanelTop}
        label="Header row"
        active={Boolean(props.headerRow)}
        onClick={() => onChange({ ...props, headerRow: !props.headerRow })}
      />
      {onInsertField && <ToolbarButton icon={Braces} label="Insert field" onClick={onInsertField} />}
    </div>
  );
}
