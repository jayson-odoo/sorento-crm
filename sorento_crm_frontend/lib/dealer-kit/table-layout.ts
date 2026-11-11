/**
 * SPEC-SHEET-DESIGNER-PARITY B4: the table element's ONE layout module. The designer canvas and the
 * print page both lay a table out here, so a row is the same height in both: the set height, or the
 * measured text plus padding when that is taller. Everything is in millimetres inside the layer.
 */
import type { TableBorderSide, TableCell, TableLayerProps } from './tag-template-types';

export const TABLE_MAX_LINES = 50;
export const DEFAULT_TABLE_FONT_PT = 10;
export const DEFAULT_TABLE_PADDING_MM = 1;
export const DEFAULT_TABLE_ROW_MM = 6;
const PT_TO_MM = 0.3528;
const TEXT_LINE_HEIGHT = 1.2;
/** Average advance of a character, in em: generous, so the estimate errs towards a taller row. */
const EM_PER_CHAR = 0.55;

const SIDES = ['top', 'right', 'bottom', 'left'] as const;
export type TableSide = (typeof SIDES)[number];

export const DEFAULT_TABLE_BORDER: TableBorderSide = { color: '#000000', width_mm: 0.2 };

function blankCell(like?: TableCell): TableCell {
  return {
    text: '',
    padding_mm: like?.padding_mm ?? DEFAULT_TABLE_PADDING_MM,
    ...(like?.fill ? { fill: like.fill } : {}),
    border: like?.border
      ? { ...like.border }
      : { top: DEFAULT_TABLE_BORDER, right: DEFAULT_TABLE_BORDER, bottom: DEFAULT_TABLE_BORDER, left: DEFAULT_TABLE_BORDER },
  };
}

export function defaultTableProps(rows: number, cols: number, width_mm: number): TableLayerProps {
  return {
    kind: 'table',
    columns: Array.from({ length: cols }, () => ({ width_mm: width_mm / cols })),
    rows: Array.from({ length: rows }, () => ({ height_mm: DEFAULT_TABLE_ROW_MM })),
    cells: Array.from({ length: rows }, () => Array.from({ length: cols }, () => blankCell())),
    fontFamily: 'DM Sans',
    fontSize: DEFAULT_TABLE_FONT_PT,
    color: '#000000',
    align: 'left',
    verticalAlign: 'middle',
  };
}

/** A text height estimate (mm) for `text` wrapped to `width_mm`; the one measure canvas and print share. */
export function estimateTableTextHeight(text: string, width_mm: number, fontSize_pt: number): number {
  if (!text) return 0;
  const perLine = Math.max(1, Math.floor(width_mm / (EM_PER_CHAR * fontSize_pt * PT_TO_MM)));
  const lines = text
    .split('\n')
    .reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / perLine)), 0);
  return lines * fontSize_pt * PT_TO_MM * TEXT_LINE_HEIGHT;
}

export type TableMeasure = (text: string, width_mm: number) => number;

export function tableMeasure(props: Pick<TableLayerProps, 'fontSize'>): TableMeasure {
  const size = props.fontSize ?? DEFAULT_TABLE_FONT_PT;
  return (text, width) => estimateTableTextHeight(text, width, size);
}

export interface LaidOutCell {
  row: number;
  col: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  text: string;
  cell: TableCell;
}

/** One unit of a grid line, drawn once however many cells share it. */
export interface TableEdge {
  orientation: 'h' | 'v';
  /** The grid line (0..rows for 'h', 0..columns for 'v') and the cell index along it. */
  line: number;
  index: number;
  x1_mm: number;
  y1_mm: number;
  x2_mm: number;
  y2_mm: number;
  color: string;
  width_mm: number;
}

export interface TableLayout {
  cells: LaidOutCell[];
  /** Borders, resolved once per grid edge (see `resolveEdges`). */
  edges: TableEdge[];
  rowHeights_mm: number[];
  columnWidths_mm: number[];
  height_mm: number;
}

const span = (value: number | undefined) => Math.max(1, value ?? 1);

/** Which cells a merged anchor covers (not the anchor itself), as "r:c". */
function coveredSet(props: TableLayerProps): Set<string> {
  const covered = new Set<string>();
  props.cells.forEach((row, r) =>
    row.forEach((cell, c) => {
      const rs = Math.min(span(cell.rowSpan), props.rows.length - r);
      const cs = Math.min(span(cell.colSpan), props.columns.length - c);
      for (let i = 0; i < rs; i += 1) {
        for (let j = 0; j < cs; j += 1) if (i || j) covered.add(`${r + i}:${c + j}`);
      }
    }),
  );
  return covered;
}

export function tableLayout(props: TableLayerProps, layerWidth_mm: number, measure: TableMeasure): TableLayout {
  const total = props.columns.reduce((sum, col) => sum + col.width_mm, 0);
  const scale = total > 0 ? layerWidth_mm / total : 1;
  const columnWidths = props.columns.map((col) => col.width_mm * scale);
  const covered = coveredSet(props);
  const rowHeights = props.rows.map((row) => row.height_mm);

  const anchors: { r: number; c: number; cell: TableCell; rs: number; cs: number; width: number; need: number }[] = [];
  props.cells.forEach((row, r) =>
    row.forEach((cell, c) => {
      if (covered.has(`${r}:${c}`)) return;
      const rs = Math.min(span(cell.rowSpan), props.rows.length - r);
      const cs = Math.min(span(cell.colSpan), props.columns.length - c);
      const width = columnWidths.slice(c, c + cs).reduce((a, b) => a + b, 0);
      const pad = cell.padding_mm ?? DEFAULT_TABLE_PADDING_MM;
      const need = cell.text ? measure(cell.text, Math.max(0, width - 2 * pad)) + 2 * pad : 0;
      anchors.push({ r, c, cell, rs, cs, width, need });
    }),
  );
  // A single-row cell sets its row's height; a spanning one only tops up its LAST row.
  for (const a of anchors) if (a.rs === 1) rowHeights[a.r] = Math.max(rowHeights[a.r], a.need);
  for (const a of anchors) {
    if (a.rs === 1) continue;
    const have = rowHeights.slice(a.r, a.r + a.rs).reduce((x, y) => x + y, 0);
    if (a.need > have) rowHeights[a.r + a.rs - 1] += a.need - have;
  }

  const xs = columnWidths.map((_, i) => columnWidths.slice(0, i).reduce((a, b) => a + b, 0));
  const ys = rowHeights.map((_, i) => rowHeights.slice(0, i).reduce((a, b) => a + b, 0));
  const totalWidth = columnWidths.reduce((a, b) => a + b, 0);
  const totalHeight = rowHeights.reduce((a, b) => a + b, 0);
  return {
    edges: resolveEdges(props, [...xs, totalWidth], [...ys, totalHeight]),
    cells: anchors.map((a) => ({
      row: a.r,
      col: a.c,
      x_mm: xs[a.c],
      y_mm: ys[a.r],
      width_mm: a.width,
      height_mm: rowHeights.slice(a.r, a.r + a.rs).reduce((x, y) => x + y, 0),
      text: a.cell.text,
      cell: a.cell,
    })),
    rowHeights_mm: rowHeights,
    columnWidths_mm: columnWidths,
    height_mm: ys.length ? ys[ys.length - 1] + rowHeights[rowHeights.length - 1] : 0,
  };
}

/** The anchor cell that owns every grid cell (itself, or the merge that covers it). */
function ownerGrid(props: TableLayerProps): { r: number; c: number }[][] {
  const grid = props.rows.map((_, r) => props.columns.map((__, c) => ({ r, c })));
  const covered = coveredSet(props);
  props.cells.forEach((row, r) =>
    row.forEach((cell, c) => {
      if (covered.has(`${r}:${c}`)) return;
      const rs = Math.min(span(cell.rowSpan), props.rows.length - r);
      const cs = Math.min(span(cell.colSpan), props.columns.length - c);
      for (let i = 0; i < rs; i += 1) for (let j = 0; j < cs; j += 1) grid[r + i][c + j] = { r, c };
    }),
  );
  return grid;
}

/**
 * Every grid edge once. An inner edge takes the cell above's bottom (or the left cell's right) when
 * that cell names one, else the other cell's top (left); an outer edge takes its own cell's side;
 * width 0 is no line; nothing is drawn inside a merge. Canvas and print both draw these segments.
 */
function resolveEdges(props: TableLayerProps, xs: number[], ys: number[]): TableEdge[] {
  const owners = ownerGrid(props);
  const rows = props.rows.length;
  const cols = props.columns.length;
  const border = (o: { r: number; c: number } | null, side: TableSide) => (o ? props.cells[o.r][o.c].border?.[side] : undefined);
  const pick = (first?: TableBorderSide, second?: TableBorderSide) => first ?? second;
  const edges: TableEdge[] = [];
  for (let line = 0; line <= rows; line += 1) {
    for (let col = 0; col < cols; col += 1) {
      const above = line > 0 ? owners[line - 1][col] : null;
      const below = line < rows ? owners[line][col] : null;
      if (above && below && above.r === below.r && above.c === below.c) continue;
      const spec = pick(border(above, 'bottom'), border(below, 'top'));
      if (spec && spec.width_mm > 0) {
        edges.push({ orientation: 'h', line, index: col, x1_mm: xs[col], y1_mm: ys[line], x2_mm: xs[col + 1], y2_mm: ys[line], color: spec.color, width_mm: spec.width_mm });
      }
    }
  }
  for (let line = 0; line <= cols; line += 1) {
    for (let row = 0; row < rows; row += 1) {
      const left = line > 0 ? owners[row][line - 1] : null;
      const right = line < cols ? owners[row][line] : null;
      if (left && right && left.r === right.r && left.c === right.c) continue;
      const spec = pick(border(left, 'right'), border(right, 'left'));
      if (spec && spec.width_mm > 0) {
        edges.push({ orientation: 'v', line, index: row, x1_mm: xs[line], y1_mm: ys[row], x2_mm: xs[line], y2_mm: ys[row + 1], color: spec.color, width_mm: spec.width_mm });
      }
    }
  }
  return edges;
}

/** The laid-out cell under a point inside the layer (mm), or null. */
export function cellAt(layout: TableLayout, x_mm: number, y_mm: number): { row: number; col: number } | null {
  const hit = layout.cells.find(
    (c) => x_mm >= c.x_mm && x_mm < c.x_mm + c.width_mm && y_mm >= c.y_mm && y_mm < c.y_mm + c.height_mm,
  );
  return hit ? { row: hit.row, col: hit.col } : null;
}

// ---------------------------------------------------------------------------
// Row and column edits (pure: they return new props)
// ---------------------------------------------------------------------------

/** Insert a blank row so it sits at index `at`. A merge that spans the gap grows by one row. */
export function insertRow(props: TableLayerProps, at: number): TableLayerProps {
  if (props.rows.length >= TABLE_MAX_LINES) return props;
  const index = Math.max(0, Math.min(at, props.rows.length));
  const ref = props.cells[Math.min(index, props.cells.length - 1)];
  const cells = props.cells.map((row, r) =>
    row.map((cell) => (r < index && r + span(cell.rowSpan) > index ? { ...cell, rowSpan: span(cell.rowSpan) + 1 } : cell)),
  );
  cells.splice(index, 0, ref.map((cell) => blankCell(cell)));
  const rows = [...props.rows];
  rows.splice(index, 0, { height_mm: props.rows[Math.min(index, props.rows.length - 1)].height_mm });
  return { ...props, rows, cells };
}

export function insertColumn(props: TableLayerProps, at: number): TableLayerProps {
  if (props.columns.length >= TABLE_MAX_LINES) return props;
  const index = Math.max(0, Math.min(at, props.columns.length));
  const refCol = Math.min(index, props.columns.length - 1);
  const cells = props.cells.map((row) => {
    const next = row.map((cell, c) =>
      c < index && c + span(cell.colSpan) > index ? { ...cell, colSpan: span(cell.colSpan) + 1 } : cell,
    );
    next.splice(index, 0, blankCell(row[refCol]));
    return next;
  });
  const columns = [...props.columns];
  columns.splice(index, 0, { width_mm: props.columns[refCol].width_mm });
  return { ...props, columns, cells };
}

export function deleteRow(props: TableLayerProps, at: number): TableLayerProps {
  if (props.rows.length <= 1 || at < 0 || at >= props.rows.length) return props;
  const cells = props.cells.map((row) => row.map((cell) => ({ ...cell })));
  // A merge anchored on the deleted row hands its anchor to the row below.
  cells[at].forEach((cell, c) => {
    if (span(cell.rowSpan) > 1 && at + 1 < cells.length) {
      cells[at + 1][c] = { ...cell, rowSpan: span(cell.rowSpan) - 1 };
    }
  });
  cells.forEach((row, r) =>
    row.forEach((cell, c) => {
      if (r < at && r + span(cell.rowSpan) > at) cells[r][c] = { ...cell, rowSpan: span(cell.rowSpan) - 1 };
    }),
  );
  cells.splice(at, 1);
  const rows = props.rows.filter((_, i) => i !== at);
  return { ...props, rows, cells: cells.map((row) => row.map(trimSpans)) };
}

export function deleteColumn(props: TableLayerProps, at: number): TableLayerProps {
  if (props.columns.length <= 1 || at < 0 || at >= props.columns.length) return props;
  const cells = props.cells.map((row) => row.map((cell) => ({ ...cell })));
  cells.forEach((row) => {
    const gone = row[at];
    if (span(gone.colSpan) > 1 && at + 1 < row.length) row[at + 1] = { ...gone, colSpan: span(gone.colSpan) - 1 };
    row.forEach((cell, c) => {
      if (c < at && c + span(cell.colSpan) > at) row[c] = { ...cell, colSpan: span(cell.colSpan) - 1 };
    });
    row.splice(at, 1);
  });
  const columns = props.columns.filter((_, i) => i !== at);
  return { ...props, columns, cells: cells.map((row) => row.map(trimSpans)) };
}

/** A span of 1 is no span: drop the key so props stay as a designer wrote them. */
function trimSpans(cell: TableCell): TableCell {
  if (span(cell.rowSpan) > 1 && span(cell.colSpan) > 1) return cell;
  const { rowSpan, colSpan, ...rest } = cell;
  return {
    ...rest,
    ...(span(rowSpan) > 1 ? { rowSpan } : {}),
    ...(span(colSpan) > 1 ? { colSpan } : {}),
  };
}

/** The anchor that owns (r, c): itself, or the merge that covers it. */
function ownerOf(props: TableLayerProps, r: number, c: number): { r: number; c: number } {
  for (let rr = 0; rr <= r; rr += 1) {
    for (let cc = 0; cc <= c; cc += 1) {
      const cell = props.cells[rr]?.[cc];
      if (cell && rr + span(cell.rowSpan) > r && cc + span(cell.colSpan) > c) return { r: rr, c: cc };
    }
  }
  return { r, c };
}

/**
 * Set one side (or 'all') of a cell's border AND the facing side of every neighbour across that
 * edge, so the drawn shared edge (`resolveEdges` takes the upper / left cell first) always shows
 * what was edited. A merged anchor writes along its full span.
 */
export function setCellBorder(
  props: TableLayerProps,
  row: number,
  col: number,
  side: TableSide | 'all',
  border: TableBorderSide,
): TableLayerProps {
  const at = ownerOf(props, row, col);
  const anchor = props.cells[at.r][at.c];
  const rs = Math.min(span(anchor.rowSpan), props.rows.length - at.r);
  const cs = Math.min(span(anchor.colSpan), props.columns.length - at.c);
  const cells = props.cells.map((r) => r.map((cell) => ({ ...cell })));
  const write = (r: number, c: number, key: TableSide) => {
    cells[r][c] = { ...cells[r][c], border: { ...(cells[r][c].border ?? {}), [key]: { ...border } } };
  };
  const opposite: Record<TableSide, TableSide> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };
  for (const key of side === 'all' ? SIDES : [side]) {
    write(at.r, at.c, key);
    const along = key === 'top' || key === 'bottom' ? cs : rs;
    const seen = new Set<string>();
    for (let i = 0; i < along; i += 1) {
      const nr = key === 'top' ? at.r - 1 : key === 'bottom' ? at.r + rs : at.r + i;
      const nc = key === 'left' ? at.c - 1 : key === 'right' ? at.c + cs : at.c + i;
      if (nr < 0 || nc < 0 || nr >= props.rows.length || nc >= props.columns.length) continue;
      const owner = ownerOf(props, nr, nc);
      const id = `${owner.r}:${owner.c}`;
      if (seen.has(id)) continue;
      seen.add(id);
      write(owner.r, owner.c, opposite[key]);
    }
  }
  return { ...props, cells };
}

/**
 * Merge the cell range into its top-left cell, which keeps the joined text (row-major, one per
 * line). A range that cuts an existing merge grows to cover it.
 */
export function mergeCells(props: TableLayerProps, r1: number, c1: number, r2: number, c2: number): TableLayerProps {
  let top = Math.max(0, Math.min(r1, r2));
  let left = Math.max(0, Math.min(c1, c2));
  let bottom = Math.min(props.rows.length - 1, Math.max(r1, r2));
  let right = Math.min(props.columns.length - 1, Math.max(c1, c2));
  for (let changed = true; changed; ) {
    changed = false;
    for (let r = top; r <= bottom; r += 1) {
      for (let c = left; c <= right; c += 1) {
        const owner = ownerOf(props, r, c);
        const cell = props.cells[owner.r][owner.c];
        const oBottom = owner.r + span(cell.rowSpan) - 1;
        const oRight = owner.c + span(cell.colSpan) - 1;
        if (owner.r < top || owner.c < left || oBottom > bottom || oRight > right) {
          top = Math.min(top, owner.r);
          left = Math.min(left, owner.c);
          bottom = Math.max(bottom, oBottom);
          right = Math.max(right, oRight);
          changed = true;
        }
      }
    }
  }
  if (top === bottom && left === right) return props;
  const covered = coveredSet(props);
  const texts: string[] = [];
  const cells = props.cells.map((row) => row.map((cell) => ({ ...cell })));
  for (let r = top; r <= bottom; r += 1) {
    for (let c = left; c <= right; c += 1) {
      if (!covered.has(`${r}:${c}`) && cells[r][c].text) texts.push(cells[r][c].text);
      if (r !== top || c !== left) {
        const { rowSpan, colSpan, ...plain } = cells[r][c];
        void rowSpan;
        void colSpan;
        cells[r][c] = { ...plain, text: '' };
      }
    }
  }
  cells[top][left] = {
    ...cells[top][left],
    text: texts.join('\n'),
    rowSpan: bottom - top + 1,
    colSpan: right - left + 1,
  };
  return { ...props, cells: cells.map((row) => row.map(trimSpans)) };
}

/** Undo a merge: the anchor is a single cell again and the cells it covered show. */
export function unmergeCell(props: TableLayerProps, row: number, col: number): TableLayerProps {
  const owner = ownerOf(props, row, col);
  const cells = props.cells.map((r) => r.map((cell) => ({ ...cell })));
  const { rowSpan, colSpan, ...plain } = cells[owner.r][owner.c];
  void rowSpan;
  void colSpan;
  cells[owner.r][owner.c] = plain;
  return { ...props, cells };
}

/** The same table with every cell's text passed through `resolve` (merge fields), before layout. */
export function resolveTableText(props: TableLayerProps, resolve: (text: string) => string): TableLayerProps {
  return {
    ...props,
    cells: props.cells.map((row) => row.map((cell) => (cell.text ? { ...cell, text: resolve(cell.text) } : cell))),
  };
}

/** The CSS-ready font size (mm) of a table's text. */
export function tableFontMm(props: Pick<TableLayerProps, 'fontSize'>): number {
  return (props.fontSize ?? DEFAULT_TABLE_FONT_PT) * PT_TO_MM;
}

export { SIDES as TABLE_SIDES };
