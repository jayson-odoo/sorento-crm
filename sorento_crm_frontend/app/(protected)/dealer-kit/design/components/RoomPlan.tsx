'use client';

import { useCallback, useMemo, useRef, useState } from 'react';

import { cn } from '@/lib/utils';
import {
  DEFAULT_GRID_MM,
  areaSquareMetres,
  boxCorners,
  moveWall,
  roomBounds,
  snapToGrid,
  type Box,
  type Point,
} from '@/lib/dealer-kit/roomGeometry';

/**
 * The room, from above.
 *
 * Drawing is always available, never a fallback nobody can reach: an upload
 * that traces the walls badly must leave the user dragging corners, not stuck
 * (AC-R4). So this view is the primitive and detection merely seeds it.
 *
 * Everything is millimetres. The SVG viewBox does the scaling, which means no
 * pixel-per-mm constant is threaded through the drag maths - the one place
 * these things usually go wrong.
 */

/**
 * Breathing room around the outline, in millimetres.
 *
 * Wide enough for a wall label to sit OUTSIDE the room without being clipped by
 * the viewBox: the labels read "4000 mm" at 150 units, so 400 left half of one
 * hanging off the edge.
 */
const PADDING_MM = 1000;

/** The viewBox that shows the whole outline with breathing room, in millimetres. */
function viewBoxFor(outline: Point[]) {
  const raw = roomBounds(outline);
  return {
    minX: raw.minX - PADDING_MM,
    minY: raw.minY - PADDING_MM,
    width: Math.max(1000, raw.maxX - raw.minX + PADDING_MM * 2),
    height: Math.max(1000, raw.maxY - raw.minY + PADDING_MM * 2),
  };
}

export interface RoomPlanProps {
  outline: Point[];
  boxes: (Box & { id: string; label: string })[];
  selectedBoxId?: string | null;
  onOutlineChange: (outline: Point[]) => void;
  onMoveBox?: (boxId: string, x: number, y: number) => void;
  onSelectBox?: (boxId: string) => void;
  /** A traced floor plan sits behind the grid as a guide (AC-R4). */
  backgroundUrl?: string | null;
}

export function RoomPlan({
  outline,
  boxes,
  selectedBoxId,
  onOutlineChange,
  onMoveBox,
  onSelectBox,
  backgroundUrl,
}: RoomPlanProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [dragging, setDragging] = useState<
    | { kind: 'corner'; index: number }
    | { kind: 'box'; id: string }
    | { kind: 'wall'; index: number }
    | null
  >(null);

  /**
   * Where a wall drag began, and the outline it began from.
   *
   * A ref, not state, and deliberately so. Moving a wall is a RELATIVE gesture,
   * so it needs a fixed origin; keeping that origin in state meant every
   * pointermove within one React batch still saw the previous origin and
   * re-applied the same delta. A 60px drag came out as 7 metres.
   *
   * Anchoring to the outline as it was at pointerdown also makes the drag
   * idempotent: the same cursor position always yields the same wall, however
   * many move events arrived on the way there.
   */
  const wallDragOrigin = useRef<{ x: number; y: number; outline: Point[] } | null>(null);

  const liveBounds = useMemo(() => viewBoxFor(outline), [outline]);

  /**
   * The viewBox is FROZEN for the duration of a drag.
   *
   * Otherwise the drag chases itself: growing the room grows the bounds, the
   * bounds set the millimetres-per-pixel scale, and the same cursor position
   * then means MORE millimetres than it did a frame ago. Pulling a wall 60px
   * moved it 3.7 metres instead of 0.7, and a corner ran away from the pointer.
   *
   * The cost is that a room dragged past the frozen edge is briefly clipped;
   * the padding covers ordinary gestures, and the scale settles on drop.
   */
  const frozenBounds = useRef<ReturnType<typeof viewBoxFor> | null>(null);
  const bounds = dragging ? (frozenBounds.current ?? liveBounds) : liveBounds;

  /** Screen point -> millimetres, via the SVG's own transform. */
  const toMillimetres = useCallback((event: React.PointerEvent): Point | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const local = point.matrixTransform(ctm.inverse());
    return { x: local.x, y: local.y };
  }, []);

  const handleMove = useCallback(
    (event: React.PointerEvent) => {
      if (!dragging) return;
      const position = toMillimetres(event);
      if (!position) return;

      const x = snapToGrid(position.x, DEFAULT_GRID_MM);
      const y = snapToGrid(position.y, DEFAULT_GRID_MM);

      if (dragging.kind === 'corner') {
        const next = outline.map((point, index) =>
          index === dragging.index ? { x, y } : point,
        );
        onOutlineChange(next);
        return;
      }

      if (dragging.kind === 'wall') {
        // Always measured from the gesture's origin against the outline as it
        // was then. Measuring against the CURRENT outline would fold each move
        // into the next and run the wall away from the cursor.
        const origin = wallDragOrigin.current;
        if (!origin) return;
        onOutlineChange(
          moveWall(
            origin.outline,
            dragging.index,
            position.x - origin.x,
            position.y - origin.y,
          ),
        );
        return;
      }

      const box = boxes.find((candidate) => candidate.id === dragging.id);
      if (box && onMoveBox) {
        // Drag by the centre: grabbing a corner makes a unit jump on pickup.
        onMoveBox(dragging.id, x - box.width / 2, y - box.depth / 2);
      }
    },
    [dragging, outline, boxes, onOutlineChange, onMoveBox, toMillimetres],
  );

  const endDrag = useCallback(() => {
    setDragging(null);
    wallDragOrigin.current = null;
    frozenBounds.current = null;
  }, []);

  /** Freeze the scale, then start the gesture. Order matters: the first
      pointermove already needs the frozen viewBox. */
  const beginDrag = useCallback(
    (next: NonNullable<typeof dragging>) => {
      frozenBounds.current = viewBoxFor(outline);
      setDragging(next);
    },
    [outline],
  );

  const area = areaSquareMetres(outline);
  /** Only used to decide which side of a wall its label sits on. */
  const centroid = useMemo(() => {
    if (outline.length === 0) return { x: 0, y: 0 };
    return {
      x: outline.reduce((total, point) => total + point.x, 0) / outline.length,
      y: outline.reduce((total, point) => total + point.y, 0) / outline.length,
    };
  }, [outline]);
  const path =
    outline.length >= 3
      ? `${outline.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')} Z`
      : '';

  return (
    <div className="relative w-full overflow-hidden rounded-lg border border-border bg-muted/20">
      <svg
        ref={svgRef}
        viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
        className="h-full w-full touch-none"
        style={{ aspectRatio: `${bounds.width} / ${bounds.height}` }}
        onPointerMove={handleMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
        data-dk-room-plan
      >
        <defs>
          <pattern
            id="dk-grid"
            width={DEFAULT_GRID_MM * 10}
            height={DEFAULT_GRID_MM * 10}
            patternUnits="userSpaceOnUse"
          >
            <path
              d={`M ${DEFAULT_GRID_MM * 10} 0 L 0 0 0 ${DEFAULT_GRID_MM * 10}`}
              fill="none"
              stroke="currentColor"
              strokeWidth={6}
              className="text-border"
            />
          </pattern>
        </defs>

        {backgroundUrl && (
          <image
            href={backgroundUrl}
            x={bounds.minX}
            y={bounds.minY}
            width={bounds.width}
            height={bounds.height}
            opacity={0.35}
            preserveAspectRatio="xMidYMid meet"
          />
        )}

        <rect
          x={bounds.minX}
          y={bounds.minY}
          width={bounds.width}
          height={bounds.height}
          fill="url(#dk-grid)"
        />

        {path && (
          <path
            d={path}
            className="fill-background stroke-foreground"
            strokeWidth={24}
            strokeLinejoin="round"
          />
        )}

        {/*
          A wall length beside every wall (AC-R1). Without it a user drags a
          corner and has no idea whether they just made a 3.6m run or a 4.1m
          one - and "roughly right" is how a worktop gets ordered 200mm short.
          Derived from the outline on every render, so it is live during a drag
          rather than a value that catches up on drop.
        */}
        {outline.length >= 3 &&
          outline.map((point, index) => {
            const next = outline[(index + 1) % outline.length];
            const length = Math.round(Math.hypot(next.x - point.x, next.y - point.y));
            if (length === 0) return null;

            // Nudged off the wall, on the side away from the room's middle, so
            // the label never sits on top of the line it measures.
            const midX = (point.x + next.x) / 2;
            const midY = (point.y + next.y) / 2;
            const horizontal = Math.abs(next.x - point.x) >= Math.abs(next.y - point.y);
            const outward = horizontal
              ? (midY < centroid.y ? -1 : 1)
              : (midX < centroid.x ? -1 : 1);

            // A vertical wall's label is set BESIDE the wall and anchored at its
            // near edge. Centring it on a point 180mm away is not enough: the
            // text is over a metre wide at this scale, so half of it lands back
            // on the wall it measures.
            const gap = 140;

            return (
              <text
                key={`wall-${index}`}
                x={midX + (horizontal ? 0 : outward * gap)}
                y={midY + (horizontal ? outward * 260 : 0)}
                textAnchor={horizontal ? 'middle' : outward < 0 ? 'end' : 'start'}
                dominantBaseline="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 150 }}
              >
                {length} mm
              </text>
            );
          })}

        {boxes.map((box) => {
          const corners = boxCorners(box);
          const points = corners.map((corner) => `${corner.x},${corner.y}`).join(' ');
          const centre = {
            x: corners.reduce((total, corner) => total + corner.x, 0) / 4,
            y: corners.reduce((total, corner) => total + corner.y, 0) / 4,
          };
          return (
            <g
              key={box.id}
              onPointerDown={(event) => {
                event.stopPropagation();
                onSelectBox?.(box.id);
                beginDrag({ kind: 'box', id: box.id });
              }}
              className="cursor-move"
              data-dk-plan-box={box.id}
            >
              <polygon
                points={points}
                className={cn(
                  'stroke-primary',
                  box.id === selectedBoxId ? 'fill-primary/40' : 'fill-primary/15',
                )}
                strokeWidth={16}
              />
              {/*
                Trimmed to what the footprint can hold. SVG text does not wrap
                or clip on its own, so a long product code spills across the
                whole plan and covers the room it is meant to label. Roughly
                half the glyph width per character at this size.
              */}
              <text
                x={centre.x}
                y={centre.y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-foreground"
                style={{ fontSize: 110 }}
              >
                {(() => {
                  const fits = Math.max(3, Math.floor(Math.min(box.width, box.depth) / 55));
                  return box.label.length > fits
                    ? `${box.label.slice(0, fits - 1)}…`
                    : box.label;
                })()}
              </text>
              <title>{box.label}</title>
            </g>
          );
        })}

        {/* A fat invisible line over each wall. Dragging a wall is what somebody
            means by "this wall is 200mm too far out"; doing it by moving two
            corners is fiddly and lets the wall go out of square. */}
        {outline.length >= 3 &&
          outline.map((point, index) => {
            const next = outline[(index + 1) % outline.length];
            const horizontal = Math.abs(next.x - point.x) >= Math.abs(next.y - point.y);
            return (
              <line
                key={`wall-handle-${index}`}
                x1={point.x}
                y1={point.y}
                x2={next.x}
                y2={next.y}
                stroke="transparent"
                strokeWidth={160}
                className={horizontal ? 'cursor-ns-resize' : 'cursor-ew-resize'}
                data-dk-room-wall={index}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  const start = toMillimetres(event);
                  if (!start) return;
                  wallDragOrigin.current = { x: start.x, y: start.y, outline };
                  beginDrag({ kind: 'wall', index });
                }}
              />
            );
          })}

        {outline.map((point, index) => (
          <circle
            key={`${point.x}-${point.y}-${index}`}
            cx={point.x}
            cy={point.y}
            r={70}
            className="cursor-grab fill-background stroke-primary"
            strokeWidth={20}
            onPointerDown={(event) => {
              event.stopPropagation();
              beginDrag({ kind: 'corner', index });
            }}
            data-dk-room-corner={index}
          />
        ))}
      </svg>

      <div className="pointer-events-none absolute bottom-2 end-2 rounded bg-background/90 px-2 py-1 text-xs text-muted-foreground">
        {/* Derived, never stored (AC-R5). */}
        {area.toFixed(1)} m<sup>2</sup>
      </div>
    </div>
  );
}
