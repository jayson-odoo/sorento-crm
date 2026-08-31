/**
 * The arithmetic behind the tag canvas's drawing-tool behaviour (D33-D44).
 *
 * A tag document keeps its layers FLAT: children carry absolute mm positions
 * and a group is a bounding box holding `children: string[]`. That is what the
 * print renderer reads, so it stays. Everything a group ought to do therefore
 * has to be a function over the layer array rather than a change of shape, and
 * this module is that set of functions: ancestry, propagation of a move or a
 * transform, marquee scoping, hit resolution under group isolation, z reorder,
 * cloning, the Layers panel tree and the viewport transform.
 *
 * No React and no Konva in here on purpose. These are the rules that were wrong
 * on the canvas, and they are testable without a browser.
 */

import type { TagLayer } from './tag-template-types';
import { boundsOf } from './product-block';

// ---------------------------------------------------------------------------
// Shared shapes
// ---------------------------------------------------------------------------

/** A rectangle in millimetres, the same field names a layer uses. */
export interface RectMm {
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface PointMm {
  x_mm: number;
  y_mm: number;
}

export interface PointPx {
  x: number;
  y: number;
}

/**
 * What the viewport is showing.
 *
 * `panX` / `panY` are the artboard origin in stage pixels, so a layer at
 * `x_mm` is drawn at `panX + x_mm * CANVAS_PX_PER_MM * zoom`.
 */
export interface CanvasView {
  zoom: number;
  panX: number;
  panY: number;
}

export interface ZoomLimits {
  min: number;
  max: number;
}

/** Pixels per millimetre at 100%. */
export const CANVAS_PX_PER_MM = 3;

export const CANVAS_MIN_ZOOM = 0.1;
export const CANVAS_MAX_ZOOM = 8;

/** Pixels of breathing room left around the artboard by a fit (D33). */
export const CANVAS_FIT_MARGIN_PX = 32;

const DEFAULT_LIMITS: ZoomLimits = { min: CANVAS_MIN_ZOOM, max: CANVAS_MAX_ZOOM };

// ---------------------------------------------------------------------------
// Ancestry
// ---------------------------------------------------------------------------

function childrenOf(layer: TagLayer | undefined): string[] {
  return layer && layer.props.kind === 'group' ? layer.props.children : [];
}

function indexById(layers: TagLayer[]): Map<string, TagLayer> {
  return new Map(layers.map((layer) => [layer.id, layer]));
}

/** childId -> the id of the group that lists it. */
function parentIndex(layers: TagLayer[]): Map<string, string> {
  const parents = new Map<string, string>();
  for (const layer of layers) {
    if (layer.props.kind !== 'group') continue;
    for (const childId of layer.props.children) {
      // A layer naming itself, or already claimed, is a document we did not
      // write; take the first claim and move on rather than throwing in a
      // render path.
      if (childId === layer.id || parents.has(childId)) continue;
      parents.set(childId, layer.id);
    }
  }
  return parents;
}

/** Every layer under `id`, at any depth. Empty for a layer that is not a group. */
export function descendantsOf(layers: TagLayer[], id: string): string[] {
  const index = indexById(layers);
  const out: string[] = [];
  const seen = new Set<string>([id]);
  const queue = [...childrenOf(index.get(id))];

  while (queue.length > 0) {
    const next = queue.shift() as string;
    if (seen.has(next) || !index.has(next)) continue;
    seen.add(next);
    out.push(next);
    queue.push(...childrenOf(index.get(next)));
  }
  return out;
}

/** The groups above `id`, innermost first. */
export function ancestorsOf(layers: TagLayer[], id: string): string[] {
  const parents = parentIndex(layers);
  const out: string[] = [];
  const seen = new Set<string>([id]);

  let current = parents.get(id);
  while (current && !seen.has(current)) {
    seen.add(current);
    out.push(current);
    current = parents.get(current);
  }
  return out;
}

/** The outermost ancestor of `id`, or `id` when it is already top level. */
export function topLevelOf(layers: TagLayer[], id: string): string {
  const chain = ancestorsOf(layers, id);
  return chain.length > 0 ? chain[chain.length - 1] : id;
}

/** Expand a selection to the layers an operation on it actually touches. */
function withDescendants(layers: TagLayer[], ids: string[]): Set<string> {
  const out = new Set<string>();
  for (const id of ids) {
    out.add(id);
    for (const child of descendantsOf(layers, id)) out.add(child);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Moving and transforming (D38)
// ---------------------------------------------------------------------------

/**
 * Move `ids` and everything under them by one delta.
 *
 * The set is what makes a group and one of its own children, both selected,
 * move once rather than twice.
 */
export function moveLayers(
  layers: TagLayer[],
  ids: string[],
  dx_mm: number,
  dy_mm: number,
): TagLayer[] {
  const moving = withDescendants(layers, ids);
  if (moving.size === 0 || (dx_mm === 0 && dy_mm === 0)) return layers;
  return layers.map((layer) =>
    moving.has(layer.id)
      ? { ...layer, x_mm: layer.x_mm + dx_mm, y_mm: layer.y_mm + dy_mm }
      : layer,
  );
}

/**
 * Apply a group's new box to every descendant (D38).
 *
 * A descendant's offset from the group origin is scaled by the size ratio and
 * turned by the rotation delta; its own size scales and its own rotation gains
 * the delta. That is the same affine change the user made to the box, which is
 * why a resized product block still looks like a product block.
 */
export function transformGroup(
  layers: TagLayer[],
  groupId: string,
  next: RectMm & { rotation_deg: number },
): TagLayer[] {
  const group = layers.find((layer) => layer.id === groupId);
  if (!group || group.props.kind !== 'group') return layers;

  const sx = group.width_mm === 0 ? 1 : next.width_mm / group.width_mm;
  const sy = group.height_mm === 0 ? 1 : next.height_mm / group.height_mm;
  const delta = next.rotation_deg - group.rotation_deg;
  const radians = (delta * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);

  const moving = new Set(descendantsOf(layers, groupId));

  return layers.map((layer) => {
    if (layer.id === groupId) return { ...layer, ...next };
    if (!moving.has(layer.id)) return layer;

    const relX = (layer.x_mm - group.x_mm) * sx;
    const relY = (layer.y_mm - group.y_mm) * sy;
    return {
      ...layer,
      x_mm: next.x_mm + relX * cos - relY * sin,
      y_mm: next.y_mm + relX * sin + relY * cos,
      width_mm: layer.width_mm * sx,
      height_mm: layer.height_mm * sy,
      rotation_deg: layer.rotation_deg + delta,
    };
  });
}

/**
 * Recompute the box of every group above `id` from its own children.
 *
 * Innermost first, so an outer group measures the inner one AFTER the inner one
 * has caught up. Without this, moving a child inside a block leaves the dashed
 * outline where the block used to be, and every later marquee and hit test is
 * answered from a box that is no longer true.
 */
export function refitAncestors(layers: TagLayer[], id: string): TagLayer[] {
  let out = layers;
  for (const ancestorId of ancestorsOf(layers, id)) out = refitGroup(out, ancestorId);
  return out;
}

/** One group's box, measured from the children it still has. */
function refitGroup(layers: TagLayer[], groupId: string): TagLayer[] {
  const index = indexById(layers);
  const group = index.get(groupId);
  const children = childrenOf(group)
    .map((childId) => index.get(childId))
    .filter((child): child is TagLayer => Boolean(child));
  if (!group || children.length === 0) return layers;
  const bounds = boundsOf(children);
  return layers.map((layer) => (layer.id === groupId ? { ...layer, ...bounds } : layer));
}

// ---------------------------------------------------------------------------
// Deleting and ungrouping (D39)
// ---------------------------------------------------------------------------

/**
 * Delete `ids` with their descendants, then repair what pointed at them.
 *
 * Deleting one child of a block must not leave the group naming a layer that no
 * longer exists, and must not leave its box the size it was.
 */
export function removeLayers(layers: TagLayer[], ids: string[]): TagLayer[] {
  const doomed = withDescendants(layers, ids);
  if (doomed.size === 0) return layers;

  // The surviving groups above what is going, innermost first: those are the
  // boxes that have to shrink once the delete lands.
  const toRefit: string[] = [];
  for (const id of ids) {
    for (const ancestorId of ancestorsOf(layers, id)) {
      if (!doomed.has(ancestorId) && !toRefit.includes(ancestorId)) toRefit.push(ancestorId);
    }
  }

  let out = layers
    .filter((layer) => !doomed.has(layer.id))
    .map((layer) =>
      layer.props.kind === 'group'
        ? {
            ...layer,
            props: {
              ...layer.props,
              children: layer.props.children.filter((childId) => !doomed.has(childId)),
            },
          }
        : layer,
    );

  for (const ancestorId of toRefit) out = refitGroup(out, ancestorId);
  return out;
}

/**
 * Drop the group layers and set their children free.
 *
 * A group inside another group hands its children to that parent, or the parent
 * would keep naming a layer that has gone. Returns the freed ids, which is what
 * the editor selects afterwards.
 */
export function ungroupLayers(
  layers: TagLayer[],
  groupIds: string[],
): { layers: TagLayer[]; ids: string[] } {
  const targets = groupIds.filter((id) => {
    const layer = layers.find((l) => l.id === id);
    return layer?.props.kind === 'group';
  });
  if (targets.length === 0) return { layers, ids: [] };

  const dropped = new Set(targets);
  const freed: string[] = [];
  for (const id of targets) {
    freed.push(...childrenOf(layers.find((l) => l.id === id)));
  }

  const out = layers
    .filter((layer) => !dropped.has(layer.id))
    .map((layer) => {
      if (layer.props.kind !== 'group') return layer;
      const children: string[] = [];
      for (const childId of layer.props.children) {
        if (!dropped.has(childId)) {
          children.push(childId);
          continue;
        }
        children.push(...childrenOf(layers.find((l) => l.id === childId)));
      }
      return { ...layer, props: { ...layer.props, children } };
    });

  return { layers: out, ids: freed };
}

// ---------------------------------------------------------------------------
// The Layers panel as a tree (D43)
// ---------------------------------------------------------------------------

/** One row of the Layers panel, top to bottom. */
export interface PanelRow {
  id: string;
  parentId: string | null;
  depth: number;
}

/** Where a dragged row lands: inside `parentId`, directly above `beforeId`. */
export interface ReparentTarget {
  /** The group it joins, or null for the top level. */
  parentId: string | null;
  /** The sibling it sits directly above, or null to go last (bottom-most). */
  beforeId: string | null;
}

/**
 * The panel's rows, top down: highest z first, a group's children indented
 * directly under it.
 *
 * The panel reads the z order, so this is also the order `reparentLayer`
 * renumbers against. Deriving it here rather than in the component is what lets
 * the drag rules be tested without rendering anything.
 */
export function panelRows(layers: TagLayer[]): PanelRow[] {
  const parents = parentIndex(layers);
  const byZDesc = [...layers].sort((a, b) => b.z_index - a.z_index);

  const rows: PanelRow[] = [];
  const seen = new Set<string>();

  const walk = (layer: TagLayer, parentId: string | null, depth: number): void => {
    if (seen.has(layer.id)) return;
    seen.add(layer.id);
    rows.push({ id: layer.id, parentId, depth });
    for (const child of byZDesc.filter((l) => parents.get(l.id) === layer.id)) {
      walk(child, layer.id, depth + 1);
    }
  };

  for (const layer of byZDesc) {
    if (!parents.has(layer.id)) walk(layer, null, 0);
  }
  // A document whose parent chain loops would otherwise lose rows entirely.
  for (const layer of byZDesc) {
    if (!seen.has(layer.id)) walk(layer, parents.get(layer.id) ?? null, 0);
  }
  return rows;
}

/**
 * What a drop on the row `overId` means, given how far down that row the
 * pointer is (0 at its top edge, 1 at its bottom).
 *
 * The middle half of a GROUP row is the group itself, which is how a layer
 * joins a block; every other part of every row is a gap between two rows, and a
 * gap belongs to whichever parent the rows around it have. That is the whole
 * difference between "put it here" and "put it in there".
 */
export function panelDropTarget(
  layers: TagLayer[],
  overId: string,
  ratio: number,
): ReparentTarget | null {
  const rows = panelRows(layers);
  const index = rows.findIndex((row) => row.id === overId);
  if (index === -1) return null;
  const over = rows[index];

  const isGroup = layers.find((l) => l.id === overId)?.props.kind === 'group';
  if (isGroup && ratio > 0.25 && ratio < 0.75) {
    return { parentId: overId, beforeId: null };
  }

  if (ratio < 0.5) return { parentId: over.parentId, beforeId: overId };

  const next = rows.slice(index + 1).find((row) => row.parentId === over.parentId);
  return { parentId: over.parentId, beforeId: next?.id ?? null };
}

/**
 * Move a layer to another place in the panel, taking its subtree with it (D43).
 *
 * Membership and stacking are the same fact here: a group's children are a
 * contiguous block directly below it in the panel, so a drop that changes where
 * a row sits also changes which group it belongs to. The whole document is
 * renumbered 1..n afterwards, which is what keeps that true, and both the old
 * and the new ancestors are refitted so no box outlives the children it
 * measured.
 *
 * A drop into the layer's own subtree is refused rather than corrected: there
 * is no sensible answer, and returning the same array lets the caller skip the
 * history entry.
 */
export function reparentLayer(
  layers: TagLayer[],
  id: string,
  target: ReparentTarget,
): TagLayer[] {
  const index = indexById(layers);
  const moving = index.get(id);
  if (!moving) return layers;

  const parentId = target.parentId;
  if (parentId !== null) {
    const parent = index.get(parentId);
    if (!parent || parent.props.kind !== 'group') return layers;
    if (parentId === id || descendantsOf(layers, id).includes(parentId)) return layers;
  }

  const oldParentId = parentIndex(layers).get(id) ?? null;

  // Sibling lists in panel order, the moved layer taken out of all of them.
  const rows = panelRows(layers).filter((row) => row.id !== id);
  const siblings = new Map<string | null, string[]>();
  for (const row of rows) {
    const list = siblings.get(row.parentId) ?? [];
    list.push(row.id);
    siblings.set(row.parentId, list);
  }

  const destination = siblings.get(parentId) ?? [];
  const slot =
    target.beforeId === null ? destination.length : destination.indexOf(target.beforeId);
  destination.splice(slot === -1 ? destination.length : slot, 0, id);
  siblings.set(parentId, destination);

  // Flatten back to panel order, then number from the bottom up so the panel
  // order IS the z order.
  const flattened: string[] = [];
  const walk = (parent: string | null): void => {
    for (const childId of siblings.get(parent) ?? []) {
      flattened.push(childId);
      walk(childId);
    }
  };
  walk(null);

  const zByIndex = new Map<string, number>();
  flattened.forEach((layerId, position) => {
    zByIndex.set(layerId, flattened.length - position);
  });

  let out = layers.map((layer) => {
    const next: TagLayer = { ...layer, z_index: zByIndex.get(layer.id) ?? layer.z_index };
    if (next.props.kind === 'group') {
      // Children bottom-most first, the order the block builders write and the
      // order the canvas draws in.
      const children = [...(siblings.get(next.id) ?? [])].reverse();
      next.props = { ...next.props, children };
    }
    return next;
  });

  for (const ancestorId of [
    ...(oldParentId ? [oldParentId, ...ancestorsOf(out, oldParentId)] : []),
    ...(parentId ? [parentId, ...ancestorsOf(out, parentId)] : []),
  ]) {
    out = refitGroup(out, ancestorId);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Marquee and hit testing (D36, D37, D40)
// ---------------------------------------------------------------------------

/** The band between two corners, whichever way round the user dragged. */
export function bandBetween(a: PointMm, b: PointMm): RectMm {
  return {
    x_mm: Math.min(a.x_mm, b.x_mm),
    y_mm: Math.min(a.y_mm, b.y_mm),
    width_mm: Math.abs(a.x_mm - b.x_mm),
    height_mm: Math.abs(a.y_mm - b.y_mm),
  };
}

function intersects(layer: TagLayer, band: RectMm): boolean {
  return (
    layer.x_mm <= band.x_mm + band.width_mm &&
    layer.x_mm + layer.width_mm >= band.x_mm &&
    layer.y_mm <= band.y_mm + band.height_mm &&
    layer.y_mm + layer.height_mm >= band.y_mm
  );
}

function contains(layer: TagLayer, x_mm: number, y_mm: number): boolean {
  return (
    x_mm >= layer.x_mm &&
    x_mm <= layer.x_mm + layer.width_mm &&
    y_mm >= layer.y_mm &&
    y_mm <= layer.y_mm + layer.height_mm
  );
}

function selectable(layer: TagLayer): boolean {
  return layer.visible && !layer.locked;
}

/**
 * Every layer the band touches, expressed at the scope the user is working in.
 *
 * Touch selects rather than enclose, as Illustrator does: a band across the
 * middle of two badges takes both. At the top level a child stands for its
 * outermost group; inside a group the scope is that group's direct children, so
 * a marquee cannot reach out of the block being edited.
 */
export function marqueeHits(
  layers: TagLayer[],
  band: RectMm,
  scope: { insideGroupId: string | null } = { insideGroupId: null },
): string[] {
  const index = indexById(layers);
  const hits = new Set<string>();

  for (const layer of layers) {
    if (!selectable(layer) || !intersects(layer, band)) continue;

    let representative: string | null;
    if (scope.insideGroupId === null) {
      representative = topLevelOf(layers, layer.id);
    } else if (layer.id === scope.insideGroupId) {
      representative = null;
    } else {
      const chain = ancestorsOf(layers, layer.id);
      const depth = chain.indexOf(scope.insideGroupId);
      representative = depth === -1 ? null : depth === 0 ? layer.id : chain[depth - 1];
    }

    if (!representative) continue;
    const resolved = index.get(representative);
    if (resolved && selectable(resolved)) hits.add(representative);
  }

  return layers
    .filter((layer) => hits.has(layer.id))
    .sort((a, b) => a.z_index - b.z_index)
    .map((layer) => layer.id);
}

/**
 * The direct child of `groupId` under the point, highest z wins (D37).
 *
 * This is what a double-click on a block picks. A nested group counts as a
 * child, so double-clicking it again goes one level deeper.
 */
export function topmostChildAt(
  layers: TagLayer[],
  groupId: string,
  x_mm: number,
  y_mm: number,
): string | null {
  const index = indexById(layers);
  const candidates = childrenOf(index.get(groupId))
    .map((childId) => index.get(childId))
    .filter(
      (child): child is TagLayer =>
        Boolean(child) && selectable(child as TagLayer) && contains(child as TagLayer, x_mm, y_mm),
    )
    .sort((a, b) => b.z_index - a.z_index);

  return candidates[0]?.id ?? null;
}

/**
 * What a click at this point selects, given the groups already entered.
 *
 * An entered group is skipped as a target, exactly as the canvas stops it
 * listening; whatever is hit then resolves outwards to the first ancestor that
 * has NOT been entered, so one click on a block takes the block and a click
 * inside an open block takes the child.
 */
export function hitLayerAt(
  layers: TagLayer[],
  x_mm: number,
  y_mm: number,
  entered: Set<string>,
): string | null {
  const hit = [...layers]
    .filter(
      (layer) =>
        selectable(layer) &&
        contains(layer, x_mm, y_mm) &&
        !(layer.props.kind === 'group' && entered.has(layer.id)),
    )
    .sort((a, b) => b.z_index - a.z_index)[0];
  if (!hit) return null;

  const chain = [...ancestorsOf(layers, hit.id)].reverse();
  for (const ancestorId of chain) {
    if (!entered.has(ancestorId)) return ancestorId;
  }
  return hit.id;
}

// ---------------------------------------------------------------------------
// Z order (D40)
// ---------------------------------------------------------------------------

export type ReorderDirection = 'front' | 'forward' | 'backward' | 'back';

/**
 * Move the selection through the stack, a group and its descendants as one
 * contiguous block, and renumber `z_index` 1..n afterwards.
 *
 * Working in blocks rather than in single layers is what stops a "Bring to
 * Front" on a product block leaving its photo behind everything else.
 *
 * The move happens at the level of the selection's COMMON parent (D60), which
 * is how Illustrator arranges within the current group: a badge selected
 * inside a block is sent to the back OF THAT BLOCK, and the block itself does
 * not move. A selection whose members sit under different parents has no group
 * to arrange inside, so each id is taken as its top-level block instead.
 */
export function reorderZ(
  layers: TagLayer[],
  ids: string[],
  direction: ReorderDirection,
): TagLayer[] {
  if (layers.length === 0 || ids.length === 0) return layers;

  const index = indexById(layers);
  const parents = parentIndex(layers);
  const byZ = [...layers].sort((a, b) => a.z_index - b.z_index);
  const parentOf = (id: string): string | null => parents.get(id) ?? null;

  const selected = ids.filter((id) => index.has(id));
  if (selected.length === 0) return layers;

  // Arrange within the selection's COMMON parent, the way Illustrator arranges
  // within the current group (D60). A selection spread over two parents has no
  // group to arrange inside, so it falls back to whole top-level blocks.
  const selectionParents = new Set(selected.map(parentOf));
  const scopeParent = selectionParents.size === 1 ? parentOf(selected[0]) : null;
  const movingRoots =
    selectionParents.size === 1
      ? new Set(selected)
      : new Set(selected.map((id) => topLevelOf(layers, id)));

  const arrange = (siblings: string[]): string[] => {
    const isSelected = (id: string) => movingRoots.has(id);
    const ordered = [...siblings];
    if (direction === 'front') {
      return [...ordered.filter((id) => !isSelected(id)), ...ordered.filter(isSelected)];
    }
    if (direction === 'back') {
      return [...ordered.filter(isSelected), ...ordered.filter((id) => !isSelected(id))];
    }
    if (direction === 'forward') {
      for (let i = ordered.length - 2; i >= 0; i -= 1) {
        if (isSelected(ordered[i]) && !isSelected(ordered[i + 1])) {
          [ordered[i], ordered[i + 1]] = [ordered[i + 1], ordered[i]];
        }
      }
      return ordered;
    }
    for (let i = 1; i < ordered.length; i += 1) {
      if (isSelected(ordered[i]) && !isSelected(ordered[i - 1])) {
        [ordered[i], ordered[i - 1]] = [ordered[i - 1], ordered[i]];
      }
    }
    return ordered;
  };

  // Walk the document bottom-up: a layer is emitted after its own subtree, so
  // every block stays contiguous with its group layer directly above it, and
  // only the scope's sibling list is re-ordered.
  const seen = new Set<string>();
  const emit = (parent: string | null): string[] => {
    const siblings = byZ.filter((layer) => parentOf(layer.id) === parent).map((layer) => layer.id);
    const out: string[] = [];
    for (const id of parent === scopeParent ? arrange(siblings) : siblings) {
      if (seen.has(id)) continue;
      seen.add(id);
      out.push(...emit(id), id);
    }
    return out;
  };

  const rank = new Map<string, number>();
  emit(null).forEach((id, position) => rank.set(id, position + 1));

  return layers.map((layer) => ({ ...layer, z_index: rank.get(layer.id) ?? layer.z_index }));
}

// ---------------------------------------------------------------------------
// Cloning (D39)
// ---------------------------------------------------------------------------

/**
 * Copy `ids` with their descendants, giving every copy a fresh id.
 *
 * `children` is remapped onto the copies, which is the bug this replaces: a
 * duplicated group used to keep pointing at the ORIGINAL children, so moving
 * the copy moved the original's layers.
 *
 * Returns the new layers alone (append them to the document) and the ids of the
 * copies of `ids` themselves, which is what to select afterwards.
 */
export function cloneLayers(
  layers: TagLayer[],
  ids: string[],
  newId: () => string,
  offset_mm: number,
  zBase?: number,
): { layers: TagLayer[]; ids: string[] } {
  const cloning = withDescendants(layers, ids);
  if (cloning.size === 0) return { layers: [], ids: [] };

  const source = layers
    .filter((layer) => cloning.has(layer.id))
    .sort((a, b) => a.z_index - b.z_index);

  const idMap = new Map<string, string>();
  for (const layer of source) idMap.set(layer.id, newId());

  const base = zBase ?? Math.max(...layers.map((l) => l.z_index)) + 1;

  const clones = source.map((layer, index) => {
    const clone: TagLayer = {
      ...structuredClone(layer),
      id: idMap.get(layer.id) as string,
      x_mm: layer.x_mm + offset_mm,
      y_mm: layer.y_mm + offset_mm,
      z_index: base + index,
    };
    if (clone.props.kind === 'group') {
      clone.props = {
        ...clone.props,
        children: clone.props.children
          .map((childId) => idMap.get(childId))
          .filter((childId): childId is string => Boolean(childId)),
      };
    }
    return clone;
  });

  return {
    layers: clones,
    ids: ids
      .map((id) => idMap.get(id))
      .filter((id): id is string => Boolean(id)),
  };
}

// ---------------------------------------------------------------------------
// Viewport (D33, D34)
// ---------------------------------------------------------------------------

/** Where a stage pixel lands on the artboard. */
export function stageToMm(view: CanvasView, x: number, y: number): PointMm {
  const scale = CANVAS_PX_PER_MM * view.zoom;
  return { x_mm: (x - view.panX) / scale, y_mm: (y - view.panY) / scale };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Zoom about a point, keeping whatever is under it under it (D34).
 *
 * The px-per-mm constant cancels out of `pan' = p - (p - pan) * z' / z`, so
 * this needs neither the artboard size nor the base scale.
 */
export function zoomAt(
  view: CanvasView,
  pointer: PointPx,
  factor: number,
  limits: ZoomLimits = DEFAULT_LIMITS,
): CanvasView {
  const zoom = clamp(view.zoom * factor, limits.min, limits.max);
  if (zoom === view.zoom) return view;
  const ratio = zoom / view.zoom;
  return {
    zoom,
    panX: pointer.x - (pointer.x - view.panX) * ratio,
    panY: pointer.y - (pointer.y - view.panY) * ratio,
  };
}

/** The view that fits the artboard in the container, centred, with a margin. */
export function fitView(
  container: { width: number; height: number },
  artboard: { width_mm: number; height_mm: number },
  marginPx: number = CANVAS_FIT_MARGIN_PX,
  limits: ZoomLimits = DEFAULT_LIMITS,
): CanvasView {
  const availableWidth = container.width - marginPx * 2;
  const availableHeight = container.height - marginPx * 2;
  if (
    availableWidth <= 0 ||
    availableHeight <= 0 ||
    artboard.width_mm <= 0 ||
    artboard.height_mm <= 0
  ) {
    // The container has not been measured yet. 100% at the margin is a view the
    // ResizeObserver will replace within the frame, and never a NaN.
    return { zoom: 1, panX: marginPx, panY: marginPx };
  }

  const zoom = clamp(
    Math.min(
      availableWidth / (artboard.width_mm * CANVAS_PX_PER_MM),
      availableHeight / (artboard.height_mm * CANVAS_PX_PER_MM),
    ),
    limits.min,
    limits.max,
  );
  const scale = CANVAS_PX_PER_MM * zoom;
  return {
    zoom,
    panX: (container.width - artboard.width_mm * scale) / 2,
    panY: (container.height - artboard.height_mm * scale) / 2,
  };
}

/** The view at 100%, artboard centred (Cmd/Ctrl+1). */
export function actualSizeView(
  container: { width: number; height: number },
  artboard: { width_mm: number; height_mm: number },
): CanvasView {
  return {
    zoom: 1,
    panX: (container.width - artboard.width_mm * CANVAS_PX_PER_MM) / 2,
    panY: (container.height - artboard.height_mm * CANVAS_PX_PER_MM) / 2,
  };
}
