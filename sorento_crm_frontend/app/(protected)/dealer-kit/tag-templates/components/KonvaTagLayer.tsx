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
import { Ellipse, Group, Image as KonvaImage, Line, Path, Rect, Text } from 'react-konva';
import type Konva from 'konva';
import JsBarcode from 'jsbarcode';
import type { LayerPadding, TagLayer, TagLayerProps } from '@/lib/dealer-kit/tag-template-types';
import type { PriceBadgeInput, PriceBadgeTypography } from '@/lib/dealer-kit/price-badge';
import { priceBadgeInsets, priceBadgeParts, priceBadgeTypography } from '@/lib/dealer-kit/price-badge';
import type { TagLayerDisplay } from '@/lib/dealer-kit/product-block';
import {
  barcodePlateGeometry,
  barcodeSymbologyFor,
  humanReadableBarcode,
} from '@/lib/dealer-kit/barcode';
import {
  polygonPoints,
  roundedPolygonPath,
  scalePolygonPoints,
} from '@/lib/dealer-kit/polygon-path';
import { paddedBox } from '@/lib/dealer-kit/text-reflow';
import { cropPixels, fittedCropDraw, type CropRect } from '@/lib/dealer-kit/image-crop';
import { useHtmlImage } from './useHtmlImage';

// `TagLayerDisplay` is resolved by whoever owns the data (the editor, the
// designer) and handed DOWN: the canvas draws layers and knows nothing about
// products, which is what lets one component render a template, a placed tag
// and a preview.
export type { TagLayerDisplay };

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
  /**
   * The GHOST pass draws a layer that overflows the artboard at 0.3 so it
   * stays visible past the clip instead of vanishing (S4). Absent = 1, same
   * as every layer before this.
   */
  opacity?: number;
  /**
   * The id reported to `onSelect`/`onDoubleClick`/`onDragStart`/`onDragMove`/
   * `onDragEnd`/`onHoverChange` (S4 fix, #720). The GHOST pass renders with a
   * Konva `id` distinct from the real layer's (`${id}-ghost`, so `stage.
   * findOne` and a test's `getByTestId` never collide with the clipped
   * copy's own node) - but selecting or dragging the GHOST must still act on
   * the REAL layer, which is what this carries. Absent means `layer.id`,
   * the ordinary single-copy case.
   */
  interactionId?: string;
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
  opacity,
  interactionId,
}: KonvaTagLayerProps) {
  if (!layer.visible) return null;

  const x = mm2px(layer.x_mm, scale);
  const y = mm2px(layer.y_mm, scale);
  const w = mm2px(layer.width_mm, scale);
  const h = mm2px(layer.height_mm, scale);
  // The GHOST pass's own Konva id is `${id}-ghost` (S4 fix, #720), but every
  // callback below still has to report the REAL layer it draws - that is
  // what makes clicking or dragging the ghost act on the actual layer.
  const reportId = interactionId ?? layer.id;

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
    onSelect?.(reportId, shiftKey);
  };

  const handleDoubleClick = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    e.cancelBubble = true;
    onDoubleClick?.(reportId);
  };

  const handleDragStart = () => {
    onDragStart?.(reportId);
  };

  const handleDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const node = e.target;
    onDragMove?.(reportId, px2mm(node.x(), scale), px2mm(node.y(), scale));
  };

  const handleDragEnd = (e: Konva.KonvaEventObject<DragEvent>) => {
    const node = e.target;
    // Snap to final position.
    onDragMove?.(reportId, px2mm(node.x(), scale), px2mm(node.y(), scale));
    onDragEnd?.(reportId);
  };

  return (
    <Group
      id={layer.id}
      x={x}
      y={y}
      width={w}
      height={h}
      rotation={layer.rotation_deg}
      opacity={opacity}
      listening={listening}
      draggable={draggable && !layer.locked}
      onMouseDown={handleMouseDown}
      onTouchStart={handleMouseDown}
      onDblClick={handleDoubleClick}
      onDblTap={handleDoubleClick}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      onMouseEnter={() => onHoverChange?.(reportId, true)}
      onMouseLeave={() => onHoverChange?.(reportId, false)}
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
    case 'text': {
      // Padding insets the box the text wraps inside (S3): x/y move the Text
      // node in from the layer's own top-left, width/height shrink to match,
      // clamped at zero rather than going negative (AC-S3-4).
      const inset = paddedBox(w, h, props.padding, scale);
      return (
        <Text
          x={inset.x}
          y={inset.y}
          width={inset.width}
          height={inset.height}
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
    }

    case 'shape':
      return <ShapeContent shape={props.shape} w={w} h={h} scale={scale} props={props} />;

    case 'image':
      return (
        <ImageContent
          w={w}
          h={h}
          url={display?.imageUrl ?? null}
          fit={props.fit}
          maskShape={props.maskShape ?? 'none'}
          cropRect={props.cropRect}
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

    case 'price_badge': {
      // Margin insets the callout (S3b, AC-7/8): the whole badge - callout AND
      // figure - moves in from the layer box. `PriceBadgeContent` never needs
      // to know margin exists, it just gets a smaller box to draw the same
      // way it always has; `padding` is a SEPARATE inset it applies itself,
      // to the figure only.
      const insets = priceBadgeInsets(props);
      const inset = paddedBox(w, h, insets.margin, scale);
      return (
        <Group x={inset.x} y={inset.y}>
          <PriceBadgeContent
            w={inset.width}
            h={inset.height}
            scale={scale}
            props={props}
            padding={insets.padding}
            input={display?.price ?? { listPrice: null, offerPrice: null }}
          />
        </Group>
      );
    }

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
  scale,
  props,
}: {
  shape: string;
  w: number;
  h: number;
  scale: number;
  props: Extract<TagLayerProps, { kind: 'shape' }>;
}) {
  switch (shape) {
    case 'polygon':
      return (
        <Path
          // The SAME builder the print page draws with, so the canvas and the
          // PDF cannot disagree about a corner (S4). The radius is converted
          // mm -> px here because the path is built in canvas pixels.
          data={roundedPolygonPath(
            scalePolygonPoints(polygonPoints(props), w, h),
            mm2px(props.cornerRadius, scale),
          )}
          fill={props.fill === 'transparent' ? undefined : props.fill}
          stroke={props.stroke === 'transparent' ? undefined : props.stroke}
          strokeWidth={props.strokeWidth}
        />
      );
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
  cropRect,
}: {
  w: number;
  h: number;
  url: string | null;
  fit: 'cover' | 'contain' | 'stretch';
  maskShape: 'none' | 'circle';
  cropRect?: CropRect;
}) {
  const image = useHtmlImage(url);

  // A not-yet-loaded (or genuinely 0x0) `HTMLImageElement` reads
  // `naturalWidth`/`naturalHeight` (and so `.width`/`.height`) as 0, which
  // `cropPixels` turns into a 0x0 crop rect - Konva's own `drawImage` throws
  // `InvalidStateError` on a source OR destination rect with a zero
  // dimension (r6 S8 review, #723 - the Versions sheet's "View" crash).
  // `useHtmlImage` only ever resolves `image` from `onload`, so this
  // SHOULD be unreachable once `!image` above is false - checked anyway,
  // since the failure mode is a full-page crash (caught only by the error
  // boundary) rather than a misdrawn picture, and it costs nothing to
  // treat "loaded but 0x0" the same as "not loaded yet".
  if (!image || image.width <= 0 || image.height <= 0) {
    return (
      <>
        <Rect width={w} height={h} fill="#f0f0f0" stroke="#ccc" strokeWidth={1} />
        <Text
          width={w}
          height={h}
          text={url ? 'Fetching image' : 'No image'}
          align="center"
          verticalAlign="middle"
          fontSize={10}
          fill="#999"
        />
      </>
    );
  }

  // Crop applies BEFORE fit (S8): `crop` tells Konva which source pixels to
  // draw, and `fittedCropDraw` (shared with the canvas crop-mode overlay,
  // `TagCanvasEditor.tsx` - r6 S8 review, #723) places the CROPPED region,
  // not the whole picture. Absent `cropRect` resolves to the whole image, so
  // this is a no-op for anything saved before S8.
  const crop = cropPixels(cropRect, image);
  const draw = fittedCropDraw(cropRect, image, fit, w, h);

  const body = (
    <KonvaImage
      image={image}
      crop={crop}
      x={draw.x}
      y={draw.y}
      width={draw.width}
      height={draw.height}
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
 * tell "still in flight" apart from "cannot encode this value" - the two used
 * to share one `null`, which drew the pending placeholder forever on a
 * genuine failure. */
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
          text="Preparing barcode"
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
  padding,
  input,
}: {
  w: number;
  h: number;
  scale: number;
  props: Extract<TagLayerProps, { kind: 'price_badge' }>;
  /** The figure's own inset from the callout's edge (S3b, AC-7). In mm. */
  padding: LayerPadding;
  input: PriceBadgeInput;
}) {
  const parts = priceBadgeParts(props, input);
  const typo = priceBadgeTypography(props);

  // The figure's own size when the layer does not name one: what this badge
  // has always drawn, so a saved badge is unchanged (AC-S6-5).
  const plainFont = badgeFontSize(typo, scale, Math.min(h * 0.6, w / 6));

  if (!parts.boxed) {
    const figure = paddedBox(w, h, padding, scale);
    return (
      <Text
        x={figure.x}
        y={figure.y}
        width={figure.width}
        height={figure.height}
        text={parts.plainText}
        align={typo.align}
        verticalAlign="middle"
        fontFamily={typo.fontFamily ?? undefined}
        fontSize={plainFont}
        fontStyle={badgeFontStyle(typo)}
        textDecoration={badgeTextDecoration(typo)}
        lineHeight={typo.lineHeight ?? undefined}
        letterSpacing={typo.letterSpacing * scale * 0.1}
        fill={parts.amountText ? '#000000' : '#999999'}
      />
    );
  }

  // The flyer's white callout: the badge IS the box (r4b, AC-S6-2), drawn
  // from the layer's own corners through the SAME builder a polygon shape
  // uses, so a slanted edge looks the same here and in the PDF. It keeps the
  // FULL margin-inset box (S3b, AC-7) - only the figure inside it moves for
  // `padding`.
  if (parts.polygonBox) {
    const figure = paddedBox(w, h, padding, scale);
    return (
      <>
        <Path
          data={roundedPolygonPath(
            scalePolygonPoints(polygonPoints(props), w, h),
            mm2px(props.cornerRadius, scale),
          )}
          fill={props.fill === 'transparent' ? undefined : props.fill}
        />
        <Text
          x={figure.x}
          y={figure.y}
          width={figure.width}
          height={figure.height}
          text={parts.plainText}
          align={typo.align}
          verticalAlign="middle"
          fontFamily={typo.fontFamily ?? undefined}
          fontSize={plainFont}
          fontStyle={badgeFontStyle(typo)}
          textDecoration={badgeTextDecoration(typo)}
          lineHeight={typo.lineHeight ?? undefined}
          letterSpacing={typo.letterSpacing * scale * 0.1}
          fill={props.textColor}
        />
      </>
    );
  }

  // Struck list price on top, filled box under it. A third of the height for
  // the strike keeps the figure dominant at every layer size. The filled box
  // itself is the callout and keeps the FULL width/height (S3b, AC-7); the
  // SP/figure/NETT row inside it is the part `padding` insets.
  const strikeH = parts.struckText ? h * 0.3 : 0;
  const boxY = strikeH;
  const boxH = h - strikeH;
  const bigFont = badgeFontSize(typo, scale, Math.max(6, boxH * 0.5));
  // The small parts keep the proportion to the figure they already had, so a
  // custom size moves the whole block together rather than only its middle.
  const smallFont = Math.max(4, bigFont * 0.56);
  const struckFont = Math.max(4, bigFont * 0.6);
  const figure = paddedBox(w, boxH, padding, scale);

  return (
    <>
      {parts.struckText && (
        <Text
          width={w}
          height={strikeH}
          text={parts.struckText}
          align="center"
          verticalAlign="middle"
          fontFamily={typo.fontFamily ?? undefined}
          fontSize={struckFont}
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
      <Group x={figure.x} y={boxY + figure.y}>
        {parts.spLabel && (
          <Text
            x={figure.width * 0.04}
            y={figure.height * 0.1}
            width={figure.width * 0.2}
            height={figure.height * 0.4}
            text={parts.spLabel}
            fontFamily={typo.fontFamily ?? undefined}
            fontSize={smallFont}
            fontStyle="bold"
            fill={props.textColor}
            verticalAlign="middle"
          />
        )}
        <Text
          y={figure.height * 0.15}
          width={figure.width}
          height={figure.height * 0.55}
          text={parts.amountText}
          align={typo.align}
          verticalAlign="middle"
          fontFamily={typo.fontFamily ?? undefined}
          fontSize={bigFont}
          fontStyle={badgeFontStyle(typo)}
          textDecoration={badgeTextDecoration(typo)}
          lineHeight={typo.lineHeight ?? undefined}
          letterSpacing={typo.letterSpacing * scale * 0.1}
          fill={props.textColor}
        />
        {parts.nettLabel && (
          <Text
            y={figure.height * 0.7}
            width={figure.width}
            height={figure.height * 0.28}
            text={parts.nettLabel}
            align="center"
            verticalAlign="middle"
            fontFamily={typo.fontFamily ?? undefined}
            fontSize={smallFont}
            fontStyle="bold"
            fill={props.textColor}
          />
        )}
      </Group>
    </>
  );
}

/**
 * The figure's size in canvas pixels: the layer's own point size when it
 * names one, converted the same way a text layer's is, and otherwise the size
 * this badge already derived from its box (AC-S6-5).
 */
function badgeFontSize(typo: PriceBadgeTypography, scale: number, derived: number): number {
  return typo.fontSize != null ? typo.fontSize * scale * 0.35 : derived;
}

/** The figure is bold unless the layer says otherwise - it always has been. */
function badgeFontStyle(typo: PriceBadgeTypography): string {
  const bold = (typo.fontWeight ?? 700) >= 600;
  return [typo.italic && 'italic', bold && 'bold'].filter(Boolean).join(' ') || 'normal';
}

function badgeTextDecoration(typo: PriceBadgeTypography): string {
  return [typo.underline && 'underline', typo.strikethrough && 'line-through']
    .filter(Boolean)
    .join(' ');
}
