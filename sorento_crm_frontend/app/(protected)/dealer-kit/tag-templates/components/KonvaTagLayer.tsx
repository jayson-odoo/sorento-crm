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

import { useMemo } from 'react';
import { Ellipse, Group, Image as KonvaImage, Line, Path, Rect, Text } from 'react-konva';
import type Konva from 'konva';
import type {
  AccessoriesLayerProps,
  FeatureIconsLayerProps,
  LayerPadding,
  TagAccessory,
  TagAccessoryBoxStyle,
  TagLayer,
  TagLayerProps,
  TextLayerProps,
} from '@/lib/dealer-kit/tag-template-types';
import type { PriceBadgeInput, PriceBadgeTypography } from '@/lib/dealer-kit/price-badge';
import { priceBadgeInsets, priceBadgeParts, priceBadgeTypography } from '@/lib/dealer-kit/price-badge';
import type { TagLayerDisplay } from '@/lib/dealer-kit/product-block';
import { konvaFlip } from '@/lib/dealer-kit/image-flip';
import {
  barcodeSvg,
  barcodeSymbologyFor,
  svgDataUrl,
} from '@/lib/dealer-kit/barcode';
import {
  polygonPoints,
  roundedPolygonPath,
  scalePolygonPoints,
} from '@/lib/dealer-kit/polygon-path';
import { paddedBox } from '@/lib/dealer-kit/text-reflow';
import {
  canvasTextHeight,
  LETTER_SPACING_MM_PER_UNIT,
  runFace,
  textFace,
  textLayerLines,
} from '@/lib/dealer-kit/text-layout';
import { isRich, parseRichText, type RichBlock } from '@/lib/dealer-kit/rich-text';
import { isAdditiveClick, isMacContextClick, isMacPlatform } from '@/lib/dealer-kit/canvas-input';
import { useFontsEpoch } from '@/lib/dealer-kit/use-fonts-epoch';
import { cropPixels, fittedCropDraw, type CropRect } from '@/lib/dealer-kit/image-crop';
import { featureIconRow } from '@/lib/dealer-kit/feature-icons';
import {
  accessoryBoxLayout,
  accessoryCardInner,
  accessoryCardLines,
  accessoryHeaderStyle,
  accessoryLineCount,
  accessoryLineStyle,
  fitLinePt,
  ptToMm,
  sampleAccessories,
  type AccessoryLineStyle,
} from '@/lib/dealer-kit/accessory-box';
import {
  boxColours,
  effectiveBoxProps,
  cardBoxLayout,
  cardElementsFor,
  cardElementsForDesign,
  cardTextProps,
  colourDotLayout,
  DEFAULT_DOT_OUTLINE,
  fitCardTextProps,
  footerElementsFor,
  type ResolvedCardElement,
} from '@/lib/dealer-kit/accessory-card';
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
    const mac = isMacPlatform();
    // macOS Ctrl+click is the system right-click: the context menu resolves its own target and
    // must find the selection as it was (DESIGNER-RICH-TEXT owner bug).
    if ('button' in e.evt && isMacContextClick(e.evt, mac)) return;
    e.cancelBubble = true;
    // Shift+click adds everywhere; Cmd+click on macOS, Ctrl+click elsewhere.
    const additive = 'shiftKey' in e.evt ? isAdditiveClick(e.evt, mac) : false;
    onSelect?.(reportId, additive);
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
      <LayerContent
        props={layer.props}
        w={w}
        h={h}
        widthMm={layer.width_mm}
        heightMm={layer.height_mm}
        scale={scale}
        display={display}
      />
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
  widthMm,
  heightMm,
  scale,
  display,
}: {
  props: TagLayerProps;
  w: number;
  h: number;
  /** The layer box in mm, as stored: what the print page lays out from too. */
  widthMm: number;
  heightMm: number;
  scale: number;
  display?: TagLayerDisplay;
}) {
  switch (props.kind) {
    case 'text': {
      const text = display?.text ?? props.text;
      // A rich description is drawn run by run; plain text keeps its single Text node.
      const blocks = display?.blocks ?? (isRich(text) ? parseRichText(text) : null);
      if (blocks) {
        return (
          <RichTextContent
            props={props}
            w={w}
            h={h}
            widthMm={widthMm}
            heightMm={heightMm}
            scale={scale}
            blocks={blocks}
          />
        );
      }
      return (
        <TextContent
          props={props}
          w={w}
          h={h}
          widthMm={widthMm}
          heightMm={heightMm}
          scale={scale}
          text={text}
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
          flipX={props.flipX}
          flipY={props.flipY}
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

    case 'feature_icons':
      return (
        <FeatureIconsContent
          w={w}
          h={h}
          widthMm={widthMm}
          heightMm={heightMm}
          scale={scale}
          props={props}
          icons={display?.icons ?? []}
        />
      );

    case 'accessories':
      return (
        <AccessoriesContent
          w={w}
          h={h}
          widthMm={widthMm}
          heightMm={heightMm}
          scale={scale}
          props={props}
          accessories={display?.accessories}
          editing={display?.accessoryEditing}
          boxStyle={display?.accessoryBoxStyle}
          headerHidden={display?.accessoryHeaderHidden}
        />
      );

    case 'barcode':
      return (
        <BarcodeContent
          w={w}
          h={h}
          widthMm={widthMm}
          heightMm={heightMm}
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
  flipX,
  flipY,
}: {
  w: number;
  h: number;
  url: string | null;
  fit: 'cover' | 'contain' | 'stretch';
  maskShape: 'none' | 'circle';
  cropRect?: CropRect;
  /** PRICETAG-DESIGNER-GAPS item 1: mirror the picture in place. */
  flipX?: boolean;
  flipY?: boolean;
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

  // Mirroring wraps ONLY the picture, inside any clip below: both clips
  // (circle, cover's box) are symmetric about the box, so the clipped area is
  // the same either way. No wrapper at all when unflipped, so an old document
  // draws the exact same node tree it always did.
  const mirror = konvaFlip({ flipX, flipY }, w, h);
  const picture = (
    <KonvaImage
      image={image}
      crop={crop}
      x={draw.x}
      y={draw.y}
      width={draw.width}
      height={draw.height}
    />
  );
  const body = mirror ? <Group {...mirror}>{picture}</Group> : picture;

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
// Text (PRICETAG-BARCODE-MATCH)
// ---------------------------------------------------------------------------

/**
 * A text layer draws the lines `textLayerLines` breaks it into - the SAME
 * lines the print page prints - with Konva's own wrapping off, in the same
 * face and units (`textFace`). Padding insets the box (S3): x/y move the Text
 * node in from the layer's top-left, width/height shrink to match, clamped at
 * zero (AC-S3-4). The node keeps its full box as its size, so the whole box
 * stays clickable, and carries the unbroken text for a live resize to
 * re-break (`TagCanvasEditor`'s transform handler).
 */
function TextContent({
  props,
  w,
  h,
  widthMm,
  heightMm,
  scale,
  text,
}: {
  props: TextLayerProps;
  w: number;
  h: number;
  widthMm: number;
  heightMm: number;
  scale: number;
  text: string;
}) {
  const epoch = useFontsEpoch();
  const lines = useMemo(() => {
    void epoch; // re-measure once a face has loaded
    return textLayerLines(props, text, widthMm, heightMm);
  }, [props, text, widthMm, heightMm, epoch]);
  const face = textFace(props);
  const inset = paddedBox(w, h, props.padding, scale);

  return (
    <Text
      key={epoch}
      x={inset.x}
      y={inset.y}
      width={inset.width}
      height={canvasTextHeight(inset.height)}
      text={lines.join('\n')}
      sourceText={text}
      fontFamily={face.fontFamily}
      fontSize={mm2px(face.fontSize_mm, scale)}
      fontStyle={face.fontStyle}
      textDecoration={
        [props.underline && 'underline', props.strikethrough && 'line-through']
          .filter(Boolean)
          .join(' ')
      }
      fill={props.color}
      align={props.align}
      lineHeight={props.lineHeight}
      letterSpacing={mm2px(face.letterSpacing_mm, scale)}
      wrap="none"
    />
  );
}

/**
 * A rich description (PRICETAG-COMBO-FORMAT): one Konva Text per run, in the run's own face,
 * colour and decoration, on the lines `textLayerLines` breaks the blocks into - the SAME lines the
 * print page prints. Family and base size stay the layer's; a heading is the layer size times its
 * factor. A highlighted run gets a rectangle behind it. The transparent rectangle keeps the whole
 * box clickable, as the plain Text node's full-size box does.
 */
function RichTextContent({
  props,
  w,
  h,
  widthMm,
  heightMm,
  scale,
  blocks,
}: {
  props: TextLayerProps;
  w: number;
  h: number;
  widthMm: number;
  heightMm: number;
  scale: number;
  blocks: RichBlock[];
}) {
  const epoch = useFontsEpoch();
  const lines = useMemo(() => {
    void epoch; // re-measure once a face has loaded
    return textLayerLines(props, blocks, widthMm, heightMm);
  }, [props, blocks, widthMm, heightMm, epoch]);
  const inset = paddedBox(w, h, props.padding, scale);

  return (
    <Group name="rich-text" key={epoch}>
      <Rect width={w} height={h} fill="transparent" />
      {lines.flatMap((line, lineIndex) =>
        line
          .filter((run) => run.text !== '')
          .flatMap((run, runIndex) => {
            const face = runFace(props, run, run.sizeFactor);
            const x = inset.x + mm2px(run.x_mm, scale);
            const y = inset.y + mm2px(run.y_mm, scale);
            const decoration = [
              (props.underline || run.underline) && 'underline',
              (props.strikethrough || run.strike) && 'line-through',
            ]
              .filter(Boolean)
              .join(' ');
            const key = `${lineIndex}:${runIndex}`;
            return [
              ...(run.highlight
                ? [
                    <Rect
                      key={`${key}:bg`}
                      x={x}
                      y={y}
                      width={mm2px(run.width_mm, scale)}
                      height={mm2px(face.fontSize_mm, scale)}
                      fill={run.highlight}
                    />,
                  ]
                : []),
              <Text
                key={key}
                x={x}
                y={y}
                text={run.text}
                fontFamily={face.fontFamily}
                fontSize={mm2px(face.fontSize_mm, scale)}
                fontStyle={face.fontStyle}
                textDecoration={decoration}
                fill={run.color || props.color}
                lineHeight={props.lineHeight}
                letterSpacing={mm2px(face.letterSpacing_mm, scale)}
                wrap="none"
              />,
            ];
          }),
      )}
    </Group>
  );
}

// ---------------------------------------------------------------------------
// Barcode (D18, S7)
// ---------------------------------------------------------------------------

/**
 * The barcode label (D18, PRICETAG-BARCODE-MATCH): the SAME SVG the request
 * preview and the printed PDF draw (`barcodeSvg`, `TagSheetRenderer`), loaded
 * as an image and drawn over the whole layer box. Konva draws none of the
 * code, bars or digits itself, so the canvas cannot lay them out differently
 * from the print page at any zoom.
 *
 * Empty binding draws the same dashed placeholder every unbound slot draws.
 * A value that cannot be encoded shows a distinct failure state, never the
 * "still loading" text forever.
 */
function BarcodeContent({
  w,
  h,
  widthMm,
  heightMm,
  showCode,
  value,
  code,
}: {
  w: number;
  h: number;
  widthMm: number;
  heightMm: number;
  showCode: boolean;
  value: string | null;
  code: string | null | undefined;
}) {
  const symbology = barcodeSymbologyFor(value);
  const url = useMemo(() => {
    if (!symbology) return null;
    const svg = barcodeSvg({ value, code, showCode, widthMm, heightMm });
    return svg ? svgDataUrl(svg) : null;
  }, [symbology, value, code, showCode, widthMm, heightMm]);
  const image = useHtmlImage(url);

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

  if (!url) {
    return (
      <>
        <Rect
          width={w}
          height={h}
          fill="transparent"
          stroke="#dc2626"
          strokeWidth={1}
          dash={[4, 4]}
        />
        <Text
          width={w}
          height={h}
          text="cannot encode"
          align="center"
          verticalAlign="middle"
          fontSize={9}
          fill="#dc2626"
        />
      </>
    );
  }

  if (!image) {
    return (
      <Text
        width={w}
        height={h}
        text="Preparing barcode"
        align="center"
        verticalAlign="middle"
        fontSize={9}
        fill="#999999"
      />
    );
  }

  return <KonvaImage image={image} width={w} height={h} />;
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
        // D22 (AC-S17-1) / blocker follow-up: `priceBadgeParts` resolves the
        // colour once, since a `promo` badge that fell through to this same
        // unboxed branch must NOT honour its own (white, boxed-callout)
        // `textColor` here - see `amountColor`'s own doc.
        fill={parts.amountColor}
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

// ---------------------------------------------------------------------------
// Feature icons (PRICETAG-DESIGNER-GAPS item 3)
// ---------------------------------------------------------------------------

/**
 * One packed row of the matched icons, laid out by `featureIconRow` (the print page uses the
 * same function), each vertically centred in the box. No icon: the dashed "Feature icons"
 * outline, so the designer can still place and size the layer.
 */
function FeatureIconsContent({
  w,
  h,
  widthMm,
  heightMm,
  scale,
  props,
  icons,
}: {
  w: number;
  h: number;
  widthMm: number;
  heightMm: number;
  scale: number;
  props: FeatureIconsLayerProps;
  icons: { id: string; url: string }[];
}) {
  const xs = featureIconRow(icons.length, props, widthMm);
  if (xs.length === 0) {
    return (
      <>
        <Rect width={w} height={h} fill="transparent" stroke="#3b82f6" strokeWidth={1} dash={[4, 4]} />
        <Text
          width={w}
          height={h}
          text="Feature icons"
          align="center"
          verticalAlign="middle"
          fontSize={Math.min(11, w / 8)}
          fill="#3b82f6"
        />
      </>
    );
  }
  const size = mm2px(props.iconSize_mm, scale);
  const y = mm2px((heightMm - props.iconSize_mm) / 2, scale);
  return (
    <>
      {xs.map((x, i) => (
        <Group key={`${icons[i].id}-${i}`} x={mm2px(x, scale)} y={y}>
          <ImageContent w={size} h={size} url={icons[i].url} fit="contain" maskShape="none" />
        </Group>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Accessories box (PRICETAG-ACCESSORIES)
// ---------------------------------------------------------------------------

/**
 * The styled box with one mini-card per accessory, laid out by `accessoryBoxLayout` (the print page
 * uses the same function). `accessories` undefined = nothing bound (the template editor with no
 * preview): two sample cards so the box can be styled. An empty list: the dashed "Accessories"
 * outline here, nothing on print (A7).
 */
function AccessoriesContent({
  w,
  h,
  widthMm,
  heightMm,
  scale,
  props: ownProps,
  accessories,
  editing,
  boxStyle,
  headerHidden,
}: {
  w: number;
  h: number;
  widthMm: number;
  heightMm: number;
  scale: number;
  props: AccessoriesLayerProps;
  accessories: TagAccessory[] | undefined;
  editing?: boolean;
  boxStyle?: TagAccessoryBoxStyle | null;
  headerHidden?: boolean;
}) {
  // The previewed product / combo may name its own box style: it replaces the design, not the place.
  const props = effectiveBoxProps(ownProps, boxStyle);
  // A box with a designed card takes its own path; one without keeps the legacy cards below.
  if (props.card) {
    return (
      <DesignedAccessoriesContent
        w={w}
        h={h}
        widthMm={widthMm}
        heightMm={heightMm}
        scale={scale}
        props={props}
        accessories={accessories}
        editing={editing}
        headerHidden={headerHidden}
      />
    );
  }
  const items = accessories ?? sampleAccessories();
  const lineCount = accessoryLineCount(items);
  const box = accessoryBoxLayout(
    items.length,
    props,
    widthMm,
    heightMm,
    lineCount,
  );
  if (box.shown === 0) {
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
          text="Accessories"
          align="center"
          verticalAlign="middle"
          fontSize={Math.min(11, w / 8)}
          fill="#3b82f6"
        />
      </>
    );
  }
  const px = (mm: number) => mm2px(mm, scale);
  const header = accessoryHeaderStyle(props);
  return (
    <>
      {box.frame && (
        <Rect
          y={px(box.frame.y_mm)}
          width={px(box.frame.width_mm)}
          height={px(box.frame.height_mm)}
          fill={props.fill}
          stroke={props.stroke}
          strokeWidth={px(props.strokeWidth_mm)}
          cornerRadius={px(props.cornerRadius_mm)}
        />
      )}
      {!headerHidden && box.header?.onBorder && (
        // Breaks the border behind a header that sits on it (legend style).
        <Rect
          x={px(box.header.x_mm)}
          y={px(box.header.y_mm)}
          width={px(box.header.width_mm)}
          height={px(box.header.height_mm)}
          fill={props.headerBackground || '#ffffff'}
        />
      )}
      {!headerHidden && box.header && (
        <Text
          x={px(box.header.x_mm)}
          y={px(box.header.y_mm)}
          width={px(box.header.width_mm)}
          height={px(box.header.height_mm)}
          text={props.headerText}
          align={box.header.onBorder || box.header.moved ? 'center' : header.align}
          verticalAlign="middle"
          fontStyle={konvaFontStyle(header)}
          textDecoration={konvaDecoration(header)}
          fontFamily={header.fontFamily ?? undefined}
          letterSpacing={px(header.letterSpacing * LETTER_SPACING_MM_PER_UNIT)}
          fontSize={px(ptToMm(box.header.fontSize_pt))}
          fill={header.color}
          wrap="none"
        />
      )}
      {box.cards.map((card, i) => {
        const item = items[i];
        const inner = accessoryCardInner(card, props, Boolean(item.image?.url), lineCount);
        const texts = accessoryCardLines(item);
        return (
          <Group key={`${item.id}-${i}`} x={px(card.x_mm)} y={px(card.y_mm)}>
            <Rect
              width={px(card.width_mm)}
              height={px(card.height_mm)}
              fill={props.cardFill}
              cornerRadius={px(Math.min(props.cornerRadius_mm, 1.5))}
            />
            {inner.image && (
              <Group x={px(inner.image.x_mm)} y={px(inner.image.y_mm)}>
                <ImageContent
                  w={px(inner.image.width_mm)}
                  h={px(inner.image.height_mm)}
                  url={item.image?.url ?? null}
                  fit="contain"
                  maskShape="none"
                />
              </Group>
            )}
            {inner.lines.map((line, n) => {
              if (!texts[n]) return null;
              const style = accessoryLineStyle(props, n);
              const basePt = n === 0 ? props.nameFontSize : props.specFontSize;
              return (
                <Text
                  key={n}
                  x={px(line.x_mm)}
                  y={px(line.y_mm)}
                  width={px(line.width_mm)}
                  height={px(line.height_mm)}
                  text={texts[n]}
                  align={style.align}
                  verticalAlign="middle"
                  fontStyle={konvaFontStyle(style)}
                  textDecoration={konvaDecoration(style)}
                  fontFamily={style.fontFamily ?? undefined}
                  letterSpacing={px(style.letterSpacing * LETTER_SPACING_MM_PER_UNIT)}
                  fontSize={px(ptToMm(fitLinePt(texts[n], line.width_mm, basePt, style.bold)))}
                  fill={style.color}
                  wrap="none"
                />
              );
            })}
          </Group>
        );
      })}
      {box.badge && (
        <Group x={px(box.badge.x_mm)} y={px(box.badge.y_mm)}>
          <>
            <Ellipse
              x={px(box.badge.width_mm / 2)}
              y={px(box.badge.height_mm / 2)}
              radiusX={px(box.badge.width_mm / 2)}
              radiusY={px(box.badge.height_mm / 2)}
              fill={props.badgeColor}
            />
            <Text
              width={px(box.badge.width_mm)}
              height={px(box.badge.height_mm)}
              text="+"
              align="center"
              verticalAlign="middle"
              fontStyle="bold"
              fontSize={px(box.badge.height_mm * 0.9)}
              fill="#ffffff"
            />
          </>
        </Group>
      )}
    </>
  );
}

/**
 * PRICETAG-ACCESSORY-DESIGNER: a box with a designed `card`. The frame, header and badge are the
 * legacy ones; each shown card is drawn at the layout's `scale` with the elements
 * `cardElementsFor` resolves for that accessory; the footer follows the cards. The print page
 * draws the same layout (`cardBoxLayout`), so the two cannot disagree.
 */
function DesignedAccessoriesContent({
  w,
  h,
  widthMm,
  heightMm,
  scale,
  props,
  accessories,
  editing,
  headerHidden,
}: {
  w: number;
  h: number;
  widthMm: number;
  heightMm: number;
  scale: number;
  props: AccessoriesLayerProps;
  accessories: TagAccessory[] | undefined;
  editing?: boolean;
  headerHidden?: boolean;
}) {
  const items = accessories ?? sampleAccessories();
  const box = cardBoxLayout(items.length, props, widthMm, heightMm);
  if (box.shown === 0) {
    return (
      <>
        <Rect width={w} height={h} fill="transparent" stroke="#3b82f6" strokeWidth={1} dash={[4, 4]} />
        <Text
          width={w}
          height={h}
          text="Accessories"
          align="center"
          verticalAlign="middle"
          fontSize={Math.min(11, w / 8)}
          fill="#3b82f6"
        />
      </>
    );
  }
  const px = (mm: number) => mm2px(mm, scale);
  const header = accessoryHeaderStyle(props);
  const shownItems = items.slice(0, box.shown);
  return (
    <>
      {box.frame && (
        <Rect
          y={px(box.frame.y_mm)}
          width={px(box.frame.width_mm)}
          height={px(box.frame.height_mm)}
          fill={props.fill}
          stroke={props.stroke}
          strokeWidth={px(props.strokeWidth_mm)}
          cornerRadius={px(props.cornerRadius_mm)}
        />
      )}
      {!headerHidden && box.header?.onBorder && (
        <Rect
          x={px(box.header.x_mm)}
          y={px(box.header.y_mm)}
          width={px(box.header.width_mm)}
          height={px(box.header.height_mm)}
          fill={props.headerBackground || '#ffffff'}
        />
      )}
      {!headerHidden && box.header && (
        <Text
          x={px(box.header.x_mm)}
          y={px(box.header.y_mm)}
          width={px(box.header.width_mm)}
          height={px(box.header.height_mm)}
          text={props.headerText}
          align={box.header.onBorder || box.header.moved ? 'center' : header.align}
          verticalAlign="middle"
          fontStyle={konvaFontStyle(header)}
          textDecoration={konvaDecoration(header)}
          fontFamily={header.fontFamily ?? undefined}
          letterSpacing={px(header.letterSpacing * LETTER_SPACING_MM_PER_UNIT)}
          fontSize={px(ptToMm(box.header.fontSize_pt))}
          fill={header.color}
          wrap="none"
        />
      )}
      {box.cards.map((card, i) => {
        const item = items[i];
        return (
          <Group
            key={`${item.id}-${i}`}
            x={px(card.x_mm)}
            y={px(card.y_mm)}
            // While a card is edited the first one is the editable frame; the rest follow, faded.
            opacity={editing && i > 0 ? 0.45 : 1}
          >
            <Rect
              width={px(card.width_mm)}
              height={px(card.height_mm)}
              fill={props.cardFill}
              cornerRadius={px(Math.min(props.cornerRadius_mm, 1.5))}
            />
            {(editing && i === 0
              ? cardElementsForDesign(item, props.card!)
              : cardElementsFor(item, props.card!)
            ).map((element) => (
              <CardElementNode
                key={element.id}
                element={element}
                factor={box.scale}
                scale={scale}
                boxFont={props.fontFamily}
              />
            ))}
          </Group>
        );
      })}
      {box.footer && props.footer && (
        <Group x={px(box.footer.x_mm)} y={px(box.footer.y_mm)}>
          {footerElementsFor(boxColours(shownItems), props.footer).map((element) => (
            <CardElementNode
              key={element.id}
              element={element}
              factor={1}
              scale={scale}
              boxFont={props.fontFamily}
            />
          ))}
        </Group>
      )}
      {box.badge && (
        <Group x={px(box.badge.x_mm)} y={px(box.badge.y_mm)}>
          <Ellipse
            x={px(box.badge.width_mm / 2)}
            y={px(box.badge.height_mm / 2)}
            radiusX={px(box.badge.width_mm / 2)}
            radiusY={px(box.badge.height_mm / 2)}
            fill={props.badgeColor}
          />
          <Text
            width={px(box.badge.width_mm)}
            height={px(box.badge.height_mm)}
            text="+"
            align="center"
            verticalAlign="middle"
            fontStyle="bold"
            fontSize={px(box.badge.height_mm * 0.9)}
            fill="#ffffff"
          />
        </Group>
      )}
    </>
  );
}

/** One resolved card (or footer) element at `factor` (the card's shrink), `scale` px per mm. */
function CardElementNode({
  element,
  factor,
  scale,
  boxFont,
}: {
  element: ResolvedCardElement;
  factor: number;
  scale: number;
  boxFont?: string;
}) {
  const px = (mm: number) => mm2px(mm * factor, scale);
  const x = px(element.x_mm);
  const y = px(element.y_mm);
  const wMm = element.width_mm * factor;
  const hMm = element.height_mm * factor;
  switch (element.kind) {
    case 'picture':
      if (element.placeholder) {
        // Designer only: where a picture goes, never printed.
        return (
          <Rect
            x={x}
            y={y}
            width={px(element.width_mm)}
            height={px(element.height_mm)}
            fill="#e5e7eb"
            stroke="#9ca3af"
            strokeWidth={1}
            listening={false}
          />
        );
      }
      return (
        <Group x={x} y={y}>
          <ImageContent
            w={px(element.width_mm)}
            h={px(element.height_mm)}
            url={element.src ?? null}
            fit={element.fit ?? 'contain'}
            maskShape="none"
          />
        </Group>
      );
    case 'text':
      return (
        <Group x={x} y={y}>
          <CardTextNode
            element={element}
            widthMm={wMm}
            heightMm={hMm}
            factor={factor}
            scale={scale}
            boxFont={boxFont}
          />
        </Group>
      );
    case 'colour_dots': {
      const colours = element.colours ?? [];
      const dots = colourDotLayout(element, colours.length, factor);
      return (
        <Group x={x} y={y}>
          {dots.map((dot, i) => (
            <Ellipse
              key={i}
              x={mm2px(dot.x_mm + dot.d_mm / 2, scale)}
              y={mm2px(dot.y_mm + dot.d_mm / 2, scale)}
              radiusX={mm2px(dot.d_mm / 2, scale)}
              radiusY={mm2px(dot.d_mm / 2, scale)}
              fill={colours[i]}
              stroke={element.dotOutline || DEFAULT_DOT_OUTLINE}
              strokeWidth={mm2px(0.15 * factor, scale)}
            />
          ))}
        </Group>
      );
    }
    case 'shape': {
      const w = px(element.width_mm);
      const h = px(element.height_mm);
      const stroke = element.stroke || undefined;
      const strokeWidth = px(element.strokeWidth_mm ?? 0.2);
      if (element.shape === 'ellipse') {
        return (
          <Ellipse
            x={x + w / 2}
            y={y + h / 2}
            radiusX={w / 2}
            radiusY={h / 2}
            fill={element.fill || undefined}
            stroke={stroke}
            strokeWidth={stroke ? strokeWidth : 0}
          />
        );
      }
      if (element.shape === 'line') {
        // A rule along the longer side, in the stroke colour.
        const thick = Math.min(Math.max(strokeWidth, 1), Math.max(w, h));
        const horizontal = w >= h;
        return (
          <Rect
            x={x}
            y={horizontal ? y + (h - thick) / 2 : y}
            width={horizontal ? w : thick}
            height={horizontal ? thick : h}
            fill={element.stroke || element.fill || '#111827'}
          />
        );
      }
      return (
        <Rect
          x={x}
          y={y}
          width={w}
          height={h}
          fill={element.fill || undefined}
          stroke={stroke}
          strokeWidth={stroke ? strokeWidth : 0}
          cornerRadius={element.shape === 'rounded_rect' ? px(element.cornerRadius_mm ?? 1) : 0}
        />
      );
    }
  }
}

/** A text element: plain or rich, shrunk until it sits inside its rect (never spills, never cut). */
function CardTextNode({
  element,
  widthMm,
  heightMm,
  factor,
  scale,
  boxFont,
}: {
  element: ResolvedCardElement;
  widthMm: number;
  heightMm: number;
  factor: number;
  scale: number;
  boxFont?: string;
}) {
  const epoch = useFontsEpoch();
  const text = element.text ?? '';
  const props = useMemo(() => {
    void epoch; // re-measure once a face has loaded
    return fitCardTextProps(cardTextProps(element, factor, boxFont), text, widthMm, heightMm);
  }, [element, factor, boxFont, text, widthMm, heightMm, epoch]);
  const w = mm2px(widthMm, scale);
  const h = mm2px(heightMm, scale);
  if (isRich(text)) {
    return (
      <RichTextContent
        props={props}
        w={w}
        h={h}
        widthMm={widthMm}
        heightMm={heightMm}
        scale={scale}
        blocks={parseRichText(text)}
      />
    );
  }
  return (
    <TextContent props={props} w={w} h={h} widthMm={widthMm} heightMm={heightMm} scale={scale} text={text} />
  );
}

/** Konva's `fontStyle` for an accessory text role: "normal", "bold", "italic" or "italic bold". */
function konvaFontStyle(style: AccessoryLineStyle): string {
  return [style.italic && 'italic', style.bold && 'bold'].filter(Boolean).join(' ') || 'normal';
}

/** Konva's `textDecoration`: "underline", "line-through", both, or "". */
function konvaDecoration(style: AccessoryLineStyle): string {
  return [style.underline && 'underline', style.strikethrough && 'line-through']
    .filter(Boolean)
    .join(' ');
}
