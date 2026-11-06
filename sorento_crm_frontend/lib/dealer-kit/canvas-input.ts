/**
 * Pointer and keyboard rules of the tag designer canvas that depend on the platform or on the
 * whole stack of layers under the pointer (DESIGNER-RICH-TEXT owner bug, 6 Nov).
 */

import { useEffect, useState } from 'react';

import { ancestorsOf, contains, selectable } from './canvas-geometry';
import type { TagLayer } from './tag-template-types';

/** macOS (and iPadOS) writes shortcuts with the command key. */
export function isMacPlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Mac|iPod|iPhone|iPad/.test(navigator.platform ?? '');
}

/** A shortcut as menus and tooltips write it: `⌘G` / `⇧⌘Z` on macOS, `Ctrl+G` /
 * `Ctrl+Shift+Z` elsewhere. */
export function shortcutLabel(key: string, mac: boolean, shift = false): string {
  if (mac) return `${shift ? '⇧' : ''}⌘${key}`;
  return `Ctrl+${shift ? 'Shift+' : ''}${key}`;
}

/** Whether this browser is macOS, read after mount (there is no navigator on the server). */
export function useIsMac(): boolean {
  const [mac, setMac] = useState(false);
  useEffect(() => setMac(isMacPlatform()), []);
  return mac;
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
        selectable(layer) &&
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
 * `hits` are the layer boxes under the pointer, top first; `drawnHit` is the layer Konva actually
 * drew there (as the id a click selects), when it can say.
 *  1. ANY selected layer under the pointer keeps the whole selection, so the menu acts on it: a
 *     selected layer under the pointer wins over unselected shapes drawn on top of it (a frame,
 *     a background card), which is how Group stays reachable (crew pass item 12, 6 Nov).
 *  2. Otherwise the layer Konva drew is selected alone; without one, the top box.
 *  3. Empty canvas keeps the selection.
 */
export function selectionForContextMenu(
  selected: ReadonlySet<string>,
  hits: string[],
  drawnHit?: string | null,
): Set<string> | null {
  const under = drawnHit ? [drawnHit, ...hits] : hits;
  if (under.some((id) => selected.has(id))) return null;
  if (under.length === 0) return null;
  return new Set([under[0]]);
}
