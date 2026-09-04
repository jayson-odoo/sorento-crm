'use client';

/**
 * Renders a single TagLayer as Konva nodes.
 *
 * Each layer type maps to the appropriate Konva primitive. The Konva Group
 * carries `id={layer.id}`, which is how the editor finds the node again during
 * a drag; without it `stage.findOne('#id')` answered undefined and every canvas
 * move was silently thrown away on Save.
 *
 * There is no Transformer here. ONE Transformer lives in the editor and is
 * attached to the whole selection (D38), because a per-layer one cannot express
 * a multi-selection and cannot propagate a group's resize to its children.
 */

import { useEffect, useState } from 'react';
import { Ellipse, Group, Image as KonvaImage, Line, Rect, Text } from 'react-konva';
import type Konva from 'konva';
import JsBarcode from 'jsbarcode';
import type { TagLayer, TagLayerProps } from '@/lib/dealer-kit/tag-template-types';
import type { PriceBadgeInput } from '@/lib/dealer-kit/price-badge';
import { priceBadgeParts } from '@/lib/dealer-kit/price-badge';
import type { TagLayerDisplay } from '@/lib/dealer-kit/product-block';
import {
  barcodePlateGeometry,
  barcodeSymbologyFor,
  humanReadableBarcode,
} from '@/lib/dealer-kit/barcode';

// `TagLayerDisplay` is resolved by whoever owns the data (the editor, the
// designer) and handed DOWN: the canvas draws layers and knows nothing about
// products, which is what lets one component render a template, a placed tag
// and a preview.
export type { TagLayerDisplay };

/**
 * Load an image for Konva.
 *
 * Konva needs a real HTMLImageElement rather than a URL, and re-rendering with
 * a half-loaded one paints nothing, so the element only reaches the stage once
 * it has decoded.
 *
 * **No `crossOrigin`.** It used to be `anonymous`, for a reason that does not
 * hold: a signed URL needs no CORS, and `anonymous` makes the browser DISCARD
 * an image whose response carries no `Access-Control-Allow-Origin`. The R2
 * bucket serving library assets sends none, so every badge, icon and diagram on
 * a tag failed to decode and sat on "Loading" forever - which is exactly what
 * the eight seeded templates showed, all 28 pieces of artwork, on a canvas that
 * was otherwise correct.
 *
 * What `anonymous` would buy is an UNTAINTED canvas, and nothing here wants
 * one: the tag PDF is rendered by headless Chromium against the print page, not
 * by `stage.toDataURL()`, and there is no `toDataURL` anywhere under
 * `dealer-kit/`. Bring it back only alongside a client-side canvas export - and
 * with a CORS rule on the bucket, or the export will draw blanks instead.
 */
function useHtmlImage(url: string | null | undefined): HTMLImageElement | null {
  const [image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!url) {
      setImage(null);
      return;
    }
    let live = true;
    const element = new window.Image();
    element.src = url;
    element.onload = () => {
      if (live) setImage(element);
    };
    element.onerror = () => {
      if (live) setImage(null);
    };
    return () => {
      live = false;
    };
  }, [url]);

  return image;
}

interface KonvaTagLayerProps {
  layer: TagLayer;
  scale: number;
  /** Live values for a bound layer. Absent = draw the layer's own content. */
  display?: TagLayerDisplay;
  /**
   * False while the hand tool is active, and for a locked layer. Kept separate
   * from `locked` so the tool can suspend dragging without touching the doc.
   */
  draggable?: boolean;
  /**
   * False for a group the user has entered (D37), so its outline stays visible
   * but its children receive the pointer events. Konva hit-tests a
   * `fill="transparent"` rect, so this - and not removing the fill - is what
   * makes a node pass through.
   */
  listening?: boolean;
  onSelect?: (id: string, additive: boolean) => void;
  onDoubleClick?: (id: string) => void;
  onDragStart?: (id: string) => void;
  onDragMove?: (id: string, x_mm: number, y_mm: number) => void;
  onDragEnd?: (id: string) => void;
  /**
   * The pointer entered/left this layer's own bounds (S6, D10). Used to show
   * a previewable block's eye chip on hover - a plain pass-through, the host
   * resolves which BLOCK a hovered child belongs to.
   */
  onHoverChange?: (id: string, hovering: boolean) => void;
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
  display,
  draggable = true,
  listening = true,
  onSelect,
  onDoubleClick,
  onDragStart,
  onDragMove,
  onDragEnd,
  onHoverChange,
}: KonvaTagLayerProps) {
  if (!layer.visible) return null;

  const x = mm2px(layer.x_mm, scale);
  const y = mm2px(layer.y_mm, scale);
  const w = mm2px(layer.width_mm, scale);
  const h = mm2px(layer.height_mm, scale);

  // Selecting on mousedown rather than click, because a drag never produces a
  // click: without it, dragging an unselected layer moved a layer the inspector
  // and the toolbar still thought was not selected.
  const handleMouseDown = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (layer.locked) return;
    // Only the left button selects. The middle one pans the view (D44) and the
    // right one is the context menu's, which resolves its own target.
    if ('button' in e.evt && e.evt.button !== 0) return;
    e.cancelBubble = true;
    const shiftKey = 'shiftKey' in e.evt ? e.evt.shiftKey : false;
    onSelect?.(layer.id, shiftKey);
  };

  const handleDoubleClick = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    e.cancelBubble = true;
    onDoubleClick?.(layer.id);
  };

  const handleDragStart = () => {
    onDragStart?.(layer.id);
  };

  const handleDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const node = e.target;
    onDragMove?.(layer.id, px2mm(node.x(), scale), px2mm(node.y(), scale));
  };

  const handleDragEnd = (e: Konva.KonvaEventObject<DragEvent>) => {
    const node = e.target;
    // Snap to final position.
    onDragMove?.(layer.id, px2mm(node.x(), scale), px2mm(node.y(), scale));
    onDragEnd?.(layer.id);
  };

  return (
    <Group
      id={layer.id}
      x={x}
      y={y}
      width={w}
      height={h}
      rotation={layer.rotation_deg}
      listening={listening}
      draggable={draggable && !layer.locked}
      onMouseDown={handleMouseDown}
      onTouchStart={handleMouseDown}
      onDblClick={handleDoubleClick}
      onDblTap={handleDoubleClick}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      onMouseEnter={() => onHoverChange?.(layer.id, true)}
      onMouseLeave={() => onHoverChange?.(layer.id, false)}
    >
      <LayerContent props={layer.props} w={w} h={h} scale={scale} display={display} />
    </Group>
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
  display,
}: {
  props: TagLayerProps;
  w: number;
  h: number;
  scale: number;
  display?: TagLayerDisplay;
}) {
  switch (props.kind) {
    case 'text':
      return (
        <Text
          width={w}
          height={h}
          text={display?.text ?? props.text}
          fontFamily={props.fontFamily}
          fontSize={props.fontSize * scale * 0.35}
          fontStyle={
            [props.italic && 'italic', props.fontWeight >= 600 && 'bold']
              .filter(Boolean)
              .join(' ') || 'normal'
          }
          textDecoration={
            [props.underline && 'underline', props.strikethrough && 'line-through']
              .filter(Boolean)
              .join(' ')
          }
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
      return (
        <ImageContent
          w={w}
          h={h}
          url={display?.imageUrl ?? null}
          fit={props.fit}
          maskShape={props.maskShape ?? 'none'}
        />
      );

    case 'product_slot':
      // A slot draws its DATA when there is any (D42) and falls back to the
      // dashed outline naming the field, which is what a designer needs to see
      // while the template is unbound.
      if (display?.imageUrl) {
        return (
          <ImageContent
            w={w}
            h={h}
            url={display.imageUrl}
            fit="contain"
            maskShape="none"
          />
        );
      }
      if (display?.text) {
        return (
          <Text
            width={w}
            height={h}
            text={display.text}
            fontSize={Math.min(11, w / 6)}
            fill="#000000"
            wrap="word"
          />
        );
      }
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

    case 'price_badge':
      return (
        <PriceBadgeContent
          w={w}
          h={h}
          scale={scale}
          props={props}
          input={display?.price ?? { listPrice: null, offerPrice: null }}
        />
      );

    case 'badge':
      if (display?.imageUrl) {
        return (
          <ImageContent
            w={w}
            h={h}
            url={display.imageUrl}
            fit="contain"
            maskShape="none"
          />
        );
      }
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

    case 'barcode':
      return (
        <BarcodeContent
          w={w}
          h={h}
          scale={scale}
          showCode={props.show_code}
          value={display?.text ?? null}
          code={display?.code ?? null}
        />
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

// ---------------------------------------------------------------------------
// Image
// ---------------------------------------------------------------------------

function ImageContent({
  w,
  h,
  url,
  fit,
  maskShape,
}: {
  w: number;
  h: number;
  url: string | null;
  fit: 'cover' | 'contain';
  maskShape: 'none' | 'circle';
}) {
  const image = useHtmlImage(url);

  if (!image) {
    return (
      <>
        <Rect width={w} height={h} fill="#f0f0f0" stroke="#ccc" strokeWidth={1} />
        <Text
          width={w}
          height={h}
          text={url ? 'Loading' : 'No image'}
          align="center"
          verticalAlign="middle"
          fontSize={10}
          fill="#999"
        />
      </>
    );
  }

  // `contain` letterboxes inside the box, `cover` fills it and overflows; the
  // clip below is what turns overflow into a crop rather than a picture spilling
  // over the layer next to it.
  const ratio = image.width / image.height;
  const boxRatio = w / h;
  const wide = fit === 'contain' ? ratio > boxRatio : ratio < boxRatio;
  const drawW = wide ? w : h * ratio;
  const drawH = wide ? w / ratio : h;

  const body = (
    <KonvaImage
      image={image}
      x={(w - drawW) / 2}
      y={(h - drawH) / 2}
      width={drawW}
      height={drawH}
    />
  );

  if (maskShape === 'circle') {
    return (
      <Group
        clipFunc={(ctx) => {
          ctx.beginPath();
          ctx.arc(w / 2, h / 2, Math.min(w, h) / 2, 0, Math.PI * 2, false);
          ctx.closePath();
        }}
      >
        {body}
      </Group>
    );
  }

  if (fit === 'cover') {
    return (
      <Group
        clipFunc={(ctx) => {
          ctx.beginPath();
          ctx.rect(0, 0, w, h);
          ctx.closePath();
        }}
      >
        {body}
      </Group>
    );
  }

  return body;
}

// ---------------------------------------------------------------------------
// Barcode (D18, S7)
// ---------------------------------------------------------------------------

/** Whether the offscreen canvas has been drawn, is still to be drawn, or
 * `jsbarcode` threw drawing it. Distinct from `pending` so the renderer can
 * tell "still loading" apart from "cannot encode this value" - the two used
 * to share one `null`, which drew "Loading" forever on a genuine failure. */
type BarcodeCanvasState =
  | { status: 'pending' }
  | { status: 'failed' }
  | { status: 'ready'; canvas: HTMLCanvasElement };

/**
 * Generates the bars onto an offscreen canvas via `jsbarcode`, the same
 * symbology decision `humanReadableBarcode` and the print page's DOM
 * renderer use (`barcodeSymbologyFor`). Konva takes any `CanvasImageSource`
 * as an Image's `image` prop, so the generated canvas is used directly -
 * no data-URL round trip.
 */
function useBarcodeCanvas(value: string | null): BarcodeCanvasState {
  const [state, setState] = useState<BarcodeCanvasState>({ status: 'pending' });

  useEffect(() => {
    const symbology = barcodeSymbologyFor(value);
    if (!symbology || !value) {
      setState({ status: 'pending' });
      return;
    }
    const element = document.createElement('canvas');
    try {
      JsBarcode(element, value.trim(), {
        format: symbology,
        displayValue: false,
        margin: 0,
        height: 160,
      });
      setState({ status: 'ready', canvas: element });
    } catch {
      setState({ status: 'failed' });
    }
  }, [value]);

  return state;
}

/**
 * The label plate (D18): white rounded backing, an optional black
 * product-code strip on top, the bars, then the guard-split human-readable
 * digits. Empty binding draws the same dashed placeholder every unbound
 * slot draws, so a designer sees the same "nothing here yet" language across
 * layer types. Band heights, padding and font sizes come from
 * `barcodePlateGeometry` (mm of plate), converted to canvas px by `scale` -
 * the SAME numbers the print page reaches by converting to `pt` instead, so
 * the two cannot draw a differently-proportioned plate.
 */
function BarcodeContent({
  w,
  h,
  scale,
  showCode,
  value,
  code,
}: {
  w: number;
  h: number;
  scale: number;
  showCode: boolean;
  value: string | null;
  code: string | null | undefined;
}) {
  const symbology = barcodeSymbologyFor(value);
  const barsState = useBarcodeCanvas(value);

  if (!value || !symbology) {
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
          text="barcode"
          align="center"
          verticalAlign="middle"
          fontSize={Math.min(11, w / 6)}
          fill="#3b82f6"
        />
      </>
    );
  }

  const geo = barcodePlateGeometry(px2mm(w, scale), px2mm(h, scale), showCode && !!code);
  const strip = mm2px(geo.stripHeight_mm, scale);
  const humanH = mm2px(geo.humanHeight_mm, scale);
  const barsY = mm2px(geo.barsY_mm, scale);
  const barsH = mm2px(geo.barsHeight_mm, scale);

  return (
    <>
      <Rect width={w} height={h} fill="#ffffff" cornerRadius={mm2px(geo.cornerRadius_mm, scale)} />
      {strip > 0 && (
        <>
          <Rect width={w} height={strip} fill="#000000" />
          <Text
            width={w}
            height={strip}
            text={code ?? ''}
            align="center"
            verticalAlign="middle"
            fontSize={mm2px(geo.stripFontSize_mm, scale)}
            fontStyle="bold"
            fill="#ffffff"
          />
        </>
      )}
      {barsState.status === 'ready' ? (
        <KonvaImage
          image={barsState.canvas}
          x={mm2px(geo.barsX_mm, scale)}
          y={barsY}
          width={mm2px(geo.barsWidth_mm, scale)}
          height={barsH}
        />
      ) : barsState.status === 'failed' ? (
        <>
          <Rect
            x={mm2px(geo.barsX_mm, scale)}
            y={barsY}
            width={mm2px(geo.barsWidth_mm, scale)}
            height={barsH}
            fill="transparent"
            stroke="#dc2626"
            strokeWidth={1}
            dash={[4, 4]}
          />
          <Text
            width={w}
            y={barsY}
            height={barsH}
            text="cannot encode"
            align="center"
            verticalAlign="middle"
            fontSize={9}
            fill="#dc2626"
          />
        </>
      ) : (
        <Text
          width={w}
          y={barsY}
          height={barsH}
          text="Loading"
          align="center"
          verticalAlign="middle"
          fontSize={9}
          fill="#999999"
        />
      )}
      <Text
        width={w}
        y={h - humanH}
        height={humanH}
        text={humanReadableBarcode(value, symbology)}
        align="center"
        verticalAlign="middle"
        fontSize={mm2px(geo.humanFontSize_mm, scale)}
        fontFamily="monospace"
        fill="#000000"
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Price badge (D26)
// ---------------------------------------------------------------------------

/**
 * The badge, composed by `priceBadgeParts` so this and the DOM print renderer
 * cannot disagree about what a promotional price looks like.
 */
function PriceBadgeContent({
  w,
  h,
  scale,
  props,
  input,
}: {
  w: number;
  h: number;
  scale: number;
  props: Extract<TagLayerProps, { kind: 'price_badge' }>;
  input: PriceBadgeInput;
}) {
  const parts = priceBadgeParts(props, input);

  if (!parts.boxed) {
    return (
      <Text
        width={w}
        height={h}
        text={parts.plainText}
        align="center"
        verticalAlign="middle"
        fontSize={Math.min(h * 0.6, w / 6)}
        fontStyle="bold"
        fill={parts.amountText ? '#000000' : '#999999'}
      />
    );
  }

  // Struck list price on top, filled box under it. A third of the height for
  // the strike keeps the figure dominant at every layer size.
  const strikeH = parts.struckText ? h * 0.3 : 0;
  const boxY = strikeH;
  const boxH = h - strikeH;
  const smallFont = Math.max(4, boxH * 0.28);
  const bigFont = Math.max(6, boxH * 0.5);

  return (
    <>
      {parts.struckText && (
        <Text
          width={w}
          height={strikeH}
          text={parts.struckText}
          align="center"
          verticalAlign="middle"
          fontSize={Math.max(4, strikeH * 0.7)}
          fill="#666666"
          textDecoration="line-through"
        />
      )}
      <Rect
        y={boxY}
        width={w}
        height={boxH}
        fill={props.fill}
        cornerRadius={mm2px(props.cornerRadius, scale)}
      />
      {parts.spLabel && (
        <Text
          x={w * 0.04}
          y={boxY + boxH * 0.1}
          width={w * 0.2}
          height={boxH * 0.4}
          text={parts.spLabel}
          fontSize={smallFont}
          fontStyle="bold"
          fill={props.textColor}
          verticalAlign="middle"
        />
      )}
      <Text
        y={boxY + boxH * 0.15}
        width={w}
        height={boxH * 0.55}
        text={parts.amountText}
        align="center"
        verticalAlign="middle"
        fontSize={bigFont}
        fontStyle="bold"
        fill={props.textColor}
      />
      {parts.nettLabel && (
        <Text
          y={boxY + boxH * 0.7}
          width={w}
          height={boxH * 0.28}
          text={parts.nettLabel}
          align="center"
          verticalAlign="middle"
          fontSize={smallFont}
          fontStyle="bold"
          fill={props.textColor}
        />
      )}
    </>
  );
}
