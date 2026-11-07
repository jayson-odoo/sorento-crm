'use client';

/**
 * PRICETAG-ACCESSORY-DESIGNER S3: the editable frame drawn over card 1 (or the footer) of an
 * accessories box while it is in editing mode. Every element is a selectable, draggable rectangle;
 * the selected one gets a Konva Transformer to resize it. Positions are written back in card
 * millimetres (the box's shrink factor undone), so what is dragged is what prints.
 */
import { useEffect, useRef, useState } from 'react';
import { Group, Line, Rect, Transformer } from 'react-konva';
import type Konva from 'konva';
import { cardBoxLayout, snapElement, type ElementGuide } from '@/lib/dealer-kit/accessory-card';
import type {
  AccessoriesLayerProps,
  CardElement,
  TagLayer,
} from '@/lib/dealer-kit/tag-template-types';

export type AccessoryEditTarget = 'card' | 'footer';

const round = (mm: number) => Math.round(mm * 100) / 100;
const MIN_MM = 1;

export function AccessoryEditOverlay({
  layer,
  target,
  elementId,
  count = 2,
  scale,
  onSelectElement,
  onUpdateElement,
}: {
  layer: TagLayer;
  target: AccessoryEditTarget;
  elementId: string | null;
  /** How many cards the canvas draws for this box (its previewed list, else the two samples). */
  count?: number;
  /** Canvas pixels per millimetre. */
  scale: number;
  onSelectElement: (elementId: string | null) => void;
  onUpdateElement: (elementId: string, patch: Partial<CardElement>) => void;
}) {
  const props = layer.props as AccessoriesLayerProps;
  const trRef = useRef<Konva.Transformer>(null);
  const nodes = useRef(new Map<string, Konva.Rect>());
  const [guides, setGuides] = useState<ElementGuide[]>([]);

  useEffect(() => {
    const tr = trRef.current;
    if (!tr) return;
    const node = elementId ? nodes.current.get(elementId) : undefined;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [elementId, props.card, props.footer, target]);

  // Editing the footer lays it out even while hidden (as the canvas draws it); editing the card does not.
  const shown: AccessoriesLayerProps =
    target === 'footer'
      ? { ...props, footer: { height_mm: 6, elements: [], ...props.footer, show: true } }
      : props;
  const box = cardBoxLayout(count, shown, layer.width_mm, layer.height_mm);
  const origin = target === 'card' ? box.cards[0] : box.footer;
  const elements = target === 'card' ? props.card?.elements : props.footer?.elements;
  if (!origin || !elements) return null;
  const factor = target === 'card' ? box.scale : 1;
  const px = (mm: number) => mm * factor * scale;

  return (
    <Group x={layer.x_mm * scale} y={layer.y_mm * scale} rotation={layer.rotation_deg || 0}>
      <Group x={origin.x_mm * scale} y={origin.y_mm * scale}>
        {/* Empty space inside the card: a click here clears the element selection (Delete then removes
            nothing). It sits under the elements, so a click on one still reaches it. */}
        <Rect
          name="accessory-card-frame"
          width={origin.width_mm * scale}
          height={origin.height_mm * scale}
          fill="transparent"
          stroke="#2563eb"
          strokeWidth={1}
          onMouseDown={(e) => {
            e.cancelBubble = true;
          }}
          onClick={(e) => {
            e.cancelBubble = true;
            onSelectElement(null);
          }}
          onTap={() => onSelectElement(null)}
        />
        {elements.map((element) => (
          <Rect
            key={element.id}
            name={`accessory-card-element-${element.id}`}
            ref={(node) => {
              if (node) nodes.current.set(element.id, node);
              else nodes.current.delete(element.id);
            }}
            x={px(element.x_mm)}
            y={px(element.y_mm)}
            width={px(element.width_mm)}
            height={px(element.height_mm)}
            fill={element.kind === 'picture' ? 'rgba(148,163,184,0.25)' : 'transparent'}
            stroke={element.id === elementId ? '#2563eb' : '#93c5fd'}
            strokeWidth={1}
            dash={element.hidden ? [3, 3] : undefined}
            draggable
            onMouseDown={(e) => {
              e.cancelBubble = true;
            }}
            onClick={(e) => {
              e.cancelBubble = true;
              onSelectElement(element.id);
            }}
            onTap={() => onSelectElement(element.id)}
            onDragStart={() => onSelectElement(element.id)}
            onDragMove={(e) => {
              const unit = factor * scale;
              const snapped = snapElement(
                { ...element, x_mm: e.target.x() / unit, y_mm: e.target.y() / unit },
                elements.filter((other) => other.id !== element.id && !other.hidden),
                { width_mm: origin.width_mm / factor, height_mm: origin.height_mm / factor },
              );
              e.target.position({ x: snapped.x_mm * unit, y: snapped.y_mm * unit });
              setGuides(snapped.guides);
            }}
            onDragEnd={(e) => {
              e.cancelBubble = true;
              setGuides([]);
              onUpdateElement(element.id, {
                x_mm: round(e.target.x() / (factor * scale)),
                y_mm: round(e.target.y() / (factor * scale)),
              });
            }}
            onTransformEnd={(e) => {
              const node = e.target as Konva.Rect;
              const w = Math.max(MIN_MM, round((node.width() * node.scaleX()) / (factor * scale)));
              const h = Math.max(MIN_MM / 2, round((node.height() * node.scaleY()) / (factor * scale)));
              node.scaleX(1);
              node.scaleY(1);
              onUpdateElement(element.id, {
                x_mm: round(node.x() / (factor * scale)),
                y_mm: round(node.y() / (factor * scale)),
                width_mm: w,
                height_mm: h,
              });
            }}
          />
        ))}
        {guides.map((guide, i) => {
          const at = guide.position_mm * factor * scale;
          return (
            <Line
              key={`${guide.orientation}-${i}`}
              points={
                guide.orientation === 'vertical'
                  ? [at, 0, at, origin.height_mm * scale]
                  : [0, at, origin.width_mm * scale, at]
              }
              stroke="#f43f5e"
              strokeWidth={0.5}
              dash={[4, 4]}
              listening={false}
            />
          );
        })}
        <Transformer
          ref={trRef}
          rotateEnabled={false}
          keepRatio={false}
          ignoreStroke
          boundBoxFunc={(_old, next) =>
            next.width < 2 || next.height < 2 ? { ...next, width: Math.max(next.width, 2), height: Math.max(next.height, 2) } : next
          }
        />
      </Group>
    </Group>
  );
}
