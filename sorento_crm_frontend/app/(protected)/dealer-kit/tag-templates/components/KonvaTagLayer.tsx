'use client';

/**
 * Renders a single TagLayer as Konva nodes.
 *
 * Each layer type maps to the appropriate Konva primitive. Selected layers
 * show a `Transformer` for resize/rotate. Locked layers are not
 * draggable/selectable.
 */

import { useEffect, useRef } from 'react';
import { Ellipse, Group, Line, Rect, Text, Transformer } from 'react-konva';
import type Konva from 'konva';
import type { TagLayer, TagLayerProps } from '@/lib/dealer-kit/tag-template-types';

interface KonvaTagLayerProps {
  layer: TagLayer;
  scale: number;
  isSelected: boolean;
  onSelect: (id: string, additive: boolean) => void;
  onDragStart: (id: string) => void;
  onDragMove: (id: string, x_mm: number, y_mm: number) => void;
  onDragEnd: (id: string) => void;
  onTransformEnd: (id: string, attrs: { x_mm: number; y_mm: number; width_mm: number; height_mm: number; rotation_deg: number }) => void;
}

/** Convert mm to canvas pixels. */
function mm2px(mm: number, scale: number) {
  return mm * scale;
}

/** Convert canvas pixels to mm. */
function px2mm(px: number, scale: number) {
  return px / scale;
}

export function KonvaTagLayer({
  layer,
  scale,
  isSelected,
  onSelect,
  onDragStart,
  onDragMove,
  onDragEnd,
  onTransformEnd,
}: KonvaTagLayerProps) {
  const shapeRef = useRef<Konva.Group>(null);
  const trRef = useRef<Konva.Transformer>(null);

  useEffect(() => {
    if (isSelected && trRef.current && shapeRef.current) {
      trRef.current.nodes([shapeRef.current]);
      trRef.current.getLayer()?.batchDraw();
    }
  }, [isSelected]);

  if (!layer.visible) return null;

  const x = mm2px(layer.x_mm, scale);
  const y = mm2px(layer.y_mm, scale);
  const w = mm2px(layer.width_mm, scale);
  const h = mm2px(layer.height_mm, scale);

  const handleClick = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (layer.locked) return;
    e.cancelBubble = true;
    const shiftKey = 'shiftKey' in e.evt ? e.evt.shiftKey : false;
    onSelect(layer.id, shiftKey);
  };

  const handleDragStart = () => {
    onDragStart(layer.id);
  };

  const handleDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const node = e.target;
    onDragMove(layer.id, px2mm(node.x(), scale), px2mm(node.y(), scale));
  };

  const handleDragEnd = (e: Konva.KonvaEventObject<DragEvent>) => {
    const node = e.target;
    // Snap to final position.
    onDragMove(layer.id, px2mm(node.x(), scale), px2mm(node.y(), scale));
    onDragEnd(layer.id);
  };

  const handleTransformEnd = () => {
    const node = shapeRef.current;
    if (!node) return;
    const scaleX = node.scaleX();
    const scaleY = node.scaleY();
    // Reset scale to 1 and apply to width/height.
    node.scaleX(1);
    node.scaleY(1);
    onTransformEnd(layer.id, {
      x_mm: px2mm(node.x(), scale),
      y_mm: px2mm(node.y(), scale),
      width_mm: px2mm(node.width() * scaleX, scale),
      height_mm: px2mm(node.height() * scaleY, scale),
      rotation_deg: node.rotation(),
    });
  };

  return (
    <>
      <Group
        ref={shapeRef}
        x={x}
        y={y}
        width={w}
        height={h}
        rotation={layer.rotation_deg}
        draggable={!layer.locked}
        onClick={handleClick}
        onTap={handleClick}
        onDragStart={handleDragStart}
        onDragMove={handleDragMove}
        onDragEnd={handleDragEnd}
        onTransformEnd={handleTransformEnd}
      >
        <LayerContent props={layer.props} w={w} h={h} scale={scale} />
      </Group>

      {isSelected && !layer.locked && (
        <Transformer
          ref={trRef}
          rotateEnabled
          keepRatio={false}
          enabledAnchors={[
            'top-left',
            'top-right',
            'bottom-left',
            'bottom-right',
            'middle-left',
            'middle-right',
            'top-center',
            'bottom-center',
          ]}
          boundBoxFunc={(_oldBox, newBox) => {
            // Minimum size = 2mm in pixels.
            const minSize = mm2px(2, scale);
            if (newBox.width < minSize || newBox.height < minSize) {
              return {
                ...newBox,
                width: Math.max(newBox.width, minSize),
                height: Math.max(newBox.height, minSize),
              };
            }
            return newBox;
          }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Type-specific content rendering
// ---------------------------------------------------------------------------

function LayerContent({
  props,
  w,
  h,
  scale,
}: {
  props: TagLayerProps;
  w: number;
  h: number;
  scale: number;
}) {
  switch (props.kind) {
    case 'text':
      return (
        <Text
          width={w}
          height={h}
          text={props.text}
          fontFamily={props.fontFamily}
          fontSize={props.fontSize * scale * 0.35}
          fontStyle={props.fontWeight >= 700 ? 'bold' : 'normal'}
          fill={props.color}
          align={props.align}
          lineHeight={props.lineHeight}
          letterSpacing={props.letterSpacing * scale * 0.1}
          wrap="word"
        />
      );

    case 'shape':
      return <ShapeContent shape={props.shape} w={w} h={h} props={props} />;

    case 'image':
      // Image placeholder (asset loading is out of scope for Phase 1 mock).
      return (
        <>
          <Rect width={w} height={h} fill="#f0f0f0" stroke="#ccc" strokeWidth={1} />
          <Text
            width={w}
            height={h}
            text={props.assetId ? 'Image' : 'No image'}
            align="center"
            verticalAlign="middle"
            fontSize={10}
            fill="#999"
          />
        </>
      );

    case 'product_slot':
      return (
        <>
          <Rect
            width={w}
            height={h}
            fill="transparent"
            stroke="#3b82f6"
            strokeWidth={1}
            dash={[4, 4]}
          />
          <Text
            width={w}
            height={h}
            text={props.fieldKey.replace(/_/g, ' ')}
            align="center"
            verticalAlign="middle"
            fontSize={Math.min(11, w / 6)}
            fill="#3b82f6"
          />
        </>
      );

    case 'price_field':
      return <PriceFieldContent w={w} h={h} priceType={props.priceType} scale={scale} />;

    case 'badge':
      return (
        <>
          <Rect width={w} height={h} fill="#2e7d32" cornerRadius={mm2px(1, scale)} />
          <Text
            width={w}
            height={h}
            text="BADGE"
            align="center"
            verticalAlign="middle"
            fontSize={Math.min(10, w / 5)}
            fill="#ffffff"
            fontStyle="bold"
          />
        </>
      );

    case 'group':
      // Group renders nothing itself; children are rendered separately.
      return (
        <Rect
          width={w}
          height={h}
          fill="transparent"
          stroke="#8b5cf6"
          strokeWidth={1}
          dash={[6, 3]}
        />
      );
  }
}

function mm2px_(mm: number, scale: number) {
  return mm * scale;
}

function ShapeContent({
  shape,
  w,
  h,
  props,
}: {
  shape: string;
  w: number;
  h: number;
  props: Extract<TagLayerProps, { kind: 'shape' }>;
}) {
  switch (shape) {
    case 'ellipse':
      return (
        <Ellipse
          x={w / 2}
          y={h / 2}
          radiusX={w / 2}
          radiusY={h / 2}
          fill={props.fill === 'transparent' ? undefined : props.fill}
          stroke={props.stroke === 'transparent' ? undefined : props.stroke}
          strokeWidth={props.strokeWidth}
        />
      );
    case 'line':
      return (
        <Line
          points={[0, h / 2, w, h / 2]}
          stroke={props.stroke === 'transparent' ? '#000' : props.stroke}
          strokeWidth={props.strokeWidth || 1}
        />
      );
    case 'rounded_rect':
      return (
        <Rect
          width={w}
          height={h}
          fill={props.fill === 'transparent' ? undefined : props.fill}
          stroke={props.stroke === 'transparent' ? undefined : props.stroke}
          strokeWidth={props.strokeWidth}
          cornerRadius={mm2px_(props.cornerRadius, w / 20)}
        />
      );
    default:
      // rect
      return (
        <Rect
          width={w}
          height={h}
          fill={props.fill === 'transparent' ? undefined : props.fill}
          stroke={props.stroke === 'transparent' ? undefined : props.stroke}
          strokeWidth={props.strokeWidth}
        />
      );
  }
}

function PriceFieldContent({
  w,
  h,
  priceType,
}: {
  w: number;
  h: number;
  priceType: string;
  scale: number;
}) {
  const fontSize = Math.min(12, w / 8);

  if (priceType === 'list') {
    return (
      <>
        <Rect width={w} height={h} fill="transparent" stroke="#999" strokeWidth={0.5} dash={[2, 2]} />
        <Text
          width={w}
          height={h}
          text="RM 1,550"
          align="center"
          verticalAlign="middle"
          fontSize={fontSize}
          fill="#333"
          fontStyle="bold"
        />
      </>
    );
  }

  if (priceType === 'sell') {
    return (
      <>
        <Rect width={w} height={h} fill="transparent" stroke="#999" strokeWidth={0.5} dash={[2, 2]} />
        <Text
          width={w}
          height={h}
          text="SP RM 999 NETT"
          align="center"
          verticalAlign="middle"
          fontSize={fontSize}
          fill="#b44d2e"
          fontStyle="bold"
        />
      </>
    );
  }

  // both
  const halfH = h / 2;
  return (
    <>
      <Rect width={w} height={h} fill="transparent" stroke="#999" strokeWidth={0.5} dash={[2, 2]} />
      <Text
        width={w}
        height={halfH}
        text="LP: RM 1,550"
        align="center"
        verticalAlign="middle"
        fontSize={fontSize * 0.8}
        fill="#999"
        textDecoration="line-through"
      />
      <Text
        y={halfH}
        width={w}
        height={halfH}
        text="SP RM 999 NETT"
        align="center"
        verticalAlign="middle"
        fontSize={fontSize}
        fill="#b44d2e"
        fontStyle="bold"
      />
    </>
  );
}
