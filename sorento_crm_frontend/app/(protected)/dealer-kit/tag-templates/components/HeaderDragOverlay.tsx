'use client';

/**
 * PRICETAG-HEADER-DRAG (owner 9 Nov: "I want to drag and place it at other places"): a handle over the
 * selected accessories box's header. Dragging it moves the HEADER, not the box, anywhere inside the
 * box, with snapping guides; the drop is stored as `headerPos` in box millimetres, the spot every
 * render (canvas, preview, print) reads through `accessoryChrome`.
 */
import { useState } from 'react';
import { Group, Line, Rect } from 'react-konva';
import { snapHeader, type ElementGuide } from '@/lib/dealer-kit/accessory-card';
import type { AccessoryRect } from '@/lib/dealer-kit/accessory-box';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

const round = (mm: number) => Math.round(mm * 100) / 100;

export function HeaderDragOverlay({
  layer,
  header,
  frame,
  boxWidth_mm,
  boxHeight_mm,
  scale,
  onMove,
}: {
  layer: TagLayer;
  /** The header as the shared layout places it now. */
  header: AccessoryRect;
  frame: AccessoryRect | null;
  /** The box as drawn (closed up around its cards). */
  boxWidth_mm: number;
  boxHeight_mm: number;
  /** Canvas pixels per millimetre. */
  scale: number;
  onMove: (pos: { x_mm: number; y_mm: number }) => void;
}) {
  const [guides, setGuides] = useState<ElementGuide[]>([]);
  const area = { width_mm: boxWidth_mm, height_mm: boxHeight_mm };
  const land = (x: number, y: number) =>
    snapHeader({ ...header, x_mm: x / scale, y_mm: y / scale }, frame, area);

  return (
    <Group x={layer.x_mm * scale} y={layer.y_mm * scale} rotation={layer.rotation_deg || 0}>
      <Rect
        name="accessory-header-handle"
        x={header.x_mm * scale}
        y={header.y_mm * scale}
        width={header.width_mm * scale}
        height={header.height_mm * scale}
        fill="transparent"
        stroke="#2563eb"
        strokeWidth={1}
        dash={[3, 3]}
        draggable
        onMouseEnter={(e) => {
          const stage = e.target.getStage();
          if (stage) stage.container().style.cursor = 'move';
        }}
        onMouseLeave={(e) => {
          const stage = e.target.getStage();
          if (stage) stage.container().style.cursor = '';
        }}
        // The press is the header's, never the box's or the stage's (no box drag, no marquee).
        onMouseDown={(e) => {
          e.cancelBubble = true;
        }}
        onTouchStart={(e) => {
          e.cancelBubble = true;
        }}
        onClick={(e) => {
          e.cancelBubble = true;
        }}
        onTap={(e) => {
          e.cancelBubble = true;
        }}
        onDragMove={(e) => {
          e.cancelBubble = true;
          const at = land(e.target.x(), e.target.y());
          e.target.position({ x: at.x_mm * scale, y: at.y_mm * scale });
          setGuides(at.guides);
        }}
        onDragEnd={(e) => {
          e.cancelBubble = true;
          setGuides([]);
          const at = land(e.target.x(), e.target.y());
          onMove({ x_mm: round(at.x_mm), y_mm: round(at.y_mm) });
        }}
      />
      {guides.map((g, i) => (
        <Line
          key={i}
          points={
            g.orientation === 'vertical'
              ? [g.position_mm * scale, 0, g.position_mm * scale, boxHeight_mm * scale]
              : [0, g.position_mm * scale, boxWidth_mm * scale, g.position_mm * scale]
          }
          stroke="#ec4899"
          strokeWidth={1}
          dash={[4, 3]}
          listening={false}
        />
      ))}
    </Group>
  );
}
