/**
 * Pure DOM/CSS renderer for tag sheets.
 *
 * Renders each sheet as an A4-sized div with absolutely positioned tags, each
 * tag containing its layers as DOM elements. This is deliberately NOT Konva:
 * Chromium's page.pdf() needs DOM for reliable rendering.
 *
 * Positions and sizes are in millimetres throughout, converted to CSS mm units.
 * The renderer is theme-independent: white background, explicit colours, no
 * CSS variables.
 */

import { useMemo, type CSSProperties } from 'react';
import JsBarcode from 'jsbarcode';

import type {
  ImpositionConfig,
  PlacedTag,
  TagBindingData,
  TagImage,
  TagLayer,
  TagSheetDoc,
  TagSheet,
  TagSpecValue,
} from '@/lib/dealer-kit/tag-template-types';
import { imageSourceOf } from '@/lib/dealer-kit/tag-template-types';
import {
  layerText,
  resolveBarcodeValue,
  resolveSlotText,
  slotImageAttachmentId,
} from '@/lib/dealer-kit/product-block';
import { priceBadgeParts } from '@/lib/dealer-kit/price-badge';
import {
  barcodePlateGeometry,
  barcodeSymbologyFor,
  humanReadableBarcode,
  MM_TO_PT,
} from '@/lib/dealer-kit/barcode';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ResolvedLineData {
  line_id: string;
  code: string;
  name: string;
  dimensions: string;
  spec_lines: string;
  list_price: number | null;
  sell_price: number | null;
  show_promo_price: boolean;
  included_accessories: string;
  quantity: number;
  /** One line per member, already formatted, for a set line. */
  set_members?: string;
  /**
   * The line's reviewed specs, key by key, so `{{spec.<key>}}` resolves in the
   * PDF exactly as it did on the canvas (D58).
   */
  specs?: TagSpecValue[];
  /**
   * The line's photos, primary first, as the payload resolved them.
   *
   * Carried beside the text because a product-photo slot follows the PRODUCT
   * (D42), and a template ships with `source: null`: without the list there is
   * no way to know which attachment is the primary one, and the tag prints an
   * empty box where the picture goes.
   */
  images?: TagImage[];
  /** `products.barcode` (D14/S7). Null/absent for a set line or a product with
   * none - the barcode layer renders nothing on print for either. */
  barcode?: string | null;
}

/**
 * Every picture the sheet may need, signed at payload time.
 *
 * `assets` is keyed by dealer-kit asset id, `images` by product attachment id.
 * Sent WITH the payload rather than fetched here, for the same reason the
 * catalogue print page takes its backgrounds that way: the worker waits on one
 * ready flag, and an image that starts loading after it prints as a blank box.
 */
export interface TagSheetMedia {
  assets?: Record<string, string>;
  images?: Record<string, string>;
}

interface TagSheetRendererProps extends TagSheetMedia {
  doc: TagSheetDoc;
  resolvedData: Record<string, ResolvedLineData>;
  /** When true, render at a scaled-down size for preview (not print). */
  preview?: boolean;
  /** Scale factor for preview mode (default 0.3). */
  previewScale?: number;
}

// ---------------------------------------------------------------------------
// Layer renderers (pure DOM)
// ---------------------------------------------------------------------------

/**
 * The payload's line as a binding, so the print page can ask the SAME question
 * the canvas asks.
 *
 * `ResolvedLineData` is `LineTagData` with two fields the payload may omit, so
 * this is an adaptation rather than a second model. It is what lets a text
 * layer resolve through `layerText` here: this file used to carry its own
 * switch over `slot_binding`, which is exactly the kind of second copy that
 * eventually prints a different word than the proof showed.
 */
function bindingOf(resolved: ResolvedLineData | null): TagBindingData | null {
  if (!resolved) return null;
  return {
    kind: 'line',
    line: {
      ...resolved,
      set_members: resolved.set_members ?? '',
      specs: resolved.specs ?? [],
      images: resolved.images ?? [],
      barcode: resolved.barcode ?? null,
    },
  };
}

function renderTextLayer(layer: TagLayer, resolved: ResolvedLineData | null) {
  const props = layer.props;
  if (props.kind !== 'text') return null;

  const text = layerText(layer, bindingOf(resolved), 'print');

  return (
    <div
      style={{
        position: 'absolute',
        left: `${layer.x_mm}mm`,
        top: `${layer.y_mm}mm`,
        width: `${layer.width_mm}mm`,
        height: `${layer.height_mm}mm`,
        transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
        fontFamily: props.fontFamily || 'DM Sans, sans-serif',
        fontSize: `${props.fontSize}pt`,
        fontWeight: props.fontWeight,
        color: props.color,
        textAlign: props.align,
        lineHeight: props.lineHeight,
        letterSpacing: props.letterSpacing ? `${props.letterSpacing}px` : undefined,
        overflow: 'hidden',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {text}
    </div>
  );
}

function renderShapeLayer(layer: TagLayer) {
  const props = layer.props;
  if (props.kind !== 'shape') return null;

  const isEllipse = props.shape === 'ellipse';
  const isLine = props.shape === 'line';

  return (
    <div
      style={{
        position: 'absolute',
        left: `${layer.x_mm}mm`,
        top: `${layer.y_mm}mm`,
        width: `${layer.width_mm}mm`,
        height: isLine ? '0' : `${layer.height_mm}mm`,
        transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
        backgroundColor: isLine ? 'transparent' : props.fill,
        border: isLine
          ? 'none'
          : props.strokeWidth
            ? `${props.strokeWidth}mm solid ${props.stroke}`
            : 'none',
        borderTop: isLine
          ? `${props.strokeWidth || 0.5}mm solid ${props.stroke}`
          : undefined,
        borderRadius: isEllipse
          ? '50%'
          : props.cornerRadius
            ? `${props.cornerRadius}mm`
            : undefined,
      }}
    />
  );
}

/**
 * The URL a layer prints, or null when nothing could be signed for it.
 *
 * `slotImageAttachmentId` is the SAME rule the canvas resolves a product photo
 * by (D42), so the proof on screen and the PDF cannot pick different pictures.
 */
function imageUrlFor(
  layer: TagLayer,
  media: TagSheetMedia,
  resolved: ResolvedLineData | null,
): string | null {
  const props = layer.props;
  if (props.kind === 'image') {
    const source = imageSourceOf(props);
    if (source?.type === 'asset') return media.assets?.[source.assetId] ?? null;
  } else if (props.kind !== 'product_slot') {
    return null;
  }
  const attachmentId = slotImageAttachmentId(layer, resolved?.images ?? []);
  return attachmentId ? media.images?.[attachmentId] ?? null : null;
}

function renderImageLayer(
  layer: TagLayer,
  media: TagSheetMedia,
  resolved: ResolvedLineData | null,
) {
  const props = layer.props;
  if (props.kind !== 'image') return null;

  const url = imageUrlFor(layer, media, resolved);
  const circle = props.maskShape === 'circle';

  return (
    <div
      style={{
        position: 'absolute',
        left: `${layer.x_mm}mm`,
        top: `${layer.y_mm}mm`,
        width: `${layer.width_mm}mm`,
        height: `${layer.height_mm}mm`,
        transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
        overflow: 'hidden',
        borderRadius: circle ? '50%' : undefined,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: url ? 'transparent' : '#f5f5f5',
      }}
    >
      {url && (
        <img
          src={url}
          alt=""
          style={{
            width: '100%',
            height: '100%',
            objectFit: props.fit === 'cover' ? 'cover' : 'contain',
          }}
        />
      )}
    </div>
  );
}

/**
 * The price badge, composed by the SAME helper the Konva editor uses.
 *
 * That shared call is the whole point of the layer type: the proof a
 * salesperson approves on screen and the PDF that reaches the printer state the
 * same price in the same shape (AC-L.1).
 */
function renderPriceBadgeLayer(layer: TagLayer, resolved: ResolvedLineData | null) {
  const props = layer.props;
  if (props.kind !== 'price_badge') return null;

  const parts = priceBadgeParts(props, {
    listPrice: resolved?.list_price ?? null,
    offerPrice:
      resolved && resolved.show_promo_price ? resolved.sell_price ?? null : null,
  });

  const frame: CSSProperties = {
    position: 'absolute',
    left: `${layer.x_mm}mm`,
    top: `${layer.y_mm}mm`,
    width: `${layer.width_mm}mm`,
    height: `${layer.height_mm}mm`,
    transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
    fontFamily: 'DM Sans, sans-serif',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    overflow: 'hidden',
  };

  if (!parts.boxed) {
    return (
      <div style={frame}>
        <span
          style={{
            fontSize: '13pt',
            fontWeight: 700,
            textAlign: 'center',
            color: parts.amountText ? '#000000' : '#999999',
          }}
        >
          {parts.plainText}
        </span>
      </div>
    );
  }

  return (
    <div style={frame}>
      {parts.struckText && (
        <span
          style={{
            fontSize: '9pt',
            color: '#666666',
            textAlign: 'center',
            textDecoration: 'line-through',
          }}
        >
          {parts.struckText}
        </span>
      )}
      <div
        style={{
          flex: 1,
          backgroundColor: props.fill,
          color: props.textColor,
          borderRadius: `${props.cornerRadius}mm`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '1mm',
          padding: '0.5mm 1mm',
        }}
      >
        {parts.spLabel && (
          <span style={{ fontSize: '8pt', fontWeight: 700 }}>{parts.spLabel}</span>
        )}
        <span style={{ fontSize: '16pt', fontWeight: 800 }}>{parts.amountText}</span>
        {parts.nettLabel && (
          <span style={{ fontSize: '8pt', fontWeight: 700 }}>{parts.nettLabel}</span>
        )}
      </div>
    </div>
  );
}

function renderProductSlotLayer(
  layer: TagLayer,
  resolved: ResolvedLineData | null,
  media: TagSheetMedia,
) {
  const props = layer.props;
  if (props.kind !== 'product_slot') return null;

  let content = '';
  if (resolved) {
    switch (props.fieldKey) {
      case 'code':
        content = resolved.code;
        break;
      case 'name':
        content = resolved.name;
        break;
      case 'dimensions':
        content = resolved.dimensions;
        break;
      case 'spec_lines':
        content = resolved.spec_lines;
        break;
      case 'product_image': {
        // The product's photo, by the same rule the canvas draws it with (D42).
        const url = imageUrlFor(layer, media, resolved);
        return (
          <div
            style={{
              position: 'absolute',
              left: `${layer.x_mm}mm`,
              top: `${layer.y_mm}mm`,
              width: `${layer.width_mm}mm`,
              height: `${layer.height_mm}mm`,
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: url ? 'transparent' : '#f0f0f0',
            }}
          >
            {url ? (
              <img
                src={url}
                alt=""
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              />
            ) : (
              <span
                style={{
                  color: '#999',
                  fontSize: '8pt',
                  fontFamily: 'sans-serif',
                }}
              >
                {resolved.code || 'Image'}
              </span>
            )}
          </div>
        );
      }
    }
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: `${layer.x_mm}mm`,
        top: `${layer.y_mm}mm`,
        width: `${layer.width_mm}mm`,
        height: `${layer.height_mm}mm`,
        transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
        fontFamily: 'DM Sans, sans-serif',
        fontSize: '10pt',
        color: '#000000',
        overflow: 'hidden',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {content}
    </div>
  );
}

function renderBadgeLayer(layer: TagLayer, media: TagSheetMedia) {
  const props = layer.props;
  if (props.kind !== 'badge') return null;

  const url = props.assetId ? media.assets?.[props.assetId] ?? null : null;

  return (
    <div
      style={{
        position: 'absolute',
        left: `${layer.x_mm}mm`,
        top: `${layer.y_mm}mm`,
        width: `${layer.width_mm}mm`,
        height: `${layer.height_mm}mm`,
        transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
        overflow: 'hidden',
      }}
    >
      {url && (
        <img
          src={url}
          alt=""
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      )}
    </div>
  );
}

/**
 * Draws the bars onto an offscreen canvas via `jsbarcode` and returns a data
 * URL, or null if there is nothing to draw or `jsbarcode` threw.
 *
 * Computed with `useMemo`, not `useEffect` + state: `jsbarcode`'s draw is
 * synchronous (a canvas fill, no network, no timer), so there is nothing to
 * wait for - the data URL is ready in the SAME render/paint as the rest of
 * the plate. An effect-based version used to add a second commit after the
 * page's own image-readiness effect had already run and counted
 * `document.images`, so the print worker could call `page.pdf()` before the
 * bars `<img>` even existed in the DOM and the plate printed bar-less.
 */
function barcodeDataUrl(value: string, symbology: 'EAN13' | 'CODE128'): string | null {
  const canvas = document.createElement('canvas');
  try {
    JsBarcode(canvas, value.trim(), {
      format: symbology,
      displayValue: false,
      margin: 0,
      height: 160,
    });
    return canvas.toDataURL('image/png');
  } catch {
    return null;
  }
}

/**
 * The barcode's label plate (D18), on the print page. Empty renders NOTHING -
 * not the editor's dashed placeholder, which exists to tell a designer what
 * is missing and has no business on a physical tag (AC-S7-3). A value
 * `jsbarcode` cannot encode at print time renders the SAME nothing, for the
 * same reason - a bar-less plate on a physical tag is worse than no plate.
 *
 * Band heights, padding and font sizes come from `barcodePlateGeometry` (mm
 * of plate), converted to `pt` for font sizes via `MM_TO_PT` - the SAME
 * numbers the Konva editor reaches by converting to canvas px instead, so the
 * two cannot draw a differently-proportioned plate (AC-S7-4/6).
 */
function BarcodeLayer({
  layer,
  resolved,
}: {
  layer: TagLayer;
  resolved: ResolvedLineData | null;
}) {
  const props = layer.props;
  const isBarcode = props.kind === 'barcode';

  const binding = bindingOf(resolved);
  const value = isBarcode ? resolveBarcodeValue(layer, binding) : null;
  const code = isBarcode ? resolveSlotText({ slot_binding: 'code' }, binding) : null;
  const symbology = barcodeSymbologyFor(value);

  const barsUrl = useMemo(() => {
    if (!value || !symbology) return null;
    return barcodeDataUrl(value, symbology);
  }, [value, symbology]);

  // Nothing on print for an unbound/empty barcode, or one `jsbarcode` could
  // not encode - AC-S7-3. The `kind` check is unreachable in practice (the
  // caller only renders this for a barcode layer) but is what lets TS narrow
  // `props.show_code` below.
  if (props.kind !== 'barcode' || !value || !symbology || !barsUrl) return null;

  const h = layer.height_mm;
  const w = layer.width_mm;
  const geo = barcodePlateGeometry(w, h, props.show_code && !!code);

  return (
    <div
      style={{
        position: 'absolute',
        left: `${layer.x_mm}mm`,
        top: `${layer.y_mm}mm`,
        width: `${w}mm`,
        height: `${h}mm`,
        transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
        backgroundColor: '#ffffff',
        borderRadius: `${geo.cornerRadius_mm}mm`,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {geo.stripHeight_mm > 0 && (
        <div
          style={{
            height: `${geo.stripHeight_mm}mm`,
            backgroundColor: '#000000',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: `${geo.stripFontSize_mm * MM_TO_PT}pt`,
            fontFamily: 'DM Sans, sans-serif',
          }}
        >
          {code}
        </div>
      )}
      <div
        style={{
          flex: 1,
          // A flex item's automatic minimum height defaults to its CONTENT
          // size, not 0 - so without this, the bars `<img>`'s own intrinsic
          // aspect ratio (JsBarcode draws it wide and short) refused to
          // shrink below that size on a small plate, and flexbox took the
          // extra height from the human-readable row next to it instead,
          // squeezing it to nothing. Found live: a 40x22mm plate printed with
          // its human-readable digits entirely gone (AC-S7-4/6).
          minHeight: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <img
          src={barsUrl}
          alt=""
          style={{ width: '88%', height: '100%', objectFit: 'contain' }}
        />
      </div>
      <div
        style={{
          height: `${geo.humanHeight_mm}mm`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'monospace',
          fontSize: `${geo.humanFontSize_mm * MM_TO_PT}pt`,
          color: '#000000',
        }}
      >
        {humanReadableBarcode(value, symbology)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tag renderer
// ---------------------------------------------------------------------------

function TagRenderer({
  tag,
  resolved,
  bleed_mm,
  media,
}: {
  tag: PlacedTag;
  resolved: ResolvedLineData | null;
  bleed_mm: number;
  media: TagSheetMedia;
}) {
  const sortedLayers = [...tag.layers]
    .filter((l) => l.visible !== false)
    .sort((a, b) => a.z_index - b.z_index);

  return (
    <div
      style={{
        position: 'absolute',
        left: `${tag.x_mm}mm`,
        top: `${tag.y_mm}mm`,
        width: `${tag.width_mm}mm`,
        height: `${tag.height_mm}mm`,
        overflow: 'hidden',
        backgroundColor: '#ffffff',
      }}
    >
      {sortedLayers.map((layer) => (
        <div key={layer.id}>
          {layer.type === 'text' && renderTextLayer(layer, resolved)}
          {layer.type === 'shape' && renderShapeLayer(layer)}
          {layer.type === 'image' && renderImageLayer(layer, media, resolved)}
          {layer.type === 'product_slot' &&
            renderProductSlotLayer(layer, resolved, media)}
          {layer.type === 'price_badge' && renderPriceBadgeLayer(layer, resolved)}
          {layer.type === 'badge' && renderBadgeLayer(layer, media)}
          {layer.type === 'barcode' && <BarcodeLayer layer={layer} resolved={resolved} />}
        </div>
      ))}

      {/* Bleed marks at corners */}
      {bleed_mm > 0 && (
        <>
          {/* Top-left */}
          <div
            style={{
              position: 'absolute',
              left: `-${bleed_mm}mm`,
              top: '0',
              width: `${bleed_mm}mm`,
              height: '0.1mm',
              backgroundColor: '#000000',
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: '0',
              top: `-${bleed_mm}mm`,
              width: '0.1mm',
              height: `${bleed_mm}mm`,
              backgroundColor: '#000000',
            }}
          />
          {/* Top-right */}
          <div
            style={{
              position: 'absolute',
              right: `-${bleed_mm}mm`,
              top: '0',
              width: `${bleed_mm}mm`,
              height: '0.1mm',
              backgroundColor: '#000000',
            }}
          />
          <div
            style={{
              position: 'absolute',
              right: '0',
              top: `-${bleed_mm}mm`,
              width: '0.1mm',
              height: `${bleed_mm}mm`,
              backgroundColor: '#000000',
            }}
          />
          {/* Bottom-left */}
          <div
            style={{
              position: 'absolute',
              left: `-${bleed_mm}mm`,
              bottom: '0',
              width: `${bleed_mm}mm`,
              height: '0.1mm',
              backgroundColor: '#000000',
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: '0',
              bottom: `-${bleed_mm}mm`,
              width: '0.1mm',
              height: `${bleed_mm}mm`,
              backgroundColor: '#000000',
            }}
          />
          {/* Bottom-right */}
          <div
            style={{
              position: 'absolute',
              right: `-${bleed_mm}mm`,
              bottom: '0',
              width: `${bleed_mm}mm`,
              height: '0.1mm',
              backgroundColor: '#000000',
            }}
          />
          <div
            style={{
              position: 'absolute',
              right: '0',
              bottom: `-${bleed_mm}mm`,
              width: '0.1mm',
              height: `${bleed_mm}mm`,
              backgroundColor: '#000000',
            }}
          />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sheet renderer
// ---------------------------------------------------------------------------

function SheetRenderer({
  sheet,
  imposition,
  resolvedData,
  isLast,
  media,
}: {
  sheet: TagSheet;
  imposition: ImpositionConfig;
  resolvedData: Record<string, ResolvedLineData>;
  isLast: boolean;
  media: TagSheetMedia;
}) {
  return (
    <div
      className="sheet"
      style={{
        width: `${imposition.page_width_mm}mm`,
        height: `${imposition.page_height_mm}mm`,
        position: 'relative',
        backgroundColor: '#ffffff',
        // Page break between sheets, but not after the last one.
        breakAfter: isLast ? 'auto' : 'page',
        overflow: 'hidden',
      }}
    >
      {sheet.tags.map((tag) => {
        const resolved = resolvedData[tag.request_line_id] ?? null;
        return (
          <TagRenderer
            key={tag.id}
            tag={tag}
            resolved={resolved}
            bleed_mm={imposition.bleed_mm}
            media={media}
          />
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main renderer
// ---------------------------------------------------------------------------

export default function TagSheetRenderer({
  doc,
  resolvedData,
  assets,
  images,
  preview = false,
  previewScale = 0.3,
}: TagSheetRendererProps) {
  const imposition = doc.imposition;
  const media: TagSheetMedia = { assets, images };

  if (preview) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          alignItems: 'center',
        }}
      >
        {doc.sheets.map((sheet, index) => (
          <div
            key={sheet.id}
            style={{
              transform: `scale(${previewScale})`,
              transformOrigin: 'top center',
              width: `${imposition.page_width_mm}mm`,
              height: `${imposition.page_height_mm}mm`,
            }}
          >
            <SheetRenderer
              sheet={sheet}
              imposition={imposition}
              resolvedData={resolvedData}
              isLast={index === doc.sheets.length - 1}
              media={media}
            />
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      {doc.sheets.map((sheet, index) => (
        <SheetRenderer
          key={sheet.id}
          sheet={sheet}
          imposition={imposition}
          resolvedData={resolvedData}
          isLast={index === doc.sheets.length - 1}
          media={media}
        />
      ))}
    </>
  );
}
