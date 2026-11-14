/**
 * SPEC-SHEET-DESIGNER-PARITY B4: a border shared by two cells is drawn once. `tableLayout` resolves
 * every grid edge to one unit segment, which the canvas and the print page both draw.
 */
import { describe, expect, it } from 'vitest';

import { defaultTableProps, mergeCells, tableLayout } from './table-layout';
import type { TableLayerProps } from './tag-template-types';

const measure = () => 0;
const side = (width_mm: number, color = '#000000') => ({ color, width_mm });

function bordered(rows: number, cols: number, width = 0.3): TableLayerProps {
  const props = defaultTableProps(rows, cols, cols * 20);
  props.cells = props.cells.map((row) =>
    row.map((cell) => ({ ...cell, border: { top: side(width), right: side(width), bottom: side(width), left: side(width) } })),
  );
  return props;
}

const horizontal = (edges: { y1_mm: number; y2_mm: number }[]) => edges.filter((e) => e.y1_mm === e.y2_mm);
const vertical = (edges: { x1_mm: number; x2_mm: number }[]) => edges.filter((e) => e.x1_mm === e.x2_mm);

describe('tableLayout edges', () => {
  it('a 2x2 table with every border set has 6 horizontal and 6 vertical unit segments, none twice', () => {
    const { edges } = tableLayout(bordered(2, 2), 40, measure);
    expect(horizontal(edges)).toHaveLength(6);
    expect(vertical(edges)).toHaveLength(6);
    const keys = edges.map((e) => [e.x1_mm, e.y1_mm, e.x2_mm, e.y2_mm].join(','));
    expect(new Set(keys).size).toBe(keys.length);
    for (const e of edges) expect(e.width_mm).toBe(0.3);
  });

  it('an inner edge uses the upper / left cell when it has a border, else the other cell', () => {
    const props = bordered(2, 1);
    props.cells[0][0].border = { ...props.cells[0][0].border, bottom: side(0.5, '#ff0000') };
    props.cells[1][0].border = { ...props.cells[1][0].border, top: side(0.9, '#00ff00') };
    let inner = horizontal(tableLayout(props, 20, measure).edges).filter((e) => e.y1_mm > 0 && e.y1_mm < 12);
    expect(inner).toHaveLength(1);
    expect(inner[0]).toMatchObject({ color: '#ff0000', width_mm: 0.5 });

    props.cells[0][0].border = { ...props.cells[0][0].border, bottom: undefined };
    inner = horizontal(tableLayout(props, 20, measure).edges).filter((e) => e.y1_mm > 0 && e.y1_mm < 12);
    expect(inner[0]).toMatchObject({ color: '#00ff00', width_mm: 0.9 });
  });

  it('width 0 is no segment, and an outer edge uses its own cell', () => {
    const props = bordered(1, 1);
    props.cells[0][0].border = { top: side(0.4, '#ff0000'), right: side(0), bottom: side(0.2), left: side(0.2) };
    const { edges } = tableLayout(props, 20, measure);
    expect(edges).toHaveLength(3);
    expect(edges.find((e) => e.y1_mm === 0 && e.y2_mm === 0)).toMatchObject({ color: '#ff0000', width_mm: 0.4 });
  });

  it('a merge removes the inner segments', () => {
    const merged = mergeCells(bordered(2, 2), 0, 0, 1, 1);
    const { edges } = tableLayout(merged, 40, measure);
    // Only the outline: 2 unit segments per side.
    expect(horizontal(edges)).toHaveLength(4);
    expect(vertical(edges)).toHaveLength(4);
  });
});
