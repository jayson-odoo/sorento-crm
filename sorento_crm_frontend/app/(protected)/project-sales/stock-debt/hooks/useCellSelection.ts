'use client';

import * as React from 'react';

/**
 * Excel-style rectangle selection over a grid of VALUE cells (R7, AC-25 to AC-32).
 *
 * Screen-agnostic on purpose (A7): the board is `(rowId, columnKey) -> number | null`, so
 * the low stock report - the plan's named second case - can reuse this hook unchanged; it
 * is not lifted into `DataGrid` proper until that second caller exists (one event does not
 * need a registry).
 *
 * Selection model:
 * - A plain press-and-drag (no modifier) starts a fresh RECTANGLE from the pressed cell to
 *   wherever the pointer is currently over (AC-25). Releasing without having moved past a
 *   4px threshold is a PLAIN CLICK: `onCellClick` returns `true` and the caller opens its
 *   drill, exactly like today.
 * - Shift+click extends the rectangle from the ANCHOR (the cell a drag or a previous click
 *   started from) to the clicked cell (AC-26).
 * - Cmd/Ctrl+click TOGGLES exactly the pressed cell in or out of the current selection,
 *   leaving the rest alone (AC-26).
 * - Clicking a column header selects that whole column, every row on the page (AC-27).
 * - Escape, or `clear()` on an outside click the caller wires up, empties the selection
 *   (AC-29).
 * - Shift+Arrow on a focused cell grows the rectangle one cell in that direction (AC-32);
 *   the caller is responsible for moving DOM focus to the returned coordinate (a ref map
 *   keyed the same way the cells are, `${rowId}::${columnKey}`).
 *
 * `summary` is `null` below two selected values (AC-28: the bar only shows at >= 2), and
 * `copyText()` prints the selection in GRID order (row by row, column by column) so pasting
 * into a spreadsheet reproduces the rectangle (AC-30).
 */

export interface CellCoord {
  rowId: string;
  columnKey: string;
}

export interface CellSelectionSummary {
  count: number;
  sum: number;
  avg: number;
  min: number;
  max: number;
}

export interface UseCellSelectionArgs {
  /** The page's row ids, in display (top-to-bottom) order. */
  rowIds: string[];
  /** The page's selectable value columns, in display (left-to-right) order. */
  columnKeys: string[];
  /** `null` marks a cell as unselectable (e.g. a row with no value in that column). */
  getValue: (rowId: string, columnKey: string) => number | null;
}

export interface UseCellSelectionResult {
  isSelected: (rowId: string, columnKey: string) => boolean;
  selectedCount: number;
  summary: CellSelectionSummary | null;
  copyText: () => string;
  clear: () => void;
  onCellPointerDown: (rowId: string, columnKey: string, e: React.PointerEvent) => void;
  onCellPointerEnter: (rowId: string, columnKey: string, e: React.PointerEvent) => void;
  /** Returns `true` when the caller should proceed to open its own drill/dialog. */
  onCellClick: (rowId: string, columnKey: string, e: React.MouseEvent) => boolean;
  onColumnHeaderClick: (columnKey: string) => void;
  /** Returns the coordinate DOM focus should move to, or `null` if the key was not handled. */
  onCellKeyDown: (rowId: string, columnKey: string, e: React.KeyboardEvent) => CellCoord | null;
}

const DRAG_THRESHOLD_PX = 4;

function cellKey(rowId: string, columnKey: string): string {
  return `${rowId}::${columnKey}`;
}

function rectangle(
  rowIds: string[],
  columnKeys: string[],
  a: CellCoord,
  b: CellCoord,
): Set<string> {
  const rowStart = rowIds.indexOf(a.rowId);
  const rowEnd = rowIds.indexOf(b.rowId);
  const colStart = columnKeys.indexOf(a.columnKey);
  const colEnd = columnKeys.indexOf(b.columnKey);
  const keys = new Set<string>();
  if (rowStart === -1 || rowEnd === -1 || colStart === -1 || colEnd === -1) return keys;
  const [rLo, rHi] = rowStart <= rowEnd ? [rowStart, rowEnd] : [rowEnd, rowStart];
  const [cLo, cHi] = colStart <= colEnd ? [colStart, colEnd] : [colEnd, colStart];
  for (let r = rLo; r <= rHi; r += 1) {
    for (let c = cLo; c <= cHi; c += 1) {
      keys.add(cellKey(rowIds[r], columnKeys[c]));
    }
  }
  return keys;
}

export function useCellSelection({
  rowIds,
  columnKeys,
  getValue,
}: UseCellSelectionArgs): UseCellSelectionResult {
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const anchorRef = React.useRef<CellCoord | null>(null);
  const draggingRef = React.useRef(false);
  const draggedRef = React.useRef(false);
  const startRef = React.useRef<CellCoord | null>(null);
  const startPosRef = React.useRef<{ x: number; y: number } | null>(null);

  React.useEffect(() => {
    function finishDrag() {
      draggingRef.current = false;
    }
    function onEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') setSelected(new Set());
    }
    window.addEventListener('pointerup', finishDrag);
    window.addEventListener('keydown', onEscape);
    return () => {
      window.removeEventListener('pointerup', finishDrag);
      window.removeEventListener('keydown', onEscape);
    };
  }, []);

  const clear = React.useCallback(() => setSelected(new Set()), []);

  const isSelected = React.useCallback(
    (rowId: string, columnKey: string) => selected.has(cellKey(rowId, columnKey)),
    [selected],
  );

  const onCellPointerDown = React.useCallback(
    (rowId: string, columnKey: string, e: React.PointerEvent) => {
      if (e.button !== 0 || e.shiftKey || e.ctrlKey || e.metaKey) return;
      draggingRef.current = true;
      draggedRef.current = false;
      startRef.current = { rowId, columnKey };
      startPosRef.current = { x: e.clientX, y: e.clientY };
      anchorRef.current = { rowId, columnKey };
      setSelected(new Set([cellKey(rowId, columnKey)]));
    },
    [],
  );

  const onCellPointerEnter = React.useCallback(
    (rowId: string, columnKey: string, e: React.PointerEvent) => {
      if (!draggingRef.current || e.buttons !== 1) return;
      const start = startRef.current;
      const startPos = startPosRef.current;
      if (!start || !startPos) return;
      if (!draggedRef.current) {
        const moved =
          Math.abs(e.clientX - startPos.x) > DRAG_THRESHOLD_PX ||
          Math.abs(e.clientY - startPos.y) > DRAG_THRESHOLD_PX ||
          start.rowId !== rowId ||
          start.columnKey !== columnKey;
        if (!moved) return;
        draggedRef.current = true;
      }
      setSelected(rectangle(rowIds, columnKeys, start, { rowId, columnKey }));
    },
    [rowIds, columnKeys],
  );

  const onCellClick = React.useCallback(
    (rowId: string, columnKey: string, e: React.MouseEvent) => {
      if (draggedRef.current) {
        // The drag already set the rectangle; this click just ends the gesture.
        draggedRef.current = false;
        return false;
      }
      if (e.shiftKey && anchorRef.current) {
        setSelected(rectangle(rowIds, columnKeys, anchorRef.current, { rowId, columnKey }));
        return false;
      }
      if (e.ctrlKey || e.metaKey) {
        const key = cellKey(rowId, columnKey);
        setSelected((previous) => {
          const next = new Set(previous);
          if (next.has(key)) next.delete(key);
          else next.add(key);
          return next;
        });
        anchorRef.current = { rowId, columnKey };
        return false;
      }
      // A plain click: nothing lingers highlighted, and the caller opens its drill.
      clear();
      anchorRef.current = { rowId, columnKey };
      return true;
    },
    [rowIds, columnKeys, clear],
  );

  const onColumnHeaderClick = React.useCallback(
    (columnKey: string) => {
      setSelected(new Set(rowIds.map((rowId) => cellKey(rowId, columnKey))));
      anchorRef.current = rowIds.length ? { rowId: rowIds[0], columnKey } : null;
    },
    [rowIds],
  );

  const onCellKeyDown = React.useCallback(
    (rowId: string, columnKey: string, e: React.KeyboardEvent): CellCoord | null => {
      if (!e.shiftKey) return null;
      const rowIndex = rowIds.indexOf(rowId);
      const colIndex = columnKeys.indexOf(columnKey);
      if (rowIndex === -1 || colIndex === -1) return null;
      let nextRow = rowIndex;
      let nextCol = colIndex;
      if (e.key === 'ArrowUp') nextRow = Math.max(0, rowIndex - 1);
      else if (e.key === 'ArrowDown') nextRow = Math.min(rowIds.length - 1, rowIndex + 1);
      else if (e.key === 'ArrowLeft') nextCol = Math.max(0, colIndex - 1);
      else if (e.key === 'ArrowRight') nextCol = Math.min(columnKeys.length - 1, colIndex + 1);
      else return null;

      e.preventDefault();
      const next: CellCoord = { rowId: rowIds[nextRow], columnKey: columnKeys[nextCol] };
      const anchor = anchorRef.current ?? { rowId, columnKey };
      anchorRef.current = anchor;
      setSelected(rectangle(rowIds, columnKeys, anchor, next));
      return next;
    },
    [rowIds, columnKeys],
  );

  const values = React.useMemo(() => {
    const result: number[] = [];
    selected.forEach((key) => {
      const separator = key.indexOf('::');
      const rowId = key.slice(0, separator);
      const columnKey = key.slice(separator + 2);
      const value = getValue(rowId, columnKey);
      if (value !== null) result.push(value);
    });
    return result;
  }, [selected, getValue]);

  const summary = React.useMemo<CellSelectionSummary | null>(() => {
    if (values.length < 2) return null;
    const sum = values.reduce((total, value) => total + value, 0);
    return {
      count: values.length,
      sum,
      avg: sum / values.length,
      min: Math.min(...values),
      max: Math.max(...values),
    };
  }, [values]);

  const copyText = React.useCallback(() => {
    return rowIds
      .map((rowId) =>
        columnKeys
          .filter((columnKey) => selected.has(cellKey(rowId, columnKey)))
          .map((columnKey) => String(getValue(rowId, columnKey) ?? '')),
      )
      .filter((line) => line.length > 0)
      .map((line) => line.join('\t'))
      .join('\n');
  }, [rowIds, columnKeys, selected, getValue]);

  return {
    isSelected,
    selectedCount: selected.size,
    summary,
    copyText,
    clear,
    onCellPointerDown,
    onCellPointerEnter,
    onCellClick,
    onColumnHeaderClick,
    onCellKeyDown,
  };
}
