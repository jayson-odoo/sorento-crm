/**
 * Surface finishes: what the walls and the floor look like.
 *
 * Deliberately a SMALL fixed palette rather than a texture library. The point
 * of a finish here is to let a customer picture the room and to tell two
 * schemes apart at a glance, not to render a specific tile - the tile they are
 * actually buying is a product on the quote, with a code and a price, and
 * pretending a swatch is that product would be a lie the drawing tells.
 *
 * Ids are stored, never colours: a stored colour cannot be restyled and would
 * ignore the theme forever.
 */

export interface Finish {
  id: string;
  label: string;
  /** Plan fill / 3D material colour. */
  color: string;
}

export const WALL_FINISHES: Finish[] = [
  { id: 'plaster', label: 'Plaster', color: '#f8fafc' },
  { id: 'warm-white', label: 'Warm white', color: '#f5f0e8' },
  { id: 'light-grey', label: 'Light grey', color: '#e2e8f0' },
  { id: 'charcoal', label: 'Charcoal', color: '#475569' },
  { id: 'sage', label: 'Sage', color: '#dbe5dc' },
  { id: 'terracotta', label: 'Terracotta', color: '#e3c2b4' },
];

export const FLOOR_FINISHES: Finish[] = [
  { id: 'screed', label: 'Screed', color: '#e2e8f0' },
  { id: 'porcelain', label: 'Porcelain', color: '#eef2f6' },
  { id: 'timber', label: 'Timber', color: '#d8b98d' },
  { id: 'slate', label: 'Slate', color: '#94a3b8' },
  { id: 'marble', label: 'Marble', color: '#f1efe9' },
  { id: 'graphite', label: 'Graphite', color: '#64748b' },
];

export const DEFAULT_WALL_FINISH = 'plaster';
export const DEFAULT_FLOOR_FINISH = 'screed';

export interface Finishes {
  /** One id for the whole floor. */
  floor?: string;
  /** Per wall, keyed by outline index as a string (JSON has no numeric keys). */
  walls?: Record<string, string>;
}

function colorFrom(palette: Finish[], id: string | undefined, fallback: string): string {
  const found = palette.find((finish) => finish.id === id);
  if (found) return found.color;
  // An unknown id is not an error: a design saved when the palette had a
  // colour that has since been dropped must still open, just plainly.
  return palette.find((finish) => finish.id === fallback)?.color ?? palette[0].color;
}

export function wallColor(finishes: Finishes | undefined, wallIndex: number): string {
  return colorFrom(WALL_FINISHES, finishes?.walls?.[String(wallIndex)], DEFAULT_WALL_FINISH);
}

export function floorColor(finishes: Finishes | undefined): string {
  return colorFrom(FLOOR_FINISHES, finishes?.floor, DEFAULT_FLOOR_FINISH);
}

/** The chosen id for a wall, or the default. Used to show which swatch is on. */
export function wallFinishId(finishes: Finishes | undefined, wallIndex: number): string {
  return finishes?.walls?.[String(wallIndex)] ?? DEFAULT_WALL_FINISH;
}

export function floorFinishId(finishes: Finishes | undefined): string {
  return finishes?.floor ?? DEFAULT_FLOOR_FINISH;
}

/** Set one wall's finish, leaving every other surface alone. */
export function setWallFinish(
  finishes: Finishes | undefined,
  wallIndex: number,
  finishId: string,
): Finishes {
  return {
    ...finishes,
    walls: { ...(finishes?.walls ?? {}), [String(wallIndex)]: finishId },
  };
}

export function setFloorFinish(finishes: Finishes | undefined, finishId: string): Finishes {
  return { ...finishes, floor: finishId };
}
