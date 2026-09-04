/**
 * Layout state for `TagCanvasEditor`'s side panels (S1, D7): the Lines +
 * Layers column on the left, the Inspector on the right, and the split
 * between Lines/rail and Layers inside the left column.
 *
 * One localStorage key shared by the template editor and the request
 * designer (AC-S1-5), so a width chosen in either place carries to the
 * other. `react-resizable-panels` reports sizes as PERCENTAGES of the panel
 * group's own width, which changes with the browser window - what is
 * persisted here is pixels, so a saved width means the same thing on a
 * different screen. The caller converts px <-> % against the group's
 * measured width on mount and on every resize.
 */

export interface PanelLayout {
  /** Width of the left column (Lines/rail + Layers), in px. */
  left: number;
  /** Width of the right column (Inspector), in px. */
  right: number;
  /** Height given to the rail (top pane) of the left column's own split, in px. */
  railSplit: number;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
}

export const STORAGE_KEY = 'dealer-kit.canvas-panels.v1';

export const LEFT_MIN_PX = 180;
export const LEFT_MAX_PX = 480;
export const RIGHT_MIN_PX = 200;
export const RIGHT_MAX_PX = 480;
/** Neither pane of the left column's own split may shrink below this (AC-S1-4). */
export const RAIL_MIN_PX = 96;

export const DEFAULT_PANEL_LAYOUT: PanelLayout = {
  left: 208, // matches the old fixed `w-52`
  right: 240, // matches the old fixed `w-60`
  railSplit: 220,
  leftCollapsed: false,
  rightCollapsed: false,
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function clampLeft(px: number): number {
  return clamp(px, LEFT_MIN_PX, LEFT_MAX_PX);
}

export function clampRight(px: number): number {
  return clamp(px, RIGHT_MIN_PX, RIGHT_MAX_PX);
}

/**
 * Only the floor is enforced here - the ceiling depends on the left column's
 * measured height at render time (the Layers pane needs the same 96px floor
 * out of the same space), so the component clamps the other side live.
 */
export function clampRailSplit(px: number): number {
  return Math.max(px, RAIL_MIN_PX);
}

function isPanelLayout(value: unknown): value is PanelLayout {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.left === 'number' &&
    typeof v.right === 'number' &&
    typeof v.railSplit === 'number' &&
    typeof v.leftCollapsed === 'boolean' &&
    typeof v.rightCollapsed === 'boolean'
  );
}

/** Reads the persisted layout, clamped, or the default when absent/corrupt. */
export function readPanelLayout(): PanelLayout {
  if (typeof window === 'undefined') return DEFAULT_PANEL_LAYOUT;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PANEL_LAYOUT;
    const parsed: unknown = JSON.parse(raw);
    if (!isPanelLayout(parsed)) return DEFAULT_PANEL_LAYOUT;
    return {
      left: clampLeft(parsed.left),
      right: clampRight(parsed.right),
      railSplit: clampRailSplit(parsed.railSplit),
      leftCollapsed: parsed.leftCollapsed,
      rightCollapsed: parsed.rightCollapsed,
    };
  } catch {
    return DEFAULT_PANEL_LAYOUT;
  }
}

export function writePanelLayout(layout: PanelLayout): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  } catch {
    // ignore - non-persistent fallback is acceptable
  }
}
