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

import type {
  ImpositionConfig,
  PlacedTag,
  TagLayer,
  TagSheetDoc,
  TagSheet,
} from '@/lib/dealer-kit/tag-template-types';

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
}

interface TagSheetRendererProps {
  doc: TagSheetDoc;
  resolvedData: Record<string, ResolvedLineData>;
  /** When true, render at a scaled-down size for preview (not print). */
  preview?: boolean;
  /** Scale factor for preview mode (default 0.3). */
  previewScale?: number;
}

// ---------------------------------------------------------------------------
// Price formatting
// ---------------------------------------------------------------------------

function formatPrice(amount: number): string {
  return `RM ${amount.toLocaleString('en-MY', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

// ---------------------------------------------------------------------------
// Layer renderers (pure DOM)
// ---------------------------------------------------------------------------

function renderTextLayer(layer: TagLayer, resolved: ResolvedLineData | null) {
  const props = layer.props;
  if (props.kind !== 'text') return null;

  // Resolve slot binding.
  let text = layer.text_override ?? props.text;
  if (!layer.text_override && layer.slot_binding && resolved) {
    switch (layer.slot_binding) {
      case 'code':
        text = resolved.code;
        break;
      case 'name':
        text = resolved.name;
        break;
      case 'dimensions':
        text = resolved.dimensions;
        break;
      case 'spec_lines':
        text = resolved.spec_lines;
        break;
      case 'included_accessories':
        text = resolved.included_accessories;
        break;
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

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function renderImageLayer(layer: TagLayer, _resolved: ResolvedLineData | null) {
  const props = layer.props;
  if (props.kind !== 'image') return null;

  // For print, we would need the actual asset URL from the payload.
  // For now, render a placeholder if no src is available.
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
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#f5f5f5',
      }}
    >
      {/* Asset images will be resolved and injected by the print payload */}
    </div>
  );
}

function renderProductSlotLayer(
  layer: TagLayer,
  resolved: ResolvedLineData | null,
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
      case 'product_image':
        // Would render an image; placeholder for now.
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
              backgroundColor: '#f0f0f0',
            }}
          >
            <span
              style={{
                color: '#999',
                fontSize: '8pt',
                fontFamily: 'sans-serif',
              }}
            >
              {resolved.code || 'Image'}
            </span>
          </div>
        );
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

function renderPriceFieldLayer(
  layer: TagLayer,
  resolved: ResolvedLineData | null,
) {
  const props = layer.props;
  if (props.kind !== 'price_field') return null;

  const showPromo = resolved?.show_promo_price && resolved.sell_price != null;
  const listPrice = resolved?.list_price;
  const sellPrice = resolved?.sell_price;

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
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      {props.priceType === 'list' && listPrice != null && (
        <span
          style={{
            fontSize: '12pt',
            fontWeight: 700,
            color: '#000000',
          }}
        >
          {formatPrice(listPrice)}
        </span>
      )}
      {props.priceType === 'sell' && sellPrice != null && showPromo && (
        <span
          style={{
            fontSize: '14pt',
            fontWeight: 700,
            color: '#d32f2f',
          }}
        >
          {formatPrice(sellPrice)} NETT
        </span>
      )}
      {props.priceType === 'both' && (
        <>
          {showPromo && listPrice != null ? (
            <>
              <span
                style={{
                  fontSize: '10pt',
                  color: '#666666',
                  textDecoration: 'line-through',
                }}
              >
                {formatPrice(listPrice)}
              </span>
              <span
                style={{
                  fontSize: '14pt',
                  fontWeight: 700,
                  color: '#d32f2f',
                }}
              >
                {sellPrice != null ? `${formatPrice(sellPrice)} NETT` : ''}
              </span>
            </>
          ) : listPrice != null ? (
            <span
              style={{
                fontSize: '12pt',
                fontWeight: 700,
                color: '#000000',
              }}
            >
              {formatPrice(listPrice)}
            </span>
          ) : (
            <span
              style={{
                fontSize: '10pt',
                color: '#999999',
              }}
            >
              Price TBC
            </span>
          )}
        </>
      )}
    </div>
  );
}

function renderBadgeLayer(layer: TagLayer) {
  const props = layer.props;
  if (props.kind !== 'badge') return null;

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
      {/* Badge asset would be resolved from the asset map */}
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
}: {
  tag: PlacedTag;
  resolved: ResolvedLineData | null;
  bleed_mm: number;
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
          {layer.type === 'image' && renderImageLayer(layer, resolved)}
          {layer.type === 'product_slot' &&
            renderProductSlotLayer(layer, resolved)}
          {layer.type === 'price_field' &&
            renderPriceFieldLayer(layer, resolved)}
          {layer.type === 'badge' && renderBadgeLayer(layer)}
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
}: {
  sheet: TagSheet;
  imposition: ImpositionConfig;
  resolvedData: Record<string, ResolvedLineData>;
  isLast: boolean;
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
  preview = false,
  previewScale = 0.3,
}: TagSheetRendererProps) {
  const imposition = doc.imposition;

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
        />
      ))}
    </>
  );
}
