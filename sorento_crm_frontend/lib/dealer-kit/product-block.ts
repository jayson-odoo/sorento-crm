/**
 * Turning a product into layers, and reading a layer's bound value back out.
 *
 * The canvas edits layers; the catalogue builder's data layer knows products.
 * This module is the seam between them, and it is deliberately PURE - layers in,
 * layers out, no fetching and no React - so the same functions serve the tag
 * template editor, the tag sheet designer and a vitest run.
 *
 * Two rules it exists to keep:
 *
 * * **A saved document holds bindings, never values** (ADR 0008). Every builder
 *   below writes a `slot_binding` and leaves `text_override` null; the text a
 *   designer sees comes from `layerText`, resolved against live data held only
 *   in editor state.
 * * **Typing over a bound layer unlinks it, it does not corrupt it.** The typed
 *   text goes to `text_override`, the binding stays, and "Relink" is just
 *   clearing the override again.
 */

import type {
  GroupBinding,
  ProductSetMemberTagData,
  ProductSetTagData,
  ProductTagData,
  SlotBinding,
  TagBindingData,
  TagImage,
  TagLayer,
  TagLayerType,
  TextLayerProps,
} from './tag-template-types';
import {
  defaultImageProps,
  defaultPriceBadgeProps,
  defaultTextProps,
  imageSourceOf,
} from './tag-template-types';
import type { PriceBadgeInput } from './price-badge';
import { formatTagPrice } from './price-badge';
import type { MergeFieldMode } from './merge-fields';
import { hasMergeField, renderMergeFields } from './merge-fields';

// ---------------------------------------------------------------------------
// Reading a bound value
// ---------------------------------------------------------------------------

/** `- SK-1234 (Kitchen Sink) 800 x 500 x 220 mm` */
export function formatSetMemberLine(member: ProductSetMemberTagData): string {
  const head = `- ${member.code}${member.name ? ` (${member.name})` : ''}`;
  return member.dimensions ? `${head} ${member.dimensions}` : head;
}

/**
 * The value a slot resolves to, or null when this layer is not bound to one or
 * the data behind it has not arrived.
 *
 * Null rather than an empty string: the caller falls back to the layer's own
 * text, and "no data yet" must not blank a tag that already reads correctly.
 */
export function resolveSlotText(
  layer: Pick<TagLayer, 'slot_binding'>,
  data: TagBindingData | null | undefined,
): string | null {
  if (!layer.slot_binding || !data) return null;

  // A price on a TEXT layer, which is not the same thing as a price badge and
  // does not replace it. The flyer prints `LP: RM 1,550` as an ordinary line
  // above the promotional block on five of its eight tags, and a template that
  // could not resolve that line would print the placeholder it was seeded with
  // - a made-up figure on a real tag, which is the worst failure available
  // here. The BADGE stays the way a promotional price is drawn (D26); this is
  // the plain line beside it.
  if (layer.slot_binding === 'list_price' || layer.slot_binding === 'sell_price') {
    const { listPrice, offerPrice } = priceBadgeInput(data);
    const amount = layer.slot_binding === 'list_price' ? listPrice : offerPrice;
    return amount == null ? null : formatTagPrice(amount);
  }

  if (data.kind === 'line') {
    switch (layer.slot_binding) {
      case 'code':
        return data.line.code;
      case 'name':
        return data.line.name;
      case 'dimensions':
        return data.line.dimensions;
      case 'spec_lines':
        return data.line.spec_lines;
      case 'set_members':
        return data.line.set_members;
      case 'included_accessories':
        return data.line.included_accessories;
      case 'barcode':
        return data.line.barcode;
      default:
        return null;
    }
  }

  if (data.kind === 'set') {
    switch (layer.slot_binding) {
      case 'code':
        return data.set.set_code;
      case 'name':
        return data.set.name;
      case 'set_members':
        return data.set.members.map(formatSetMemberLine).join('\n');
      // A set has no barcode of its own (S7) - falls through to null.
      default:
        return null;
    }
  }

  const product = data.product;
  switch (layer.slot_binding) {
    case 'code':
      return product.code;
    case 'name':
      return product.name;
    case 'dimensions':
      return product.dimensions;
    case 'spec_lines':
      return product.spec_lines.join('\n');
    case 'barcode':
      return product.barcode;
    default:
      return null;
  }
}

/**
 * The value a `barcode` layer draws: a typed override wins, else the bound
 * product/line's own barcode, else null (D23, S9).
 *
 * Mirrors the text layer's `text_override` pattern exactly - the override
 * lives in the SAME `text_override` field every layer already carries, it
 * just holds a barcode string instead of a sentence. One function so the
 * Konva editor (`layerDisplay` below) and the print page's
 * `TagSheetRenderer` cannot resolve an override two different ways; both call
 * this instead of reading `text_override` themselves.
 */
export function resolveBarcodeValue(
  layer: Pick<TagLayer, 'text_override'>,
  data: TagBindingData | null | undefined,
): string | null {
  return layer.text_override ?? resolveSlotText({ slot_binding: 'barcode' }, data);
}

/** The photo a product leads with: the one marked primary, else the first. */
export function primaryImageOf(images: TagImage[]): TagImage | undefined {
  return images.find((image) => image.is_primary) ?? images[0];
}

/**
 * Which of the bound product's photos a product-photo slot draws (D42).
 *
 * A layer that is ABOUT the product photo follows the product, because that is
 * what "product image" means; the designer's explicit pick only wins while it
 * is still one of THIS product's photos. Templates ship unbound, so their hero
 * layer holds `source: null` and would otherwise draw nothing at all - which is
 * the "No image" a preview used to show against a product with three photos.
 *
 * Returns an attachment id rather than a URL, because the two callers hold
 * different maps: the canvas has the bound data's signed URLs, the print page
 * has the payload's. An `asset` source answers null, being the caller's own
 * business, and so does an image layer bound to no slot: a picture nobody chose
 * is decoration, not the product.
 */
export function slotImageAttachmentId(
  layer: Pick<TagLayer, 'slot_binding' | 'props'>,
  images: TagImage[],
): string | null {
  if (layer.props.kind === 'product_slot') {
    return layer.props.fieldKey === 'product_image'
      ? primaryImageOf(images)?.attachment_id ?? null
      : null;
  }
  if (layer.props.kind !== 'image') return null;

  const source = imageSourceOf(layer.props);
  if (source?.type === 'asset') return null;

  const bound = layer.slot_binding === 'product_image';
  if (source) {
    const pinned = images.some((image) => image.attachment_id === source.attachmentId);
    if (pinned || !bound) return source.attachmentId;
    // Pinned to a photo this product does not have: the block was re-bound, and
    // the old product's picture under the new product's name is the one failure
    // on a price tag that a customer acts on.
    return primaryImageOf(images)?.attachment_id ?? null;
  }
  return bound ? primaryImageOf(images)?.attachment_id ?? null : null;
}

/**
 * Whether a layer holds a merge field, in its override or in its own text.
 *
 * Its own text counts: an unbound layer reading `Made of {{spec.material}}` is
 * following the product exactly as a bound one does, and the Layers panel has
 * to say so (D57).
 */
export function isDynamic(
  layer: Pick<TagLayer, 'text_override' | 'props'>,
): boolean {
  if (hasMergeField(layer.text_override)) return true;
  return layer.props.kind === 'text' && hasMergeField(layer.props.text);
}

/**
 * Whether a layer is bound to a slot but showing typed text instead.
 *
 * An override holding a merge field is NOT unlinked (D57): it still draws from
 * the product, so the amber broken-link marker would be a lie and Relink-all
 * would delete a sentence that is doing its job.
 */
export function isUnlinked(
  layer: Pick<TagLayer, 'slot_binding' | 'text_override' | 'props'>,
): boolean {
  if (!layer.slot_binding || layer.text_override == null) return false;
  return !hasMergeField(layer.text_override);
}

/**
 * What a text layer actually shows: the override if somebody typed one, then
 * the resolved slot value, then the layer's own text - and in every one of
 * those, any `{{path}}` replaced by what the data says (D55).
 *
 * The resolved slot value never carries a token (it IS data), so running it
 * through the resolver costs nothing and keeps the one call site honest.
 */
export function layerText(
  layer: TagLayer,
  data: TagBindingData | null | undefined,
  mode: MergeFieldMode = 'editor',
): string {
  const raw =
    layer.text_override ??
    resolveSlotText(layer, data) ??
    (layer.props.kind === 'text' ? layer.props.text : '');
  return renderMergeFields(raw, data, mode);
}

/** The two figures a price badge draws, taken off whichever thing is bound. */
export function priceBadgeInput(
  data: TagBindingData | null | undefined,
): PriceBadgeInput {
  if (!data) return { listPrice: null, offerPrice: null };
  if (data.kind === 'line') {
    // A line whose promo price is switched off prints its list price, whatever
    // the promotion says: `show_promo_price` is the salesperson's per-line
    // choice (D8).
    return {
      listPrice: data.line.list_price,
      offerPrice: data.line.show_promo_price ? data.line.sell_price : null,
    };
  }
  const source = data.kind === 'product' ? data.product : data.set;
  return { listPrice: source.list_price, offerPrice: source.offer_price };
}

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------

export interface BuildOptions {
  /** Id factory, injected so a builder stays pure and a test can pin ids. */
  newId: () => string;
  /** Where the block's top-left corner goes, in mm. */
  x_mm: number;
  y_mm: number;
  /** First free z-index. Each layer produced takes the next one. */
  z_index: number;
}

interface LayerSpec {
  type: TagLayerType;
  x: number;
  y: number;
  w: number;
  h: number;
  slot?: TagLayer['slot_binding'];
  props: TagLayer['props'];
}

function materialise(specs: LayerSpec[], opts: BuildOptions): TagLayer[] {
  return specs.map((spec, index) => ({
    id: opts.newId(),
    type: spec.type,
    x_mm: opts.x_mm + spec.x,
    y_mm: opts.y_mm + spec.y,
    width_mm: spec.w,
    height_mm: spec.h,
    rotation_deg: 0,
    z_index: opts.z_index + index,
    locked: false,
    visible: true,
    slot_binding: spec.slot ?? null,
    text_override: null,
    props: spec.props,
  }));
}

function text(
  content: string,
  overrides: Partial<TextLayerProps> = {},
): TextLayerProps {
  return { ...defaultTextProps(), text: content, ...overrides };
}

/** The bounding box of a set of layers, in mm. */
export function boundsOf(layers: TagLayer[]): {
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
} {
  const minX = Math.min(...layers.map((l) => l.x_mm));
  const minY = Math.min(...layers.map((l) => l.y_mm));
  const maxX = Math.max(...layers.map((l) => l.x_mm + l.width_mm));
  const maxY = Math.max(...layers.map((l) => l.y_mm + l.height_mm));
  return { x_mm: minX, y_mm: minY, width_mm: maxX - minX, height_mm: maxY - minY };
}

/**
 * Wrap layers in a group bound to a product or a set.
 *
 * The group carries the binding so re-binding the block is one action: every
 * still-linked child re-resolves against the new product, and a child somebody
 * typed over keeps their words.
 */
export function groupLayers(
  children: TagLayer[],
  binding: GroupBinding,
  opts: Pick<BuildOptions, 'newId'> & { z_index: number },
): TagLayer {
  const bounds = boundsOf(children);
  return {
    id: opts.newId(),
    type: 'group',
    ...bounds,
    rotation_deg: 0,
    z_index: opts.z_index,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'group', children: children.map((c) => c.id), binding },
  };
}

/** Default footprint of one product block, in mm. */
export const PRODUCT_BLOCK_SIZE = { width_mm: 85, height_mm: 58 };

/**
 * A product block: photo left, code / name / dimensions / spec lines right, the
 * price badge under them. The ala carte tag on page 1 of the flyer, in layers.
 */
export function buildProductBlock(
  product: ProductTagData,
  opts: BuildOptions,
): TagLayer[] {
  const primary = primaryImageOf(product.images);
  const promo = product.offer_price != null;

  const children = materialise(
    [
      {
        type: 'image',
        x: 0,
        y: 0,
        w: 38,
        h: 38,
        slot: 'product_image',
        props: {
          ...defaultImageProps(),
          source: primary
            ? { type: 'product_attachment', attachmentId: primary.attachment_id }
            : null,
        },
      },
      {
        type: 'text',
        x: 40,
        y: 0,
        w: 45,
        h: 6,
        slot: 'code',
        props: text(product.code, { fontSize: 11, fontWeight: 700 }),
      },
      {
        type: 'text',
        x: 40,
        y: 6.5,
        w: 45,
        h: 8,
        slot: 'name',
        props: text(product.name, { fontSize: 9, fontWeight: 600 }),
      },
      {
        type: 'text',
        x: 40,
        y: 15,
        w: 45,
        h: 5,
        slot: 'dimensions',
        props: text(product.dimensions, { fontSize: 8, color: '#444444' }),
      },
      {
        type: 'text',
        x: 40,
        y: 21,
        w: 45,
        h: 19,
        slot: 'spec_lines',
        props: text(product.spec_lines.join('\n'), {
          fontSize: 7,
          lineHeight: 1.3,
          color: '#333333',
        }),
      },
      {
        type: 'price_badge',
        x: 40,
        y: 41,
        w: 45,
        h: 17,
        slot: promo ? 'sell_price' : 'list_price',
        props: defaultPriceBadgeProps(promo ? 'promo' : 'list_only'),
      },
    ],
    opts,
  );

  const group = groupLayers(children, { product_id: product.id }, {
    newId: opts.newId,
    z_index: opts.z_index + children.length,
  });
  return [...children, group];
}

/** Default footprint of one set block, in mm. */
export const SET_BLOCK_SIZE = { width_mm: 85, height_mm: 62 };

/**
 * A set block: the set's name and code, one line per member, and a price badge.
 * The bathroom furniture set tag, which lists what is in the box.
 */
export function buildSetBlock(
  set: ProductSetTagData,
  opts: BuildOptions,
): TagLayer[] {
  const promo = set.offer_price != null;

  const children = materialise(
    [
      {
        type: 'text',
        x: 0,
        y: 0,
        w: 85,
        h: 6,
        slot: 'code',
        props: text(set.set_code, { fontSize: 11, fontWeight: 700 }),
      },
      {
        type: 'text',
        x: 0,
        y: 6.5,
        w: 85,
        h: 8,
        slot: 'name',
        props: text(set.name, { fontSize: 9, fontWeight: 600 }),
      },
      {
        type: 'text',
        x: 0,
        y: 15,
        w: 85,
        h: 28,
        slot: 'set_members',
        props: text(set.members.map(formatSetMemberLine).join('\n'), {
          fontSize: 8,
          lineHeight: 1.35,
        }),
      },
      {
        type: 'price_badge',
        x: 40,
        y: 45,
        w: 45,
        h: 17,
        slot: promo ? 'sell_price' : 'list_price',
        props: defaultPriceBadgeProps(promo ? 'promo' : 'list_only'),
      },
    ],
    opts,
  );

  const group = groupLayers(children, { product_set_id: set.id }, {
    newId: opts.newId,
    z_index: opts.z_index + children.length,
  });
  return [...children, group];
}

/** The already-formatted text a set-line starter draws - no member array. */
export interface SetStarterData {
  code: string;
  name: string;
  /** Pre-joined, one line per member - what a request line resolves to,
   *  unlike `ProductSetTagData.members` which `buildSetBlock` still formats
   *  itself for the template editor's own "add a set" picker. */
  set_members: string;
  list_price: number | null;
  offer_price: number | null;
}

/**
 * The set-line starter (D6/D13): same layout as `buildSetBlock` - code, name,
 * one line per member, price badge - but reads a request line's ALREADY
 * resolved `set_members` string instead of a `ProductSetTagData.members`
 * array, since that is the shape `starterTemplateFor` has on hand and forcing
 * a fake member list just to re-derive the same string back out would be
 * make-work.
 *
 * The group's binding is not this function's job: the caller re-binds every
 * group to the real line afterward (`bindTemplateLayers`), so what is passed
 * to `groupLayers` here is a placeholder.
 */
export function buildSetStarterBlock(
  set: SetStarterData,
  opts: BuildOptions,
): TagLayer[] {
  const promo = set.offer_price != null;

  const children = materialise(
    [
      {
        type: 'text',
        x: 0,
        y: 0,
        w: 85,
        h: 6,
        slot: 'code',
        props: text(set.code, { fontSize: 11, fontWeight: 700 }),
      },
      {
        type: 'text',
        x: 0,
        y: 6.5,
        w: 85,
        h: 8,
        slot: 'name',
        props: text(set.name, { fontSize: 9, fontWeight: 600 }),
      },
      {
        type: 'text',
        x: 0,
        y: 15,
        w: 85,
        h: 28,
        slot: 'set_members',
        props: text(set.set_members, { fontSize: 8, lineHeight: 1.35 }),
      },
      {
        type: 'price_badge',
        x: 40,
        y: 45,
        w: 45,
        h: 17,
        slot: promo ? 'sell_price' : 'list_price',
        props: defaultPriceBadgeProps(promo ? 'promo' : 'list_only'),
      },
    ],
    opts,
  );

  const group = groupLayers(children, {}, {
    newId: opts.newId,
    z_index: opts.z_index + children.length,
  });
  return [...children, group];
}

// ---------------------------------------------------------------------------
// Presets (D28)
// ---------------------------------------------------------------------------

/** One alternative block: small photo, code, name, price badge. */
const ALTERNATIVE_WIDTH_MM = 34;
const ALTERNATIVE_HEIGHT_MM = 40;
const CONNECTOR_WIDTH_MM = 8;

/**
 * The OR row from the flyer: a leading `+`, then each product, `OR` between.
 *
 * Ordinary layers after the drop (D28) - nothing watches this row, so a
 * designer can move, restyle or delete any piece of it.
 */
export function buildAlternativesRow(
  products: ProductTagData[],
  opts: BuildOptions,
): TagLayer[] {
  const layers: TagLayer[] = [];
  let cursorX = opts.x_mm;
  let z = opts.z_index;

  const connector = (label: string): void => {
    layers.push(
      ...materialise(
        [
          {
            type: 'text',
            x: 0,
            y: ALTERNATIVE_HEIGHT_MM / 2 - 4,
            w: CONNECTOR_WIDTH_MM,
            h: 8,
            props: text(label, { fontSize: 10, fontWeight: 700, align: 'center' }),
          },
        ],
        { newId: opts.newId, x_mm: cursorX, y_mm: opts.y_mm, z_index: z },
      ),
    );
    cursorX += CONNECTOR_WIDTH_MM;
    z += 1;
  };

  connector('+');

  products.forEach((product, index) => {
    if (index > 0) connector('OR');

    const primary = primaryImageOf(product.images);
    const promo = product.offer_price != null;
    const block = materialise(
      [
        {
          type: 'image',
          x: 0,
          y: 0,
          w: ALTERNATIVE_WIDTH_MM,
          h: 20,
          props: {
            ...defaultImageProps(),
            source: primary
              ? { type: 'product_attachment', attachmentId: primary.attachment_id }
              : null,
          },
        },
        {
          type: 'text',
          x: 0,
          y: 21,
          w: ALTERNATIVE_WIDTH_MM,
          h: 5,
          props: text(product.code, { fontSize: 8, fontWeight: 700, align: 'center' }),
        },
        {
          type: 'text',
          x: 0,
          y: 26,
          w: ALTERNATIVE_WIDTH_MM,
          h: 5,
          props: text(product.name, { fontSize: 7, align: 'center' }),
        },
        {
          type: 'price_badge',
          x: 0,
          y: 31,
          w: ALTERNATIVE_WIDTH_MM,
          h: 9,
          props: defaultPriceBadgeProps(promo ? 'promo' : 'list_only'),
        },
      ],
      { newId: opts.newId, x_mm: cursorX, y_mm: opts.y_mm, z_index: z },
    );
    layers.push(...block);
    z += block.length;
    cursorX += ALTERNATIVE_WIDTH_MM;
  });

  return layers;
}

export interface AccessoryItem {
  /** Shown under the picture. */
  caption: string;
  /** The picture, when there is one. */
  source: { type: 'asset'; assetId: string } | { type: 'product_attachment'; attachmentId: string } | null;
}

const ACCESSORY_WIDTH_MM = 24;
const ACCESSORY_TITLE_HEIGHT_MM = 6;

/** The titled strip of small pictures with captions ("Accessories Included"). */
export function buildAccessoriesStrip(
  items: AccessoryItem[],
  opts: BuildOptions & { title?: string },
): TagLayer[] {
  const layers = materialise(
    [
      {
        type: 'text',
        x: 0,
        y: 0,
        w: Math.max(ACCESSORY_WIDTH_MM, items.length * ACCESSORY_WIDTH_MM),
        h: ACCESSORY_TITLE_HEIGHT_MM,
        props: text(opts.title ?? 'Accessories Included', {
          fontSize: 9,
          fontWeight: 700,
        }),
      },
    ],
    opts,
  );

  let z = opts.z_index + 1;
  items.forEach((item, index) => {
    const x = index * ACCESSORY_WIDTH_MM;
    layers.push(
      ...materialise(
        [
          {
            type: 'image',
            x,
            y: ACCESSORY_TITLE_HEIGHT_MM + 1,
            w: ACCESSORY_WIDTH_MM - 2,
            h: 18,
            props: { ...defaultImageProps(), source: item.source },
          },
          {
            type: 'text',
            x,
            y: ACCESSORY_TITLE_HEIGHT_MM + 20,
            w: ACCESSORY_WIDTH_MM - 2,
            h: 6,
            props: text(item.caption, { fontSize: 7, align: 'center' }),
          },
        ],
        { newId: opts.newId, x_mm: opts.x_mm, y_mm: opts.y_mm, z_index: z },
      ),
    );
    z += 2;
  });

  return layers;
}

// ---------------------------------------------------------------------------
// What a layer shows right now
// ---------------------------------------------------------------------------

/**
 * Resolved values for one layer, computed by the surface that owns the data and
 * handed DOWN to whatever draws it.
 *
 * The renderers know about layers, not products. That is what lets the same
 * Konva component draw a template, a placed tag and a preview without three
 * copies of the binding rules.
 */
export interface TagLayerDisplay {
  text?: string;
  imageUrl?: string | null;
  price?: PriceBadgeInput;
  /**
   * The bound product/line's own CODE, for the barcode layer's optional
   * product-code strip (D18). Distinct from `text`, which for a barcode
   * layer carries the barcode VALUE itself, not the product code.
   */
  code?: string | null;
}

/**
 * What a layer is CALLED on screen: the Layers panel row, and anywhere else a
 * person has to pick one layer out of several.
 *
 * Deliberately not the id and not the type alone. A designer recognises "code"
 * and "Price (promo)"; `layer-1756...-7` tells them nothing, and `Text` five
 * times over tells them no more.
 */
export function layerDisplayName(layer: TagLayer): string {
  if (layer.slot_binding) {
    return layer.slot_binding.replace(/_/g, ' ');
  }
  switch (layer.props.kind) {
    case 'text':
      return layer.props.text.slice(0, 24) || 'Text';
    case 'shape':
      return layer.props.shape.replace(/_/g, ' ');
    case 'image':
      return 'Image';
    case 'product_slot':
      return `Slot: ${layer.props.fieldKey}`;
    case 'price_badge':
      return layer.props.variant === 'promo' ? 'Price (promo)' : 'Price (list)';
    case 'badge':
      return 'Badge';
    case 'barcode':
      return 'Barcode';
    case 'group': {
      const binding = layer.props.binding;
      const what = binding?.product_set_id
        ? 'Set'
        : binding?.product_id
          ? 'Product'
          : 'Group';
      return `${what} (${layer.props.children.length})`;
    }
  }
}

/**
 * Everything a layer needs in order to draw itself against live data.
 *
 * `assetUrls` are library artwork, signed; the product's own photos come off
 * the bound data, because they carry the access gate that decides who may see
 * them and a second lookup would be a second answer to that question.
 */
export function layerDisplay(
  layer: TagLayer,
  data: TagBindingData | null | undefined,
  assetUrls: Record<string, string>,
): TagLayerDisplay | undefined {
  switch (layer.props.kind) {
    case 'text':
      return { text: layerText(layer, data) };

    case 'price_badge':
      return { price: priceBadgeInput(data) };

    case 'badge':
      return { imageUrl: assetUrls[layer.props.assetId] ?? null };

    case 'barcode':
      return {
        text: resolveBarcodeValue(layer, data) ?? undefined,
        code: resolveSlotText({ slot_binding: 'code' }, data),
      };

    case 'image': {
      const source = imageSourceOf(layer.props);
      if (source?.type === 'asset') {
        return { imageUrl: assetUrls[source.assetId] ?? null };
      }
      return { imageUrl: boundImageUrl(layer, data) };
    }

    case 'product_slot': {
      if (layer.props.fieldKey === 'product_image') {
        return { imageUrl: boundImageUrl(layer, data) };
      }
      // The other field keys are the same slots a text layer binds to, so they
      // resolve through the same function; nothing resolved means the layer
      // keeps its dashed placeholder rather than drawing an empty box.
      const text = resolveSlotText(
        { slot_binding: layer.props.fieldKey as SlotBinding },
        data,
      );
      return text == null ? undefined : { text };
    }

    default:
      return undefined;
  }
}

/** The photos of whatever is bound. A set has none of its own. */
function imagesOf(data: TagBindingData | null | undefined): TagImage[] {
  if (data?.kind === 'product') return data.product.images;
  if (data?.kind === 'line') return data.line.images;
  return [];
}

/** The URL a product-photo slot draws, resolved by D42 against the bound data. */
function boundImageUrl(
  layer: Pick<TagLayer, 'slot_binding' | 'props'>,
  data: TagBindingData | null | undefined,
): string | null {
  const images = imagesOf(data);
  const attachmentId = slotImageAttachmentId(layer, images);
  if (!attachmentId) return null;
  return images.find((image) => image.attachment_id === attachmentId)?.url ?? null;
}

/**
 * Point a product block's image layers at the new product's primary photo.
 *
 * Re-binding a block keeps its layout and its typed-over text, but an image
 * layer still holding the OLD product's attachment id would print the wrong
 * product's photo under the right product's name - the one failure on a price
 * tag that a customer acts on.
 */
export function rebindImageLayers(
  layers: TagLayer[],
  childIds: Set<string>,
  data: TagBindingData,
): TagLayer[] {
  const primary =
    data.kind === 'product' ? primaryImageOf(data.product.images) : undefined;

  return layers.map((layer) => {
    if (!childIds.has(layer.id) || layer.props.kind !== 'image') return layer;
    return {
      ...layer,
      props: {
        ...layer.props,
        source: primary
          ? { type: 'product_attachment' as const, attachmentId: primary.attachment_id }
          : null,
      },
    };
  });
}

/**
 * Point a template's groups at the product a request line names.
 *
 * A tag TEMPLATE has slot bindings but no product: it is the layout for a
 * family, not for one item. Dropping a line fills it in, and the binding is
 * written onto the group so the tag can later be re-bound or relinked the same
 * way one built in the editor can.
 */
export function bindTemplateLayers(
  layers: TagLayer[],
  binding: GroupBinding,
): TagLayer[] {
  return layers.map((layer) =>
    layer.props.kind === 'group'
      ? { ...layer, props: { ...layer.props, binding } }
      : layer,
  );
}
