'use client';

/**
 * PRICETAG-ACCESSORY-DESIGNER S3: the editable frame drawn over card 1 (or the footer) of an
 * accessories box while it is in editing mode. Every element is a selectable, draggable rectangle;
 * the selected one gets a Konva Transformer to resize it. Positions are written back in card
 * millimetres (the box's shrink factor undone), so what is dragged is what prints.
 */
import { useEffect, useRef } from 'react';
import { Group, Rect, Transformer } from 'react-konva';
import type Konva from 'konva';
import { cardBoxLayout } from '@/lib/dealer-kit/accessory-card';
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
  scale,
  onSelectElement,
  onUpdateElement,
}: {
  layer: TagLayer;
  target: AccessoryEditTarget;
  elementId: string | null;
  /** Canvas pixels per millimetre. */
  scale: number;
  onSelectElement: (elementId: string | null) => void;
  onUpdateElement: (elementId: string, patch: Partial<CardElement>) => void;
}) {
  const props = layer.props as AccessoriesLayerProps;
  const trRef = useRef<Konva.Transformer>(null);
  const nodes = useRef(new Map<string, Konva.Rect>());

  useEffect(() => {
    const tr = trRef.current;
    if (!tr) return;
    const node = elementId ? nodes.current.get(elementId) : undefined;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [elementId, props.card, props.footer, target]);

  // The footer is laid out even while hidden, so the first element lands somewhere visible.
  const shown: AccessoriesLayerProps = {
    ...props,
    footer: { show: true, height_mm: 6, elements: [], ...props.footer },
  };
  const box = cardBoxLayout(2, shown, layer.width_mm, layer.height_mm);
  const origin = target === 'card' ? box.cards[0] : box.footer;
  const elements = target === 'card' ? props.card?.elements : props.footer?.elements;
  if (!origin || !elements) return null;
  const factor = target === 'card' ? box.scale : 1;
  const px = (mm: number) => mm * factor * scale;

  return (
    <Group x={layer.x_mm * scale} y={layer.y_mm * scale} rotation={layer.rotation_deg || 0}>
      <Group x={origin.x_mm * scale} y={origin.y_mm * scale}>
        <Rect
          width={origin.width_mm * scale}
          height={origin.height_mm * scale}
          stroke="#2563eb"
          strokeWidth={1}
          listening={false}
        />
        {elements.map((element) => (
          <Rect
            key={element.id}
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
            onDragEnd={(e) => {
              e.cancelBubble = true;
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
