'use client';

import { useSyncExternalStore } from 'react';
import type * as React from 'react';
import type { Row, RowSelectionState, Table } from '@tanstack/react-table';

/**
 * GRID-DRAG-SELECT: Shift+click, drag and Shift+Arrow ranges for a row's selection checkbox.
 *
 * Spread `rangeSelectProps(table, row)` onto the row's checkbox. The box keeps its own plain
 * click; these props add:
 *
 * - Shift+click: every row between the last clicked box (the anchor) and this one takes the
 *   anchor's state, like Gmail.
 * - Drag: press a box and move over other rows; the run takes the opposite of the pressed box's
 *   state, and rows the pointer leaves again get their earlier state back. Only a press ON A BOX
 *   starts it, so a press on any other cell is still a text selection for copy. A finger on a
 *   list scrolls it, so touch starts the same drag only after a 500 ms press-and-hold; a move of
 *   more than 8px before that is a scroll.
 * - ArrowUp / ArrowDown move focus between row boxes; with Shift the next row takes the
 *   anchor's state.
 *
 * Rows are read from `table.getRowModel()`, so a range is the rows as shown (this page, this
 * sort). Rows that cannot be selected are skipped. Every gesture writes the selection in ONE
 * update, because some lists pass `onRowSelectionChange` a setter that is not updater-safe.
 */

const ROW_ID_ATTR = 'data-range-row-id';

/** Anchor per table. The react-table instance is stable for a list's lifetime. */
const anchors = new WeakMap<Table<unknown>, string>();

type Drag = {
  table: Table<unknown>;
  tableEl: Element | null;
  startId: string;
  value: boolean;
  before: RowSelectionState;
  lastId: string;
  moved: boolean;
  /** Touch press: the drag only goes live once the hold timer fires. */
  touch: boolean;
  live: boolean;
  timer: ReturnType<typeof setTimeout> | null;
  x: number;
  y: number;
};

const TOUCH_HOLD_MS = 500;
const TOUCH_SLOP_PX = 8;

let drag: Drag | null = null;

/**
 * The table whose checkbox drag is MOVING right now (a press that has not moved yet is still
 * a plain click). That table's list toolbar reads it to keep its layout still: its
 * "N selected" strip and its idle controls differ in height, and a jump mid-drag slid the
 * rows under a still pointer.
 */
let movingTable: Table<unknown> | null = null;
const movingListeners = new Set<() => void>();

function setMovingTable(table: Table<unknown> | null) {
  if (movingTable === table) return;
  movingTable = table;
  movingListeners.forEach((listener) => listener());
}

function subscribeMoving(listener: () => void) {
  movingListeners.add(listener);
  return () => {
    movingListeners.delete(listener);
  };
}

export function useRangeDragMoving<TData>(table: Table<TData>): boolean {
  return useSyncExternalStore(
    subscribeMoving,
    () => movingTable === (table as Table<unknown>),
    () => false,
  );
}

/**
 * Eats the one click the browser sends after a drag is released, wherever it lands: on the
 * first box it would toggle that box again, on a row it would open the record. Capture phase on
 * window runs before React's own listeners.
 */
function swallowNextClick() {
  const swallow = (event: MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };
  const stop = () => {
    window.removeEventListener('click', swallow, { capture: true });
    window.removeEventListener('pointerdown', stop, { capture: true });
  };
  window.addEventListener('click', swallow, { capture: true, once: true });
  // The click (if any) follows pointerup in the same task; never let the listener outlive it.
  // A new press means no click is coming, so it ends the listener too.
  window.addEventListener('pointerdown', stop, { capture: true, once: true });
  setTimeout(stop, 0);
}

function rowsOf(table: Table<unknown>) {
  return table.getRowModel().rows as Row<unknown>[];
}

/** Selection with every selectable row between `fromId` and `toId` set to `value`. */
function withRange(
  table: Table<unknown>,
  base: RowSelectionState,
  fromId: string,
  toId: string,
  value: boolean,
): RowSelectionState {
  const rows = rowsOf(table);
  const a = rows.findIndex((r) => r.id === fromId);
  const b = rows.findIndex((r) => r.id === toId);
  if (a < 0 || b < 0) return base;
  const next = { ...base };
  for (let i = Math.min(a, b); i <= Math.max(a, b); i++) {
    const row = rows[i];
    if (!row.getCanSelect()) continue;
    if (value) next[row.id] = true;
    else delete next[row.id];
  }
  return next;
}

/** `<html>`'s own inline user-select before a drag turned it off, put back after. */
let savedUserSelect: [string, string] | null = null;

function setTextSelectable(on: boolean) {
  const style = document.documentElement.style;
  if (!on) {
    savedUserSelect ??= [style.userSelect, style.getPropertyValue('-webkit-user-select')];
    style.userSelect = 'none';
    style.setProperty('-webkit-user-select', 'none');
  } else if (savedUserSelect) {
    style.userSelect = savedUserSelect[0];
    style.setProperty('-webkit-user-select', savedUserSelect[1]);
    savedUserSelect = null;
  }
}

function rowIdAt(target: EventTarget | null, tableEl: Element | null): string | null {
  const tr = (target as Element | null)?.closest?.('tr');
  if (!tr || (tableEl && !tableEl.contains(tr))) return null;
  return tr.querySelector(`[${ROW_ID_ATTR}]`)?.getAttribute(ROW_ID_ATTR) ?? null;
}

/**
 * Native, non-passive listeners attached once, before any touch starts: Chrome and iOS ignore
 * preventDefault from a touchmove listener added after touchstart, and React's onTouchMove is
 * passive. They act only while a held touch drag is live (scroll lock) or a touch press is
 * down (Android long-press menu).
 */
let touchGuardsOn = false;

function ensureTouchGuards() {
  if (touchGuardsOn || typeof document === 'undefined') return;
  touchGuardsOn = true;
  document.addEventListener(
    'touchmove',
    (event) => {
      if (drag?.touch && drag.live && event.cancelable) event.preventDefault();
    },
    { passive: false },
  );
  document.addEventListener('contextmenu', (event) => {
    if (drag?.touch) event.preventDefault();
  });
}

function onDragMove(event: PointerEvent) {
  if (!drag) return;
  if (drag.touch) {
    if (!drag.live) {
      // Moved off the press point before the hold fired: that is a scroll.
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > TOUCH_SLOP_PX) endDrag();
      return;
    }
    // The finger's pointer is captured by the pressed box, so the row comes from the point.
    const under = document.elementFromPoint?.(event.clientX, event.clientY) ?? event.target;
    moveDragTo(rowIdAt(under, drag.tableEl));
    return;
  }
  // The release happened somewhere this drag never heard about (another window, a context
  // menu): a move with the button up ends it, never ticks rows on hover.
  if (!(event.buttons & 1)) {
    endDrag();
    return;
  }
  moveDragTo(rowIdAt(event.target, drag.tableEl));
}

function moveDragTo(id: string | null) {
  if (!drag || id === null || id === drag.lastId) return;
  if (!drag.moved) {
    drag.moved = true;
    setMovingTable(drag.table);
    setTextSelectable(false);
    window.getSelection?.()?.removeAllRanges();
  }
  drag.lastId = id;
  const { table, before, startId, value } = drag;
  table.setRowSelection(withRange(table, before, startId, id, value));
}

function endDrag() {
  if (!drag) return;
  if (drag.timer) clearTimeout(drag.timer);
  if (drag.moved) {
    anchors.set(drag.table, drag.lastId);
    setTextSelectable(true);
    swallowNextClick();
  }
  drag = null;
  setMovingTable(null);
  window.removeEventListener('pointermove', onDragMove);
  window.removeEventListener('pointerup', endDrag, { capture: true });
  window.removeEventListener('pointercancel', endDrag, { capture: true });
  window.removeEventListener('blur', endDrag);
}

function focusRowBox(tableEl: Element | null, id: string) {
  const scope = tableEl ?? document;
  for (const el of scope.querySelectorAll<HTMLElement>(`[${ROW_ID_ATTR}]`)) {
    if (el.getAttribute(ROW_ID_ATTR) === id) {
      el.focus();
      return;
    }
  }
}

export function rangeSelectProps<TData>(tableArg: Table<TData>, rowArg: Row<TData>) {
  const table = tableArg as Table<unknown>;
  const row = rowArg as Row<unknown>;
  ensureTouchGuards();

  return {
    [ROW_ID_ATTR]: row.id,

    onClick: (event: React.MouseEvent) => {
      const anchorId = anchors.get(table);
      const anchor = anchorId ? rowsOf(table).find((r) => r.id === anchorId) : undefined;
      anchors.set(table, row.id);
      // No range to make (or Shift+click on the anchor itself): the box toggles itself.
      if (!event.shiftKey || !anchor || anchor.id === row.id) return;
      // preventDefault stops the box's own toggle; the range sets this row too.
      event.preventDefault();
      table.setRowSelection((old) => withRange(table, old, anchor.id, row.id, anchor.getIsSelected()));
    },

    onPointerDown: (event: React.PointerEvent) => {
      const touch = event.pointerType === 'touch';
      if (event.button !== 0 || event.shiftKey) return;
      if (!row.getCanSelect()) return;
      endDrag();
      drag = {
        table,
        tableEl: (event.currentTarget as Element).closest('table'),
        startId: row.id,
        value: !row.getIsSelected(),
        before: { ...table.getState().rowSelection },
        lastId: row.id,
        moved: false,
        touch,
        live: !touch,
        timer: null,
        x: event.clientX,
        y: event.clientY,
      };
      if (touch) {
        const started = drag;
        started.timer = setTimeout(() => {
          started.timer = null;
          if (drag === started) started.live = true;
        }, TOUCH_HOLD_MS);
      }
      window.addEventListener('pointermove', onDragMove);
      // Capture: a handler that stops pointerup from bubbling must not strand the drag.
      window.addEventListener('pointerup', endDrag, { capture: true });
      window.addEventListener('pointercancel', endDrag, { capture: true });
      window.addEventListener('blur', endDrag);
    },

    onKeyDown: (event: React.KeyboardEvent) => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      const rows = rowsOf(table);
      const here = rows.findIndex((r) => r.id === row.id);
      // The next row whose box can take focus; a disabled box cannot, so it is stepped over.
      // Past either end there is none and focus stays where it is.
      const step = event.key === 'ArrowDown' ? 1 : -1;
      let at = here + step;
      while (rows[at] && !rows[at].getCanSelect()) at += step;
      const next = rows[at];
      const tableEl = (event.currentTarget as Element).closest('table');
      if (!next) return;
      if (event.shiftKey) {
        const anchorId = anchors.get(table);
        const anchor = anchorId ? rows.find((r) => r.id === anchorId) : undefined;
        if (anchor) {
          const value = anchor.getIsSelected();
          table.setRowSelection((old) => withRange(table, old, next.id, next.id, value));
        } else {
          // Nothing clicked yet: start a ticked run here.
          anchors.set(table, row.id);
          table.setRowSelection((old) => withRange(table, old, row.id, next.id, true));
        }
      }
      focusRowBox(tableEl, next.id);
    },
  };
}
