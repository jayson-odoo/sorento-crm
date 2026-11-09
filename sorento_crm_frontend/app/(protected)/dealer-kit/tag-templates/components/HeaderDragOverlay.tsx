'use client';

/**
 * PRICETAG-HEADER-DRAG (owner 9 Nov: "I want to drag and place it at other places"): a handle over the
 * selected accessories box's header text. Dragging it moves the HEADER, not the box, anywhere inside
 * the box, with snapping guides; the text rides with the pointer (the box hides its own header for the
 * drag) and the drop is stored as `headerPos` in box millimetres, the spot every render (canvas,
 * preview, print) reads through `accessoryChrome`.
 *
 * Round 2 (owner 9 Nov ~17:00, "resize it like a normal design component"): a click selects the
 * header, and a selected header gets the canvas's usual Transformer handles (no rotation: it turns
 * with its box). A resize is stored as the band's position + size, in box millimetres.
 */
import { useEffect, useRef, useState } from 'react';
import { Group, Line, Rect, Text, Transformer } from 'react-konva';
import type Konva from 'konva';
import { accessoryHeaderStyle, ptToMm, type AccessoryRect } from '@/lib/dealer-kit/accessory-box';
import { snapHeader, type ElementGuide } from '@/lib/dealer-kit/accessory-card';
import type { AccessoriesLayerProps, TagLayer } from '@/lib/dealer-kit/tag-template-types';

const round = (mm: number) => Math.round(mm * 100) / 100;
/** The smallest band a resize can leave (mm), so a header is never lost under a 0 mm box. */
const MIN_MM = 2;

/** Only the main button's press belongs to the header: a middle-button press still pans the canvas. */
const mainButton = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) =>
  !('button' in e.evt) || (e.evt as MouseEvent).button === 0;

export function HeaderDragOverlay({
  layer,
  text,
  fontSize_pt,
  frame,
  boxWidth_mm,
  boxHeight_mm,
  scale,
  selected = false,
  onSelect,
  onResize,
  onDragState,
  onMove,
}: {
  layer: TagLayer;
  /** Where the header text draws now (the layout's `header.text`). */
  text: AccessoryRect;
  fontSize_pt: number;
  frame: AccessoryRect | null;
  /** The box as drawn (closed up around its cards). */
  boxWidth_mm: number;
  boxHeight_mm: number;
  /** Canvas pixels per millimetre. */
  scale: number;
  /** The header itself is selected (not just its box): it shows resize handles. */
  selected?: boolean;
  onSelect?: () => void;
  onResize?: (rect: { x_mm: number; y_mm: number; width_mm: number; height_mm: number }) => void;
  /** True while the header is being dragged (the box then hides its own header text). */
  onDragState?: (dragging: boolean) => void;
  onMove: (pos: { x_mm: number; y_mm: number }) => void;
}) {
  const [guides, setGuides] = useState<ElementGuide[]>([]);
  const [dragging, setDragging] = useState(false);
  const handleRef = useRef<Konva.Group>(null);
  const trRef = useRef<Konva.Transformer>(null);
  useEffect(() => {
    const tr = trRef.current;
    if (!tr || !handleRef.current) return;
    tr.nodes([handleRef.current]);
    tr.getLayer()?.batchDraw();
  }, [selected, text.x_mm, text.y_mm, text.width_mm, text.height_mm]);
  const props = layer.props as AccessoriesLayerProps;
  const style = accessoryHeaderStyle(props);
  const area = { width_mm: boxWidth_mm, height_mm: boxHeight_mm };
  const land = (x: number, y: number) =>
    snapHeader({ ...text, x_mm: x / scale, y_mm: y / scale }, frame, area);
  const drop = (x: number, y: number) => {
    setGuides([]);
    setDragging(false);
    onDragState?.(false);
    const at = land(x, y);
    onMove({ x_mm: round(at.x_mm), y_mm: round(at.y_mm) });
  };

  return (
    <Group x={layer.x_mm * scale} y={layer.y_mm * scale} rotation={layer.rotation_deg || 0}>
      <Group
        ref={handleRef}
        name="accessory-header-handle"
        x={text.x_mm * scale}
        y={text.y_mm * scale}
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
          if (mainButton(e)) e.cancelBubble = true;
        }}
        onTouchStart={(e) => {
          e.cancelBubble = true;
        }}
        onClick={(e) => {
          if (!mainButton(e)) return;
          e.cancelBubble = true;
          onSelect?.();
        }}
        onTap={(e) => {
          e.cancelBubble = true;
          onSelect?.();
        }}
        onDragStart={(e) => {
          e.cancelBubble = true;
          onSelect?.();
          setDragging(true);
          onDragState?.(true);
        }}
        onDragMove={(e) => {
          e.cancelBubble = true;
          const at = land(e.target.x(), e.target.y());
          e.target.position({ x: at.x_mm * scale, y: at.y_mm * scale });
          setGuides(at.guides);
        }}
        onDragEnd={(e) => {
          e.cancelBubble = true;
          drop(e.target.x(), e.target.y());
        }}
        onTransformEnd={(e) => {
          e.cancelBubble = true;
          const node = e.target;
          const width_mm = Math.max(MIN_MM, round((text.width_mm * node.scaleX())));
          const height_mm = Math.max(MIN_MM, round((text.height_mm * node.scaleY())));
          node.scaleX(1);
          node.scaleY(1);
          onResize?.({ x_mm: round(node.x() / scale), y_mm: round(node.y() / scale), width_mm, height_mm });
        }}
      >
        <Rect
          width={text.width_mm * scale}
          height={text.height_mm * scale}
          fill="transparent"
          stroke="#2563eb"
          strokeWidth={1}
          dash={[3, 3]}
        />
        {dragging && (
          <Text
            width={text.width_mm * scale}
            height={text.height_mm * scale}
            text={props.headerText}
            align="center"
            verticalAlign="middle"
            fontStyle={style.fontWeight >= 600 ? 'bold' : 'normal'}
            fontFamily={style.fontFamily ?? undefined}
            fontSize={ptToMm(fontSize_pt) * scale}
            fill={style.color}
            wrap="none"
            listening={false}
          />
        )}
      </Group>
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
      {selected && (
        <Transformer
          ref={trRef}
          rotateEnabled={false}
          flipEnabled={false}
          ignoreStroke
          boundBoxFunc={(oldBox, newBox) =>
            newBox.width < MIN_MM * scale || newBox.height < MIN_MM * scale ? oldBox : newBox
          }
        />
      )}
    </Group>
  );
}
