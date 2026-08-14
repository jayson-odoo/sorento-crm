/**
 * The one place the page grid's row unit and gap are defined.
 *
 * The editor lays blocks out with react-grid-layout and the published page lays
 * the same blocks out with CSS grid. Both compute a block's height from the
 * same row count, so if the two disagree about what a row is worth, what the
 * designer sees is not what the reader gets - which is exactly what happened:
 * the editor used a 24px row and the renderer a 28px one, so blocks that sat
 * neatly in the builder ran into each other once published.
 *
 * Height of N rows is the same formula on both sides:
 *
 *     N * ROW_HEIGHT_PX + (N - 1) * ROW_GAP_PX
 *
 * react-grid-layout gets it from `rowHeight` + `margin`; CSS grid from
 * `grid-auto-rows` + `gap`.
 */

/** Grid row unit in px. Small, so content-driven heights land close to their true size. */
export const ROW_HEIGHT_PX = 24;

/** Vertical gap between grid items, in px. */
export const ROW_GAP_PX = 12;

/** What N rows come to, in pixels. */
export function rowsToHeight(rows: number): number {
  return rows * ROW_HEIGHT_PX + Math.max(0, rows - 1) * ROW_GAP_PX;
}

/** Rows needed to show `heightPx` without clipping. */
export function rowsForHeight(heightPx: number): number {
  return Math.max(1, Math.ceil((heightPx + ROW_GAP_PX) / (ROW_HEIGHT_PX + ROW_GAP_PX)));
}
