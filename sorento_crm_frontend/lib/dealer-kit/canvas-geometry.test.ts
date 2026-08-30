/**
 * The arithmetic behind the tag canvas's Illustrator-style behaviour (D33-D44).
 *
 * Everything here is a pure function over the layer array, which is the point:
 * group propagation, marquee scoping, hit resolution under isolation and the
 * zoom transform are the parts that were wrong on the canvas, and none of them
 * needs a browser to be pinned.
 */

import { describe, expect, it } from 'vitest';

import type { TagLayer } from './tag-template-types';
import { defaultShapeProps, defaultTextProps } from './tag-template-types';
import {
  ancestorsOf,
  bandBetween,
  panelDropTarget,
  panelRows,
  reparentLayer,
  cloneLayers,
  descendantsOf,
  fitView,
  hitLayerAt,
  marqueeHits,
  moveLayers,
  refitAncestors,
  removeLayers,
  reorderZ,
  stageToMm,
  topLevelOf,
  topmostChildAt,
  transformGroup,
  ungroupLayers,
  zoomAt,
  CANVAS_PX_PER_MM,
} from './canvas-geometry';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

interface BoxSpec {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z?: number;
  locked?: boolean;
  visible?: boolean;
  rotation?: number;
}

function box(spec: BoxSpec): TagLayer {
  return {
    id: spec.id,
    type: 'shape',
    x_mm: spec.x,
    y_mm: spec.y,
    width_mm: spec.w,
    height_mm: spec.h,
    rotation_deg: spec.rotation ?? 0,
    z_index: spec.z ?? 1,
    locked: spec.locked ?? false,
    visible: spec.visible ?? true,
    slot_binding: null,
    text_override: null,
    props: defaultShapeProps(),
  };
}

function group(
  spec: BoxSpec & { children: string[] },
): TagLayer {
  return {
    ...box(spec),
    type: 'group',
    props: { kind: 'group', children: spec.children },
  };
}

/**
 * A block shaped like the ones the editor builds: a group over two children,
 * one of which is itself a group over a single text layer.
 *
 *   g1 (0,0 40x40)
 *     a  (0,0 10x10)
 *     g2 (20,20 20x20)
 *       b (20,20 20x20)
 */
function nested(): TagLayer[] {
  return [
    box({ id: 'a', x: 0, y: 0, w: 10, h: 10, z: 1 }),
    { ...box({ id: 'b', x: 20, y: 20, w: 20, h: 20, z: 2 }), type: 'text', props: defaultTextProps() },
    group({ id: 'g2', x: 20, y: 20, w: 20, h: 20, z: 3, children: ['b'] }),
    group({ id: 'g1', x: 0, y: 0, w: 40, h: 40, z: 4, children: ['a', 'g2'] }),
  ];
}

function byId(layers: TagLayer[], id: string): TagLayer {
  const found = layers.find((l) => l.id === id);
  if (!found) throw new Error(`no layer ${id}`);
  return found;
}

// ---------------------------------------------------------------------------
// Ancestry
// ---------------------------------------------------------------------------

describe('descendantsOf / ancestorsOf / topLevelOf', () => {
  it('walks a group through its nested groups', () => {
    expect(descendantsOf(nested(), 'g1').sort()).toEqual(['a', 'b', 'g2']);
    expect(descendantsOf(nested(), 'g2')).toEqual(['b']);
  });

  it('returns nothing for a leaf', () => {
    expect(descendantsOf(nested(), 'a')).toEqual([]);
  });

  it('lists ancestors innermost first', () => {
    expect(ancestorsOf(nested(), 'b')).toEqual(['g2', 'g1']);
    expect(ancestorsOf(nested(), 'a')).toEqual(['g1']);
    expect(ancestorsOf(nested(), 'g1')).toEqual([]);
  });

  it('resolves the outermost ancestor, or the layer itself', () => {
    expect(topLevelOf(nested(), 'b')).toBe('g1');
    expect(topLevelOf(nested(), 'g2')).toBe('g1');
    expect(topLevelOf(nested(), 'g1')).toBe('g1');
  });

  it('does not loop when a document names itself as its own child', () => {
    const layers = [group({ id: 'g', x: 0, y: 0, w: 10, h: 10, children: ['g'] })];
    expect(descendantsOf(layers, 'g')).toEqual([]);
    expect(ancestorsOf(layers, 'g')).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Moving (D38)
// ---------------------------------------------------------------------------

describe('moveLayers', () => {
  it('moves a group and every descendant by the same delta', () => {
    const next = moveLayers(nested(), ['g1'], 5, -2);
    expect(byId(next, 'g1').x_mm).toBe(5);
    expect(byId(next, 'a').x_mm).toBe(5);
    expect(byId(next, 'g2').x_mm).toBe(25);
    expect(byId(next, 'b').y_mm).toBe(18);
  });

  it('moves each layer exactly once when a group and its child are both asked for', () => {
    const next = moveLayers(nested(), ['g1', 'a'], 10, 0);
    expect(byId(next, 'a').x_mm).toBe(10);
  });

  it('moves a child without touching its group', () => {
    const next = moveLayers(nested(), ['a'], 3, 3);
    expect(byId(next, 'a').x_mm).toBe(3);
    expect(byId(next, 'g1').x_mm).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Transforming (D38)
// ---------------------------------------------------------------------------

describe('transformGroup', () => {
  it('scales descendant positions and sizes about the group origin', () => {
    const next = transformGroup(nested(), 'g1', {
      x_mm: 0,
      y_mm: 0,
      width_mm: 80,
      height_mm: 40,
      rotation_deg: 0,
    });
    const a = byId(next, 'a');
    expect(a.x_mm).toBe(0);
    expect(a.width_mm).toBe(20);
    expect(a.height_mm).toBe(10);
    const b = byId(next, 'b');
    expect(b.x_mm).toBe(40);
    expect(b.y_mm).toBe(20);
    expect(b.width_mm).toBe(40);
  });

  it('carries a move as well as a resize', () => {
    const next = transformGroup(nested(), 'g1', {
      x_mm: 100,
      y_mm: 100,
      width_mm: 40,
      height_mm: 40,
      rotation_deg: 0,
    });
    expect(byId(next, 'a').x_mm).toBe(100);
    expect(byId(next, 'b').x_mm).toBe(120);
  });

  it('rotates descendants about the group origin and adds the delta to each rotation', () => {
    const next = transformGroup(nested(), 'g1', {
      x_mm: 0,
      y_mm: 0,
      width_mm: 40,
      height_mm: 40,
      rotation_deg: 90,
    });
    const b = byId(next, 'b');
    // (20, 20) turned a quarter turn clockwise about the origin is (-20, 20).
    expect(b.x_mm).toBeCloseTo(-20, 6);
    expect(b.y_mm).toBeCloseTo(20, 6);
    expect(b.rotation_deg).toBeCloseTo(90, 6);
  });

  it('leaves descendants alone when the group had no extent to scale from', () => {
    const layers = [
      box({ id: 'c', x: 5, y: 5, w: 2, h: 2 }),
      group({ id: 'g', x: 5, y: 5, w: 0, h: 0, children: ['c'] }),
    ];
    const next = transformGroup(layers, 'g', {
      x_mm: 5,
      y_mm: 5,
      width_mm: 10,
      height_mm: 10,
      rotation_deg: 0,
    });
    expect(byId(next, 'c').width_mm).toBe(2);
  });

  it('does nothing when the id is not a group', () => {
    const layers = nested();
    expect(
      transformGroup(layers, 'a', {
        x_mm: 0,
        y_mm: 0,
        width_mm: 1,
        height_mm: 1,
        rotation_deg: 0,
      }),
    ).toEqual(layers);
  });
});

describe('refitAncestors', () => {
  it('recomputes every ancestor box from its own children, innermost first', () => {
    const moved = moveLayers(nested(), ['b'], 20, 20);
    const next = refitAncestors(moved, 'b');
    const g2 = byId(next, 'g2');
    expect([g2.x_mm, g2.y_mm, g2.width_mm, g2.height_mm]).toEqual([40, 40, 20, 20]);
    const g1 = byId(next, 'g1');
    expect([g1.x_mm, g1.y_mm, g1.width_mm, g1.height_mm]).toEqual([0, 0, 60, 60]);
  });

  it('leaves a top-level layer untouched', () => {
    const layers = [box({ id: 'a', x: 1, y: 1, w: 2, h: 2 })];
    expect(refitAncestors(layers, 'a')).toEqual(layers);
  });
});

// ---------------------------------------------------------------------------
// Removing and ungrouping (D39)
// ---------------------------------------------------------------------------

describe('removeLayers', () => {
  it('deletes a group with its descendants', () => {
    const next = removeLayers(nested(), ['g2']);
    expect(next.map((l) => l.id).sort()).toEqual(['a', 'g1']);
  });

  it('prunes the deleted child from its parent and refits the boxes', () => {
    const next = removeLayers(nested(), ['a']);
    const g1 = byId(next, 'g1');
    expect(g1.props.kind === 'group' && g1.props.children).toEqual(['g2']);
    expect([g1.x_mm, g1.y_mm, g1.width_mm, g1.height_mm]).toEqual([20, 20, 20, 20]);
  });
});

describe('ungroupLayers', () => {
  it('frees the children and hands the parent the freed ids', () => {
    const { layers, ids } = ungroupLayers(nested(), ['g2']);
    expect(layers.find((l) => l.id === 'g2')).toBeUndefined();
    const g1 = layers.find((l) => l.id === 'g1');
    expect(g1?.props.kind === 'group' && g1.props.children).toEqual(['a', 'b']);
    expect(ids).toEqual(['b']);
  });
});

// ---------------------------------------------------------------------------
// Marquee (D36)
// ---------------------------------------------------------------------------

describe('marqueeHits', () => {
  const flat = () => [
    box({ id: 'p', x: 0, y: 0, w: 10, h: 10, z: 1 }),
    box({ id: 'q', x: 20, y: 0, w: 10, h: 10, z: 2 }),
    box({ id: 'r', x: 60, y: 60, w: 10, h: 10, z: 3 }),
  ];

  it('selects everything the band touches, not only what it encloses', () => {
    const band = bandBetween({ x_mm: 5, y_mm: 5 }, { x_mm: 25, y_mm: 6 });
    expect(marqueeHits(flat(), band, { insideGroupId: null })).toEqual(['p', 'q']);
  });

  it('normalises a band drawn right to left and bottom to top', () => {
    const band = bandBetween({ x_mm: 25, y_mm: 6 }, { x_mm: 5, y_mm: 5 });
    expect(marqueeHits(flat(), band, { insideGroupId: null })).toEqual(['p', 'q']);
  });

  it('represents a child by its outermost group at the top level', () => {
    const band = bandBetween({ x_mm: 0, y_mm: 0 }, { x_mm: 5, y_mm: 5 });
    expect(marqueeHits(nested(), band, { insideGroupId: null })).toEqual(['g1']);
  });

  it("scopes to the direct children of the group being edited", () => {
    const band = bandBetween({ x_mm: 0, y_mm: 0 }, { x_mm: 30, y_mm: 30 });
    expect(marqueeHits(nested(), band, { insideGroupId: 'g1' })).toEqual(['a', 'g2']);
  });

  it('ignores hidden and locked layers', () => {
    const layers = [
      box({ id: 'p', x: 0, y: 0, w: 10, h: 10, visible: false }),
      box({ id: 'q', x: 0, y: 0, w: 10, h: 10, locked: true, z: 2 }),
    ];
    const band = bandBetween({ x_mm: 0, y_mm: 0 }, { x_mm: 10, y_mm: 10 });
    expect(marqueeHits(layers, band, { insideGroupId: null })).toEqual([]);
  });

  it('returns nothing for a band that touches nothing', () => {
    const band = bandBetween({ x_mm: 40, y_mm: 40 }, { x_mm: 45, y_mm: 45 });
    expect(marqueeHits(flat(), band, { insideGroupId: null })).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Hit testing (D37, D40)
// ---------------------------------------------------------------------------

describe('topmostChildAt', () => {
  it('picks the highest child under the point', () => {
    const layers = [
      box({ id: 'lo', x: 0, y: 0, w: 20, h: 20, z: 1 }),
      box({ id: 'hi', x: 0, y: 0, w: 20, h: 20, z: 5 }),
      group({ id: 'g', x: 0, y: 0, w: 20, h: 20, z: 9, children: ['lo', 'hi'] }),
    ];
    expect(topmostChildAt(layers, 'g', 5, 5)).toBe('hi');
  });

  it('skips locked and hidden children', () => {
    const layers = [
      box({ id: 'lo', x: 0, y: 0, w: 20, h: 20, z: 1 }),
      box({ id: 'hi', x: 0, y: 0, w: 20, h: 20, z: 5, locked: true }),
      group({ id: 'g', x: 0, y: 0, w: 20, h: 20, z: 9, children: ['lo', 'hi'] }),
    ];
    expect(topmostChildAt(layers, 'g', 5, 5)).toBe('lo');
  });

  it('returns null outside every child', () => {
    expect(topmostChildAt(nested(), 'g1', 15, 15)).toBeNull();
  });
});

describe('hitLayerAt', () => {
  it('resolves a child to its outermost group when nothing is entered', () => {
    expect(hitLayerAt(nested(), 5, 5, new Set())).toBe('g1');
  });

  it('stops at the first group that has not been entered', () => {
    expect(hitLayerAt(nested(), 25, 25, new Set(['g1']))).toBe('g2');
  });

  it('reaches the layer itself once every ancestor is entered', () => {
    expect(hitLayerAt(nested(), 25, 25, new Set(['g1', 'g2']))).toBe('b');
  });

  it('returns null on empty canvas', () => {
    expect(hitLayerAt(nested(), 200, 200, new Set())).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Z order (D40)
// ---------------------------------------------------------------------------

describe('reorderZ', () => {
  /** Three top-level things, the middle one a group over two children. */
  const stack = () => [
    box({ id: 'x', x: 0, y: 0, w: 5, h: 5, z: 1 }),
    box({ id: 'c1', x: 0, y: 0, w: 5, h: 5, z: 2 }),
    box({ id: 'c2', x: 0, y: 0, w: 5, h: 5, z: 3 }),
    group({ id: 'g', x: 0, y: 0, w: 5, h: 5, z: 4, children: ['c1', 'c2'] }),
    box({ id: 'y', x: 0, y: 0, w: 5, h: 5, z: 5 }),
  ];

  const order = (layers: TagLayer[]) =>
    [...layers].sort((a, b) => a.z_index - b.z_index).map((l) => l.id);

  it('sends a group and its children to the front as one block', () => {
    const next = reorderZ(stack(), ['g'], 'front');
    expect(order(next)).toEqual(['x', 'y', 'c1', 'c2', 'g']);
  });

  it('sends a group to the back as one block', () => {
    const next = reorderZ(stack(), ['g'], 'back');
    expect(order(next)).toEqual(['c1', 'c2', 'g', 'x', 'y']);
  });

  it('steps one place forward and one place backward', () => {
    expect(order(reorderZ(stack(), ['g'], 'forward'))).toEqual([
      'x',
      'y',
      'c1',
      'c2',
      'g',
    ]);
    expect(order(reorderZ(stack(), ['g'], 'backward'))).toEqual([
      'c1',
      'c2',
      'g',
      'x',
      'y',
    ]);
  });

  it('renumbers z_index contiguously from 1', () => {
    const next = reorderZ(stack(), ['x'], 'front');
    expect([...next].map((l) => l.z_index).sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5]);
  });

  it('treats a selected child as its top-level block', () => {
    expect(order(reorderZ(stack(), ['c1'], 'back'))).toEqual([
      'c1',
      'c2',
      'g',
      'x',
      'y',
    ]);
  });
});

// ---------------------------------------------------------------------------
// Cloning (D39)
// ---------------------------------------------------------------------------

describe('cloneLayers', () => {
  let seq = 0;
  const newId = () => `n${(seq += 1)}`;

  it('clones a group with its descendants and remaps children onto the copies', () => {
    seq = 0;
    const { layers, ids } = cloneLayers(nested(), ['g1'], newId, 5);
    expect(layers).toHaveLength(4);
    expect(ids).toHaveLength(1);

    const copy = byId(layers, ids[0]);
    expect(copy.props.kind === 'group' && copy.props.children).toHaveLength(2);
    const childIds = copy.props.kind === 'group' ? copy.props.children : [];
    // Every remapped child is one of the clones, never an original.
    for (const childId of childIds) {
      expect(layers.some((l) => l.id === childId)).toBe(true);
      expect(['a', 'b', 'g2']).not.toContain(childId);
    }
  });

  it('offsets every clone by the same amount', () => {
    seq = 0;
    const { layers, ids } = cloneLayers(nested(), ['g1'], newId, 5);
    expect(byId(layers, ids[0]).x_mm).toBe(5);
    const child = layers.find((l) => l.width_mm === 10);
    expect(child?.x_mm).toBe(5);
  });

  it('stacks the clones above everything already on the canvas', () => {
    seq = 0;
    const { layers } = cloneLayers(nested(), ['g1'], newId, 5);
    expect(Math.min(...layers.map((l) => l.z_index))).toBeGreaterThan(4);
  });

  it('clones a plain layer without inventing a group', () => {
    seq = 0;
    const { layers, ids } = cloneLayers(nested(), ['a'], newId, 2);
    expect(layers).toHaveLength(1);
    expect(byId(layers, ids[0]).x_mm).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Viewport (D33, D34)
// ---------------------------------------------------------------------------

describe('zoomAt', () => {
  const view = { zoom: 1, panX: 100, panY: 50 };

  it('keeps the point under the cursor under the cursor', () => {
    const before = stageToMm(view, 400, 300);
    const next = zoomAt(view, { x: 400, y: 300 }, 1.1, { min: 0.1, max: 8 });
    const after = stageToMm(next, 400, 300);
    expect(after.x_mm).toBeCloseTo(before.x_mm, 6);
    expect(after.y_mm).toBeCloseTo(before.y_mm, 6);
  });

  it('multiplies the zoom by the factor', () => {
    expect(zoomAt(view, { x: 0, y: 0 }, 1.1, { min: 0.1, max: 8 }).zoom).toBeCloseTo(1.1, 6);
  });

  it('clamps at both ends and leaves the pan alone when it cannot zoom further', () => {
    const atMax = zoomAt({ zoom: 8, panX: 10, panY: 10 }, { x: 5, y: 5 }, 2, {
      min: 0.1,
      max: 8,
    });
    expect(atMax).toEqual({ zoom: 8, panX: 10, panY: 10 });

    const atMin = zoomAt({ zoom: 0.1, panX: 10, panY: 10 }, { x: 5, y: 5 }, 0.5, {
      min: 0.1,
      max: 8,
    });
    expect(atMin.zoom).toBe(0.1);
  });
});

describe('fitView', () => {
  it('centres the artboard inside the container with the margin left over', () => {
    const view = fitView(
      { width: 800, height: 600 },
      { width_mm: 95, height_mm: 130 },
      32,
      { min: 0.1, max: 8 },
    );
    const scale = CANVAS_PX_PER_MM * view.zoom;
    expect(95 * scale).toBeLessThanOrEqual(800 - 64 + 0.001);
    expect(130 * scale).toBeCloseTo(600 - 64, 6);
    expect(view.panX).toBeCloseTo((800 - 95 * scale) / 2, 6);
    expect(view.panY).toBeCloseTo((600 - 130 * scale) / 2, 6);
  });

  it('falls back to 100% before the container has been measured', () => {
    const view = fitView({ width: 0, height: 0 }, { width_mm: 95, height_mm: 130 }, 32, {
      min: 0.1,
      max: 8,
    });
    expect(view.zoom).toBe(1);
  });
});

describe('stageToMm', () => {
  it('undoes the pan and the zoom', () => {
    const point = stageToMm({ zoom: 2, panX: 30, panY: 10 }, 30 + 2 * CANVAS_PX_PER_MM * 5, 10);
    expect(point.x_mm).toBeCloseTo(5, 6);
    expect(point.y_mm).toBeCloseTo(0, 6);
  });
});

// ---------------------------------------------------------------------------
// Layers panel drag and drop (D43)
// ---------------------------------------------------------------------------

/**
 * A block plus a loose layer, the shape the panel drags things between.
 *
 *   x  (top level, z 4)
 *   G  (0,0 40x20, z 3)
 *     c2 (20,0 20x20, z 2)
 *     c1 (0,0 10x10, z 1)
 *
 * Panel order is z descending, so the rows read x, G, c2, c1.
 */
function panelDoc(): TagLayer[] {
  return [
    box({ id: 'c1', x: 0, y: 0, w: 10, h: 10, z: 1 }),
    box({ id: 'c2', x: 20, y: 0, w: 20, h: 20, z: 2 }),
    group({ id: 'G', x: 0, y: 0, w: 40, h: 20, z: 3, children: ['c1', 'c2'] }),
    box({ id: 'x', x: 60, y: 60, w: 10, h: 10, z: 4 }),
  ];
}

describe('panelRows', () => {
  it('reads top down in z order with children indented under their group', () => {
    expect(panelRows(panelDoc())).toEqual([
      { id: 'x', parentId: null, depth: 0 },
      { id: 'G', parentId: null, depth: 0 },
      { id: 'c2', parentId: 'G', depth: 1 },
      { id: 'c1', parentId: 'G', depth: 1 },
    ]);
  });

  it('indents a nested group under its parent', () => {
    expect(panelRows(nested())).toEqual([
      { id: 'g1', parentId: null, depth: 0 },
      { id: 'g2', parentId: 'g1', depth: 1 },
      { id: 'b', parentId: 'g2', depth: 2 },
      { id: 'a', parentId: 'g1', depth: 1 },
    ]);
  });
});

describe('panelDropTarget', () => {
  it('drops above the row when the pointer is in its top edge', () => {
    expect(panelDropTarget(panelDoc(), 'c1', 0.1)).toEqual({
      parentId: 'G',
      beforeId: 'c1',
    });
  });

  it('drops below the row when the pointer is in its bottom edge', () => {
    expect(panelDropTarget(panelDoc(), 'c2', 0.9)).toEqual({
      parentId: 'G',
      beforeId: 'c1',
    });
  });

  it('drops at the end of the list below the last row', () => {
    expect(panelDropTarget(panelDoc(), 'c1', 0.9)).toEqual({
      parentId: 'G',
      beforeId: null,
    });
  });

  it('joins the group when the pointer is over the body of a group row', () => {
    expect(panelDropTarget(panelDoc(), 'G', 0.5)).toEqual({
      parentId: 'G',
      beforeId: null,
    });
  });

  it('stays beside a group when the pointer is on its edge', () => {
    expect(panelDropTarget(panelDoc(), 'G', 0.1)).toEqual({
      parentId: null,
      beforeId: 'G',
    });
    expect(panelDropTarget(panelDoc(), 'G', 0.9)).toEqual({
      parentId: null,
      beforeId: null,
    });
  });

  it('answers nothing for a row that is not there', () => {
    expect(panelDropTarget(panelDoc(), 'nope', 0.5)).toBeNull();
  });
});

describe('reparentLayer', () => {
  it('joins the group when dropped between two of its children', () => {
    const out = reparentLayer(panelDoc(), 'x', { parentId: 'G', beforeId: 'c1' });

    expect(panelRows(out).map((row) => row.id)).toEqual(['G', 'c2', 'x', 'c1']);
    expect((byId(out, 'G').props as { children: string[] }).children).toEqual([
      'c1',
      'x',
      'c2',
    ]);
  });

  it('appends as the last child when dropped onto the group row', () => {
    const out = reparentLayer(panelDoc(), 'x', { parentId: 'G', beforeId: null });

    expect(panelRows(out).map((row) => row.id)).toEqual(['G', 'c2', 'c1', 'x']);
    expect((byId(out, 'G').props as { children: string[] }).children[0]).toBe('x');
  });

  it('leaves the group when dropped between two top-level rows', () => {
    const out = reparentLayer(panelDoc(), 'c2', { parentId: null, beforeId: 'G' });

    expect(panelRows(out).map((row) => row.id)).toEqual(['x', 'c2', 'G', 'c1']);
    expect((byId(out, 'G').props as { children: string[] }).children).toEqual(['c1']);
  });

  it('refits the group it left', () => {
    const out = reparentLayer(panelDoc(), 'c2', { parentId: null, beforeId: 'G' });
    const g = byId(out, 'G');

    expect([g.x_mm, g.y_mm, g.width_mm, g.height_mm]).toEqual([0, 0, 10, 10]);
  });

  it('refits the group it joined', () => {
    const out = reparentLayer(panelDoc(), 'x', { parentId: 'G', beforeId: null });
    const g = byId(out, 'G');

    expect([g.x_mm, g.y_mm, g.width_mm, g.height_mm]).toEqual([0, 0, 70, 70]);
  });

  it('carries a whole subtree when a group row is dragged', () => {
    const layers = [...nested(), box({ id: 'top', x: 60, y: 60, w: 10, h: 10, z: 5 })];
    const out = reparentLayer(layers, 'g2', { parentId: null, beforeId: 'g1' });

    expect(panelRows(out).map((row) => row.id)).toEqual(['top', 'g2', 'b', 'g1', 'a']);
    expect((byId(out, 'g1').props as { children: string[] }).children).toEqual(['a']);
  });

  it('refuses a drop into its own subtree', () => {
    const layers = nested();

    expect(reparentLayer(layers, 'g1', { parentId: 'g2', beforeId: null })).toBe(layers);
    expect(reparentLayer(layers, 'g1', { parentId: 'g1', beforeId: null })).toBe(layers);
  });

  it('renumbers z 1..n so the panel order is the stacking order', () => {
    const out = reparentLayer(panelDoc(), 'x', { parentId: 'G', beforeId: 'c1' });
    const rows = panelRows(out).map((row) => byId(out, row.id).z_index);

    expect(rows).toEqual([4, 3, 2, 1]);
  });

  it('reorders a locked layer, because a lock protects the canvas and not the stack', () => {
    const layers = panelDoc().map((layer) =>
      layer.id === 'x' ? { ...layer, locked: true } : layer,
    );
    const out = reparentLayer(layers, 'x', { parentId: 'G', beforeId: null });

    expect((byId(out, 'G').props as { children: string[] }).children).toContain('x');
    expect(byId(out, 'x').locked).toBe(true);
  });

  it('leaves the document alone when the layer is not there', () => {
    const layers = panelDoc();

    expect(reparentLayer(layers, 'nope', { parentId: 'G', beforeId: null })).toBe(layers);
  });
});
