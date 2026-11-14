'use client';

/**
 * SPEC-SHEET-PARITY-B2 v3 (AC-C5.1): drag a selected table's row and column edges on the canvas.
 *
 * Thin hit strips laid over the table in the same overlay the in-place cell editor uses (screen px,
 * same origin and scale as `KonvaTagLayer`), never inside the Transformer. A row's bottom edge
 * (inner boundary or the table's bottom) sets that row's `height_mm`, a minimum the row keeps when
 * empty; an inner column boundary moves width between the two columns beside it, so the table keeps
 * its width. While dragging only a guide line moves; the one write happens on release, so a drag is
 * one Undo step (and one autosave on a spec sheet page).
 */

import { useState } from 'react';

import { tableLayout, tableMeasure } from '@/lib/dealer-kit/table-layout';
import type { TableLayerProps, TagLayer } from '@/lib/dealer-kit/tag-template-types';

export const TABLE_ROW_MIN_MM = 2;
export const TABLE_COLUMN_MIN_MM = 5;
/** Hit strip thickness, screen px. */
const STRIP_PX = 8;

const tenth = (value: number) => Math.round(value * 10) / 10;

type Drag = { kind: 'row' | 'col'; index: number; start: number; delta_mm: number };

export function TableEdgeHandles({
  layer,
  drawn,
  scale,
  originX,
  originY,
  onChange,
}: {
  /** The selected table layer (its stored props are what a drag writes). */
  layer: TagLayer & { props: TableLayerProps };
  /** The table as the canvas draws it (fields resolved or named), for where the edges are. */
  drawn: TableLayerProps;
  /** mm -> screen px, with the zoom. */
  scale: number;
  /** Screen offset of canvas mm (0, 0), px. */
  originX: number;
  originY: number;
  onChange: (next: TableLayerProps) => void;
}) {
  const [drag, setDrag] = useState<Drag | null>(null);
  const laid = tableLayout(drawn, layer.width_mm, tableMeasure(drawn));
  const rows = laid.rowHeights_mm;
  const cols = laid.columnWidths_mm;
  const rowEnds = rows.map((_, i) => rows.slice(0, i + 1).reduce((a, b) => a + b, 0));
  const colEnds = cols.map((_, i) => cols.slice(0, i + 1).reduce((a, b) => a + b, 0));
  const left = originX + layer.x_mm * scale;
  const top = originY + layer.y_mm * scale;

  /** The drag clamped to the minimums, in drawn mm. */
  const clamped = (d: Drag): number => {
    if (d.kind === 'row') return Math.max(TABLE_ROW_MIN_MM - rows[d.index], d.delta_mm);
    const a = cols[d.index];
    const b = cols[d.index + 1];
    return Math.min(b - TABLE_COLUMN_MIN_MM, Math.max(TABLE_COLUMN_MIN_MM - a, d.delta_mm));
  };

  const commit = (d: Drag) => {
    const delta = clamped(d);
    if (Math.abs(delta) < 0.05) return;
    const { props } = layer;
    if (d.kind === 'row') {
      const height = tenth(Math.max(TABLE_ROW_MIN_MM, rows[d.index] + delta));
      onChange({ ...props, rows: props.rows.map((r, i) => (i === d.index ? { ...r, height_mm: height } : r)) });
      return;
    }
    // Stored widths are relative (the layout scales them to the layer width): convert the drag.
    const total = props.columns.reduce((sum, c) => sum + c.width_mm, 0);
    const k = total > 0 ? layer.width_mm / total : 1;
    const pair = props.columns[d.index].width_mm + props.columns[d.index + 1].width_mm;
    const a = tenth(props.columns[d.index].width_mm + delta / k);
    onChange({
      ...props,
      columns: props.columns.map((c, i) =>
        i === d.index ? { ...c, width_mm: a } : i === d.index + 1 ? { ...c, width_mm: tenth(pair - a) } : c,
      ),
    });
  };

  const handlers = (kind: 'row' | 'col', index: number) => ({
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      setDrag({ kind, index, start: kind === 'row' ? e.clientY : e.clientX, delta_mm: 0 });
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => {
      if (!drag || drag.kind !== kind || drag.index !== index) return;
      const at = kind === 'row' ? e.clientY : e.clientX;
      setDrag({ ...drag, delta_mm: (at - drag.start) / scale });
    },
    onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => {
      if (!drag || drag.kind !== kind || drag.index !== index) return;
      const at = kind === 'row' ? e.clientY : e.clientX;
      setDrag(null);
      commit({ ...drag, delta_mm: (at - drag.start) / scale });
    },
    onPointerCancel: () => setDrag(null),
  });

  const width = layer.width_mm * scale;
  const height = laid.height_mm * scale;
  const guide = drag ? clamped(drag) : 0;

  return (
    <>
      {rows.map((_, i) => (
        <div
          key={`row-${i}`}
          data-testid={`table-row-edge-${i}`}
          className="absolute z-20 cursor-row-resize touch-none"
          style={{ left, top: top + rowEnds[i] * scale - STRIP_PX / 2, width, height: STRIP_PX }}
          {...handlers('row', i)}
        />
      ))}
      {cols.slice(0, -1).map((_, j) => (
        <div
          key={`col-${j}`}
          data-testid={`table-col-edge-${j}`}
          className="absolute z-20 cursor-col-resize touch-none"
          style={{ left: left + colEnds[j] * scale - STRIP_PX / 2, top, width: STRIP_PX, height }}
          {...handlers('col', j)}
        />
      ))}
      {drag && (
        <div
          aria-hidden
          className="pointer-events-none absolute z-20 border-primary"
          style={
            drag.kind === 'row'
              ? { left, top: top + (rowEnds[drag.index] + guide) * scale, width, borderTopWidth: 1, borderStyle: 'dashed' }
              : { left: left + (colEnds[drag.index] + guide) * scale, top, height, borderLeftWidth: 1, borderStyle: 'dashed' }
          }
        />
      )}
    </>
  );
}
