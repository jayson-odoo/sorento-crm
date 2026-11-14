'use client';

/**
 * SPEC-SHEET-PARITY-B2 v3 (AC-C1.4, AC-C4.1): a selected table's actions in the toolbar row, the
 * same in the template designer and on a spec sheet page: + Row (below the picked cell), + Column
 * (to its right), Merge (with the cell to its right), Header row (on / off) and Insert field.
 * Every change goes through `onChange` with the whole new props, so it is one undo step.
 */

import { Button } from '@/components/ui/button';
import { insertColumn, insertRow, mergeCells } from '@/lib/dealer-kit/table-layout';
import type { TableLayerProps } from '@/lib/dealer-kit/tag-template-types';

export function TableToolbarActions({
  props,
  cell,
  onChange,
  onInsertField,
}: {
  props: TableLayerProps;
  /** The picked cell (or how to read it when clicked); the first one when none is picked yet. */
  cell: { row: number; col: number } | null | (() => { row: number; col: number } | null);
  onChange: (next: TableLayerProps) => void;
  onInsertField?: () => void;
}) {
  const at = () => {
    const picked = typeof cell === 'function' ? cell() : cell;
    const row = Math.min(picked?.row ?? 0, props.rows.length - 1);
    const col = Math.min(picked?.col ?? 0, props.columns.length - 1);
    const anchor = props.cells[row]?.[col];
    return { row, col, rowSpan: Math.max(1, anchor?.rowSpan ?? 1), colSpan: Math.max(1, anchor?.colSpan ?? 1) };
  };
  const now = at();
  const canMerge = now.col + now.colSpan < props.columns.length || typeof cell === 'function';
  const button = 'h-8 shrink-0 px-2 text-xs';
  return (
    <div role="group" aria-label="Table" className="flex shrink-0 items-center gap-1">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={button}
        onClick={() => {
          const { row, rowSpan } = at();
          onChange(insertRow(props, row + rowSpan));
        }}
      >
        + Row
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={button}
        onClick={() => {
          const { col, colSpan } = at();
          onChange(insertColumn(props, col + colSpan));
        }}
      >
        + Column
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={button}
        disabled={!canMerge}
        onClick={() => {
          const { row, col, rowSpan, colSpan } = at();
          if (col + colSpan < props.columns.length) {
            onChange(mergeCells(props, row, col, row + rowSpan - 1, col + colSpan));
          }
        }}
      >
        Merge
      </Button>
      <Button
        type="button"
        variant={props.headerRow ? 'primary' : 'ghost'}
        size="sm"
        className={button}
        aria-pressed={Boolean(props.headerRow)}
        onClick={() => onChange({ ...props, headerRow: !props.headerRow })}
      >
        Header row
      </Button>
      {onInsertField && (
        <Button type="button" variant="ghost" size="sm" className={button} onClick={onInsertField}>
          Insert field
        </Button>
      )}
    </div>
  );
}
