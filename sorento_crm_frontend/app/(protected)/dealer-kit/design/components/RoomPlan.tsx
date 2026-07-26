'use client';

import { useCallback, useMemo, useRef, useState } from 'react';

import { cn } from '@/lib/utils';
import {
  DEFAULT_GRID_MM,
  areaSquareMetres,
  boxCorners,
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

const PADDING_MM = 400;

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
    { kind: 'corner'; index: number } | { kind: 'box'; id: string } | null
  >(null);

  const bounds = useMemo(() => {
    const raw = roomBounds(outline);
    return {
      minX: raw.minX - PADDING_MM,
      minY: raw.minY - PADDING_MM,
      width: Math.max(1000, raw.maxX - raw.minX + PADDING_MM * 2),
      height: Math.max(1000, raw.maxY - raw.minY + PADDING_MM * 2),
    };
  }, [outline]);

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

      const box = boxes.find((candidate) => candidate.id === dragging.id);
      if (box && onMoveBox) {
        // Drag by the centre: grabbing a corner makes a unit jump on pickup.
        onMoveBox(dragging.id, x - box.width / 2, y - box.depth / 2);
      }
    },
    [dragging, outline, boxes, onOutlineChange, onMoveBox, toMillimetres],
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
        onPointerUp={() => setDragging(null)}
        onPointerLeave={() => setDragging(null)}
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
            const offsetX = midX < centroid.x ? -180 : 180;
            const offsetY = midY < centroid.y ? -180 : 180;
            const horizontal = Math.abs(next.x - point.x) >= Math.abs(next.y - point.y);

            return (
              <text
                key={`wall-${index}`}
                x={midX + (horizontal ? 0 : offsetX)}
                y={midY + (horizontal ? offsetY : 0)}
                textAnchor="middle"
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
                setDragging({ kind: 'box', id: box.id });
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
              <text
                x={centre.x}
                y={centre.y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-foreground"
                style={{ fontSize: 140 }}
              >
                {box.label}
              </text>
            </g>
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
              setDragging({ kind: 'corner', index });
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
