/**
 * The town's camera as plain numbers (TOWN-V2 rule 4): drag sideways turns, drag up and down tilts
 * between street level (20 degrees) and bird's-eye (80 degrees), wheel / pinch / buttons zoom 0.13x
 * (all of Malaysia, TOWN-PROJECT-CITY) to 2.2x, and Reset view returns to DEFAULT_VIEW: north up over Shah Alam
 * at the live island's scale.
 */
export interface TownView {
  yaw: number;
  tilt: number;
  zoom: number;
  /** TOWN-PROJECT-CITY: where the camera looks (world x, z), when it has flown away from Shah Alam */
  tx?: number;
  tz?: number;
}

const DEG = Math.PI / 180;
export const TILT_MIN = 20 * DEG;
export const TILT_MAX = 80 * DEG;
export const ZOOM_MIN = 0.13;
export const ZOOM_MAX = 2.2;
const RADIUS = Math.hypot(70, 80);
const TURN_PER_PX = 0.006;
const TILT_PER_PX = 0.005;
const ZOOM_STEP = 1.25;

export const DEFAULT_VIEW: TownView = Object.freeze({ yaw: 142 * DEG, tilt: Math.atan2(70, 80), zoom: 1 });

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
export const clampZoom = (zoom: number) => clamp(zoom, ZOOM_MIN, ZOOM_MAX);

/** The view after a drag of (dx, dy) pixels from `start`: down tilts toward bird's-eye. */
export function dragView(start: TownView, dx: number, dy: number): TownView {
  return { ...start, yaw: start.yaw - dx * TURN_PER_PX, tilt: clamp(start.tilt + dy * TILT_PER_PX, TILT_MIN, TILT_MAX) };
}

export const wheelZoom = (zoom: number, deltaY: number) => clampZoom(zoom * Math.exp(-deltaY * 0.0015));
export const pinchZoom = (startZoom: number, startDistance: number, distance: number) =>
  clampZoom((startZoom * distance) / Math.max(1, startDistance));
export const stepZoom = (zoom: number, direction: 1 | -1) => clampZoom(direction > 0 ? zoom * ZOOM_STEP : zoom / ZOOM_STEP);

/** Where the camera sits for `view`, looking at the island's centre `lookY` up, `radius` away (the
 * perspective camera passes its fitted distance over the zoom; zoom itself is not applied here). */
export function cameraPosition(view: TownView, lookY: number, radius = RADIUS): [number, number, number] {
  const flat = Math.cos(view.tilt) * radius;
  return [Math.cos(view.yaw) * flat, lookY + Math.sin(view.tilt) * radius, Math.sin(view.yaw) * flat];
}
