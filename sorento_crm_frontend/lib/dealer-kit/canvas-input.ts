/**
 * Pointer and keyboard rules of the tag designer canvas that depend on the platform or on the
 * whole stack of layers under the pointer (DESIGNER-RICH-TEXT owner bug, 6 Nov).
 */

import { ancestorsOf } from './canvas-geometry';
import type { TagLayer } from './tag-template-types';

/** macOS (and iPadOS) writes shortcuts with the command key. */
export function isMacPlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Mac|iPod|iPhone|iPad/.test(navigator.platform ?? '');
}

/** A shortcut as the menu writes it: `⌘G` on macOS, `Ctrl+G` elsewhere. */
export function shortcutLabel(key: string, mac: boolean): string {
  return mac ? `⌘${key}` : `Ctrl+${key}`;
}

type Modifiers = Pick<MouseEvent, 'shiftKey' | 'metaKey' | 'ctrlKey'>;

/** Shift+click adds to the selection everywhere; so does Cmd+click on macOS and Ctrl+click
 * elsewhere. */
export function isAdditiveClick(e: Modifiers, mac: boolean): boolean {
  return e.shiftKey || (mac ? e.metaKey : e.ctrlKey);
}

/** On macOS Ctrl+click is the system right-click: the context menu resolves its own target, so
 * the mousedown that comes with it must not change the selection. */
export function isMacContextClick(e: Pick<MouseEvent, 'ctrlKey' | 'button'>, mac: boolean): boolean {
  return mac && e.ctrlKey && e.button === 0;
}

function contains(layer: TagLayer, x_mm: number, y_mm: number): boolean {
  return (
    x_mm >= layer.x_mm &&
    x_mm <= layer.x_mm + layer.width_mm &&
    y_mm >= layer.y_mm &&
    y_mm <= layer.y_mm + layer.height_mm
  );
}

/** The outermost layer a click on `id` selects: its topmost ancestor not entered. */
export function selectionTarget(layers: TagLayer[], id: string, entered: Set<string>): string {
  const chain = [...ancestorsOf(layers, id)].reverse();
  for (const ancestorId of chain) {
    if (!entered.has(ancestorId)) return ancestorId;
  }
  return id;
}

/**
 * Every selectable layer whose box holds the point, as the id a click would select, top first
 * (the same order `hitLayerAt` picks its one layer from).
 */
export function layersAt(
  layers: TagLayer[],
  x_mm: number,
  y_mm: number,
  entered: Set<string>,
): string[] {
  const hits = [...layers]
    .filter(
      (layer) =>
        layer.visible &&
        !layer.locked &&
        contains(layer, x_mm, y_mm) &&
        !(layer.props.kind === 'group' && entered.has(layer.id)),
    )
    .sort((a, b) => b.z_index - a.z_index);
  const out: string[] = [];
  for (const layer of hits) {
    const id = selectionTarget(layers, layer.id, entered);
    if (!out.includes(id)) out.push(id);
  }
  return out;
}

/**
 * The selection after a right-click, or null to keep the current one.
 *
 * `hits` are the layers under the pointer, top first. A right-click on ANY of them that is
 * already selected keeps the whole selection, so the menu acts on it (a frame drawn over two
 * selected text boxes must not steal the click). Nothing selected under the pointer selects just
 * the top one; empty canvas keeps the selection.
 */
export function selectionForContextMenu(
  selected: ReadonlySet<string>,
  hits: string[],
): Set<string> | null {
  if (hits.length === 0) return null;
  if (hits.some((id) => selected.has(id))) return null;
  return new Set([hits[0]]);
}
