/**
 * Tag template document model types.
 *
 * Matches the JSONB schema stored in `dealer_kit.tag_templates.doc` and used
 * by both the tag template editor (S3) and the tag sheet designer (S4).
 * Positions and sizes are always in millimetres; the canvas converts to
 * pixels via a zoom-dependent scale factor.
 */

// ---------------------------------------------------------------------------
// Layer types
// ---------------------------------------------------------------------------

export type TagLayerType =
  | 'image'
  | 'text'
  | 'shape'
  | 'product_slot'
  | 'price_field'
  | 'badge'
  | 'group';

/** Named slots that bind a layer to a product data field at render time. */
export type SlotBinding =
  | 'product_image'
  | 'code'
  | 'name'
  | 'dimensions'
  | 'spec_lines'
  | 'included_accessories'
  | 'list_price'
  | 'sell_price'
  | 'badges'
  | 'alternatives'
  | 'accessories'
  | 'set_members'
  | null;

export type ShapeType = 'rect' | 'rounded_rect' | 'ellipse' | 'line';

export type PriceDisplayType = 'list' | 'sell' | 'both';

export type ImageFit = 'cover' | 'contain';

// ---------------------------------------------------------------------------
// Layer props (discriminated union on `kind`)
// ---------------------------------------------------------------------------

export interface ImageLayerProps {
  kind: 'image';
  assetId: string | null;
  fit: ImageFit;
  cropRect?: { x: number; y: number; width: number; height: number };
}

export interface TextLayerProps {
  kind: 'text';
  text: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  color: string;
  align: 'left' | 'center' | 'right';
  lineHeight: number;
  letterSpacing: number;
}

export interface ShapeLayerProps {
  kind: 'shape';
  shape: ShapeType;
  fill: string;
  stroke: string;
  strokeWidth: number;
  cornerRadius: number;
}

export interface ProductSlotLayerProps {
  kind: 'product_slot';
  fieldKey: string;
}

export interface PriceFieldLayerProps {
  kind: 'price_field';
  priceType: PriceDisplayType;
  format: string;
}

export interface BadgeLayerProps {
  kind: 'badge';
  assetId: string;
}

export interface GroupLayerProps {
  kind: 'group';
  children: string[];
}

export type TagLayerProps =
  | ImageLayerProps
  | TextLayerProps
  | ShapeLayerProps
  | ProductSlotLayerProps
  | PriceFieldLayerProps
  | BadgeLayerProps
  | GroupLayerProps;

// ---------------------------------------------------------------------------
// Layer
// ---------------------------------------------------------------------------

export interface TagLayer {
  id: string;
  type: TagLayerType;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  rotation_deg: number;
  z_index: number;
  locked: boolean;
  visible: boolean;
  slot_binding: SlotBinding;
  text_override: string | null;
  props: TagLayerProps;
}

// ---------------------------------------------------------------------------
// Template families
// ---------------------------------------------------------------------------

export type TagTemplateFamily =
  | 'sink_combo'
  | 'ala_carte'
  | 'wc'
  | 'shower'
  | 'mirror'
  | 'mirror_cabinet'
  | 'furniture_set';

export const TAG_TEMPLATE_FAMILIES: { value: TagTemplateFamily; label: string }[] = [
  { value: 'sink_combo', label: 'Sink Combo' },
  { value: 'ala_carte', label: 'Ala Carte' },
  { value: 'wc', label: 'WC' },
  { value: 'shower', label: 'Shower' },
  { value: 'mirror', label: 'Mirror' },
  { value: 'mirror_cabinet', label: 'Mirror Cabinet' },
  { value: 'furniture_set', label: 'Furniture Set' },
];

export function familyLabel(family: string): string {
  return TAG_TEMPLATE_FAMILIES.find((f) => f.value === family)?.label ?? family;
}

// ---------------------------------------------------------------------------
// Template document (stored in tag_templates.doc JSONB)
// ---------------------------------------------------------------------------

export interface TagTemplateDoc {
  layers: TagLayer[];
  width_mm: number;
  height_mm: number;
}

// ---------------------------------------------------------------------------
// Template entity
// ---------------------------------------------------------------------------

export interface TagTemplate {
  id: string;
  name: string;
  family: TagTemplateFamily;
  doc: TagTemplateDoc;
  print_size: { width_mm: number; height_mm: number };
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Imposition (used in S4)
// ---------------------------------------------------------------------------

export type ImpositionPreset = 'a4_3up' | 'a4_2x2' | 'custom';

export interface ImpositionConfig {
  preset: ImpositionPreset;
  page_width_mm: number;
  page_height_mm: number;
  bleed_mm: number;
  gap_mm: number;
}

export const IMPOSITION_PRESETS: Record<ImpositionPreset, Omit<ImpositionConfig, 'preset'>> = {
  a4_3up: { page_width_mm: 210, page_height_mm: 297, bleed_mm: 3, gap_mm: 2 },
  a4_2x2: { page_width_mm: 210, page_height_mm: 297, bleed_mm: 3, gap_mm: 2 },
  custom: { page_width_mm: 210, page_height_mm: 297, bleed_mm: 3, gap_mm: 2 },
};

// ---------------------------------------------------------------------------
// Tag sheet document (stored in page_version.doc when page.kind = 'tag_sheet')
// ---------------------------------------------------------------------------

export interface TagSheetDoc {
  kind: 'tag_sheet';
  imposition: ImpositionConfig;
  sheets: TagSheet[];
}

export interface TagSheet {
  id: string;
  tags: PlacedTag[];
}

export interface PlacedTag {
  id: string;
  template_id: string;
  request_line_id: string;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  layers: TagLayer[];
}

// ---------------------------------------------------------------------------
// Resolved product data for rendering (never stored in doc - ADR 0008)
// ---------------------------------------------------------------------------

export interface ResolvedTagData {
  product_image_url: string | null;
  code: string;
  name: string;
  dimensions: string;
  spec_lines: string;
  list_price: string | null;
  sell_price: string | null;
  show_promo_price: boolean;
  included_accessories: string;
  alternatives: Array<{ code: string; name: string; list_price: string | null }>;
  set_members: Array<{ code: string; name: string; quantity: number }>;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

export const DEFAULT_TAG_SIZE = { width_mm: 95, height_mm: 130 };

export function defaultTextProps(): TextLayerProps {
  return {
    kind: 'text',
    text: 'Text',
    fontFamily: 'DM Sans',
    fontSize: 12,
    fontWeight: 400,
    color: '#000000',
    align: 'left',
    lineHeight: 1.2,
    letterSpacing: 0,
  };
}

export function defaultShapeProps(): ShapeLayerProps {
  return {
    kind: 'shape',
    shape: 'rect',
    fill: '#e0e0e0',
    stroke: '#999999',
    strokeWidth: 0.5,
    cornerRadius: 0,
  };
}

export function defaultImageProps(): ImageLayerProps {
  return {
    kind: 'image',
    assetId: null,
    fit: 'contain',
  };
}

export function defaultProductSlotProps(): ProductSlotLayerProps {
  return {
    kind: 'product_slot',
    fieldKey: 'product_image',
  };
}

export function defaultPriceFieldProps(): PriceFieldLayerProps {
  return {
    kind: 'price_field',
    priceType: 'both',
    format: 'RM #,##0',
  };
}

export function defaultBadgeProps(): BadgeLayerProps {
  return {
    kind: 'badge',
    assetId: '',
  };
}
