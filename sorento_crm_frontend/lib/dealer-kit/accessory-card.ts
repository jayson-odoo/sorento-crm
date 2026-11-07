/**
 * PRICETAG-ACCESSORY-DESIGNER S2: the ONE rule that lays out an "Accessories" box that carries a
 * designed `card` (editor canvas, request preview and print page all call it, card rule A10). A box
 * with no `card` keeps the legacy path in `accessory-box.ts`, untouched.
 *
 * Plan: documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md "S2 Frontend lib
 * contract". Card rules V6-V9: one card layout per box, applied to every accessory; a slot whose
 * field is empty does not print and the slot under it moves up; the box shrinks together to 70%,
 * then whole cards only.
 * Everything is in millimetres inside the layer's own box.
 */
import {
  ACCESSORY_BOX_PAD_MM,
  accessoryCardInner,
  accessoryChrome,
  accessoryHeaderHeight,
  accessoryLineStyle,
  cardSize,
  type AccessoryBoxLayout,
  type AccessoryRect,
  type LayoutProps,
} from './accessory-box';
import { formatTagPrice } from './price-badge';
import { isRich, parseRichText, richPlainText } from './rich-text';
import { textLayerLines } from './text-layout';
import type {
  AccessoriesLayerProps,
  CardElement,
  CardField,
  CardLayout,
  FooterLayout,
  TagAccessory,
  TextLayerProps,
} from './tag-template-types';

const EPS = 1e-9;
/** The smallest the cards shrink to before whole cards are dropped (owner ruling Q2). */
export const CARD_SHRINK_MIN = 0.7;

export type CardBoxProps = LayoutProps & Pick<AccessoriesLayerProps, 'card' | 'footer' | 'shrinkMin'>;

export interface CardBoxLayout extends AccessoryBoxLayout {
  /** The factor every card is drawn at (1 = its design size). */
  scale: number;
  /** The footer area, null when hidden. Not scaled. */
  footer: AccessoryRect | null;
}

// ---------------------------------------------------------------------------
// Box layout
// ---------------------------------------------------------------------------

/**
 * Where everything in the box goes for `count` accessories drawn with `props.card`.
 *
 * Vertical: cards stack at `card.width_mm * scale`, left aligned at the pad; horizontal: they run
 * left to right. `scale` is the largest factor (at most 1) at which every card fits, but never
 * below `shrinkMin` (default 70%); below that only the whole cards that fit are kept. The footer
 * sits under the cards at its own height. The box closes up like the legacy one; nothing to show
 * draws nothing.
 */
export function cardBoxLayout(
  count: number,
  props: CardBoxProps,
  boxWidth_mm: number,
  boxHeight_mm: number,
): CardBoxLayout {
  const total = Math.max(0, Math.floor(count));
  const empty = (dropped: number): CardBoxLayout => ({
    cards: [],
    shown: 0,
    dropped,
    boxWidth_mm: 0,
    boxHeight_mm: 0,
    frame: null,
    header: null,
    badge: null,
    scale: 1,
    footer: null,
  });
  if (total === 0) return empty(0);
  const card = props.card;
  if (!card || !(card.width_mm > 0) || !(card.height_mm > 0)) return empty(total);

  const pad = ACCESSORY_BOX_PAD_MM;
  const gap = Math.max(0, props.gap_mm);
  const headerH = accessoryHeaderHeight(props);
  const onBorder = Boolean(props.headerOnBorder) && headerH > 0;
  const top = onBorder ? headerH + pad * 0.5 : pad + headerH;
  const footerH = props.footer?.show && props.footer.height_mm > 0 ? props.footer.height_mm : 0;
  const min = Math.min(1, Math.max(0.1, props.shrinkMin ?? CARD_SHRINK_MIN));

  const vertical = props.direction !== 'horizontal';
  const innerW = boxWidth_mm - 2 * pad;
  const availMain = vertical ? boxHeight_mm - top - pad - footerH : innerW;
  const availCross = vertical ? innerW : boxHeight_mm - top - pad - footerH;
  const cardMain = vertical ? card.height_mm : card.width_mm;
  const cardCross = vertical ? card.width_mm : card.height_mm;

  const fit = Math.min(1, (availMain - (total - 1) * gap) / (total * cardMain), availCross / cardCross);
  const scale = fit >= min ? fit : min;

  const mainAt = cardMain * scale;
  if (cardCross * scale > availCross + EPS || !(mainAt > 0)) return empty(total);
  const shown = Math.min(total, Math.max(0, Math.floor((availMain + gap + EPS) / (mainAt + gap))));
  if (shown === 0) return empty(total);

  const w = card.width_mm * scale;
  const h = card.height_mm * scale;
  const cards: AccessoryRect[] = [];
  for (let i = 0; i < shown; i += 1) {
    cards.push(
      vertical
        ? { x_mm: pad, y_mm: top + i * (h + gap), width_mm: w, height_mm: h }
        : { x_mm: pad + i * (w + gap), y_mm: top, width_mm: w, height_mm: h },
    );
  }
  const last = cards[shown - 1];
  const outW = vertical ? boxWidth_mm : last.x_mm + last.width_mm + pad;
  const cardsBottom = last.y_mm + last.height_mm;
  const outH = vertical ? cardsBottom + footerH + pad : boxHeight_mm;
  return {
    cards,
    shown,
    dropped: total - shown,
    boxWidth_mm: outW,
    boxHeight_mm: outH,
    ...accessoryChrome(props, outW, outH),
    scale,
    footer:
      footerH > 0
        ? { x_mm: pad, y_mm: cardsBottom, width_mm: Math.max(0, outW - 2 * pad), height_mm: footerH }
        : null,
  };
}

/** Accessories a designed box does not print for lack of room; feeds the drop warning. */
export function cardDropped(
  count: number,
  props: CardBoxProps,
  boxWidth_mm: number,
  boxHeight_mm: number,
): number {
  return cardBoxLayout(count, props, boxWidth_mm, boxHeight_mm).dropped;
}

// ---------------------------------------------------------------------------
// Fields
// ---------------------------------------------------------------------------

/** The value of one field for an accessory: text, a list of hex colours, a picture URL, or null. */
export function cardFieldValue(item: TagAccessory, field: CardField): string | string[] | null {
  switch (field) {
    case 'name':
      return item.name ?? null;
    case 'code':
      return item.code ?? null;
    case 'spec':
      return item.spec ?? null;
    case 'remark':
      return item.remark ?? null;
    case 'price':
      return item.list_price != null ? `LP: ${formatTagPrice(item.list_price)}` : null;
    case 'colours':
      return (item.colours ?? []).map((colour) => colour.hex);
    case 'picture':
      return item.image?.url ?? item.images?.[0]?.url ?? null;
  }
}

/** Distinct hex colours across the shown accessories, in order of first appearance. */
export function boxColours(items: readonly TagAccessory[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    for (const colour of item.colours ?? []) {
      const key = colour.hex.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(colour.hex);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Elements
// ---------------------------------------------------------------------------

/** An element with its content resolved: `text` is the value to print, `colours` the hex dots,
 *  `src` the picture URL. The rect is final, in card (or footer) millimetres, unscaled. */
export type ResolvedCardElement = CardElement & { src?: string | null };

function isBlank(value: string): boolean {
  return (isRich(value) ? richPlainText(value) : value).trim() === '';
}

type Resolver = (element: CardElement) => ResolvedCardElement | null;

/** Resolve every visible element, drop the empty ones, and close the gaps they leave (V7). */
function resolveElements(elements: readonly CardElement[], resolve: Resolver): ResolvedCardElement[] {
  const visible = elements.filter((element) => !element.hidden);
  const resolved = visible.map(resolve);
  const tops = visible.map((element) => element.y_mm);
  const gone = resolved.map((value) => value === null);

  const order = visible
    .map((_, index) => index)
    .filter((index) => gone[index])
    .sort((a, b) => visible[a].y_mm - visible[b].y_mm);
  const overlapsX = (a: CardElement, b: CardElement) =>
    a.x_mm < b.x_mm + b.width_mm - EPS && b.x_mm < a.x_mm + a.width_mm - EPS;

  const removed = new Set<number>();
  for (const dropped of order) {
    removed.add(dropped);
    const bottom = tops[dropped] + visible[dropped].height_mm;
    const below = visible
      .map((_, index) => index)
      .filter(
        (index) =>
          !removed.has(index) &&
          tops[index] >= bottom - EPS &&
          overlapsX(visible[dropped], visible[index]),
      );
    if (below.length === 0) continue;
    const shift = Math.min(...below.map((index) => tops[index])) - tops[dropped];
    if (!(shift > 0)) continue;
    for (const index of below) tops[index] -= shift;
  }

  const out: ResolvedCardElement[] = [];
  resolved.forEach((value, index) => {
    if (value) out.push({ ...value, y_mm: tops[index] });
  });
  return out;
}

function textOf(value: string | string[] | null): string | null {
  return typeof value === 'string' && !isBlank(value) ? value : null;
}

/**
 * The elements one accessory prints: the visible ones, an element whose field is empty for this
 * accessory dropped and the elements under it moved up into its space. The card keeps its size.
 */
export function cardElementsFor(item: TagAccessory, card: CardLayout): ResolvedCardElement[] {
  return resolveElements(card.elements ?? [], (element) => {
    switch (element.kind) {
      case 'shape':
        return { ...element };
      case 'picture': {
        const src = cardFieldValue(item, 'picture');
        return typeof src === 'string' && src ? { ...element, src } : null;
      }
      case 'colour_dots': {
        const picked = element.colours && element.colours.length > 0 ? element.colours : null;
        const colours = picked ?? (cardFieldValue(item, 'colours') as string[]);
        return colours.length > 0 ? { ...element, colours } : null;
      }
      case 'text': {
        const text = element.field ? textOf(cardFieldValue(item, element.field)) : textOf(element.text ?? null);
        return text ? { ...element, text } : null;
      }
    }
  });
}

/**
 * The footer's elements. Fixed text and shapes print as designed; colour dots default to the
 * colours of the shown accessories (`colours`) unless hand-picked; fields that read one accessory
 * have nothing to read here and are dropped.
 */
export function footerElementsFor(colours: readonly string[], footer: FooterLayout): ResolvedCardElement[] {
  return resolveElements(footer.elements ?? [], (element) => {
    switch (element.kind) {
      case 'shape':
        return { ...element };
      case 'picture':
        return null;
      case 'colour_dots': {
        const picked = element.colours && element.colours.length > 0 ? element.colours : null;
        const list = picked ?? [...colours];
        return list.length > 0 ? { ...element, colours: list } : null;
      }
      case 'text': {
        if (element.field) return null;
        const text = textOf(element.text ?? null);
        return text ? { ...element, text } : null;
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Drawing helpers shared by the canvas and the print page
// ---------------------------------------------------------------------------

export const DEFAULT_DOT_GAP_MM = 0.8;
export const DEFAULT_DOT_OUTLINE = '#9ca3af';
const MIN_CARD_TEXT_PT = 2.5;
const DEFAULT_CARD_TEXT_COLOR = '#111827';

/** The dots of a colour-dots element: each circle's top-left and diameter, in the element's own
 *  millimetres at `scale`. The size comes from the element (`dotSize_mm`) or its rect, and never
 *  exceeds what fits, so resizing the element resizes the dots. */
export function colourDotLayout(
  element: Pick<CardElement, 'width_mm' | 'height_mm' | 'dotSize_mm' | 'dotGap_mm' | 'dotDirection'>,
  count: number,
  scale = 1,
): { x_mm: number; y_mm: number; d_mm: number }[] {
  if (count <= 0) return [];
  const w = element.width_mm * scale;
  const h = element.height_mm * scale;
  const gap = (element.dotGap_mm ?? DEFAULT_DOT_GAP_MM) * scale;
  const row = element.dotDirection !== 'column';
  const fits = row
    ? Math.min(h, (w - (count - 1) * gap) / count)
    : Math.min(w, (h - (count - 1) * gap) / count);
  const wanted = element.dotSize_mm != null ? element.dotSize_mm * scale : fits;
  const d = Math.max(0, Math.min(wanted, fits));
  return Array.from({ length: count }, (_, i) =>
    row
      ? { x_mm: i * (d + gap), y_mm: (h - d) / 2, d_mm: d }
      : { x_mm: (w - d) / 2, y_mm: i * (d + gap), d_mm: d },
  );
}

/** A card text element as the text-layer props the text layout and both renderers already use,
 *  with the font drawn at `scale`. `boxFont` is the box's own family, used when the element has none. */
export function cardTextProps(element: CardElement, scale = 1, boxFont?: string): TextLayerProps {
  return {
    kind: 'text',
    text: element.text ?? '',
    fontFamily: element.fontFamily || boxFont || '',
    fontSize: (element.fontSize ?? 6) * scale,
    fontWeight: element.fontWeight ?? 400,
    color: element.color || DEFAULT_CARD_TEXT_COLOR,
    align: element.align ?? 'left',
    lineHeight: element.lineHeight ?? 1.1,
    letterSpacing: 0,
    italic: element.italic,
    underline: element.underline,
  };
}

function printedChars(text: string, props: TextLayerProps, width_mm: number, height_mm: number): number {
  const count = (value: string) => value.replace(/\s/g, '').length;
  if (isRich(text)) {
    const lines = textLayerLines(props, parseRichText(text), width_mm, height_mm);
    return lines.reduce((sum, line) => sum + line.reduce((n, run) => n + count(run.text), 0), 0);
  }
  return count(textLayerLines(props, text, width_mm, height_mm).join(''));
}

/**
 * The text props with the font shrunk until the whole text sits inside `width_mm` x `height_mm`
 * (card rule F3: it never spills out of its element, and is never cut). Canvas and print both call
 * it with the same inputs, so they pick the same size. Floors at a few points.
 */
export function fitCardTextProps(
  props: TextLayerProps,
  text: string,
  width_mm: number,
  height_mm: number,
): TextLayerProps {
  const total = (isRich(text) ? richPlainText(text) : text).replace(/\s/g, '').length;
  if (printedChars(text, props, width_mm, height_mm) >= total) return props;
  let size = props.fontSize;
  for (let i = 0; i < 14 && size > MIN_CARD_TEXT_PT; i += 1) {
    size = Math.max(MIN_CARD_TEXT_PT, size * 0.9);
    const next = { ...props, fontSize: size };
    if (printedChars(text, next, width_mm, height_mm) >= total) return next;
  }
  return { ...props, fontSize: Math.max(MIN_CARD_TEXT_PT, size) };
}

// ---------------------------------------------------------------------------
// Legacy conversion and design
// ---------------------------------------------------------------------------

/**
 * A card that reproduces the legacy card of a box: picture, then name / spec text (and the product
 * code and LP price when `lines` is 3), sized by `cardSize`, with the box's own name and spec
 * styles. Used when somebody first edits a box that has no `card`. `boxWidth_mm` sizes a vertical
 * box's card to the box (the legacy card spans the box); absent, the set `cardWidth_mm` is used.
 *
 * Three lines: code, name (name style), price, spec. The card is one spec line taller than the
 * legacy one, so the spec never overlaps the price.
 */
export function cardFromLegacy(
  props: AccessoriesLayerProps,
  lines = 2,
  boxWidth_mm?: number,
): CardLayout {
  const { w, h } = cardSize(
    props,
    boxWidth_mm ?? Math.max(0, props.cardWidth_mm) + 2 * ACCESSORY_BOX_PAD_MM,
    lines,
  );
  const inner = accessoryCardInner({ x_mm: 0, y_mm: 0, width_mm: w, height_mm: h }, props, true, lines);
  const nameStyle = accessoryLineStyle(props, 0);
  const specStyle = accessoryLineStyle(props, 1);
  const text = (
    id: string,
    field: CardField,
    row: AccessoryRect,
    style: typeof nameStyle,
    pt: number,
    over: Partial<AccessoryRect> = {},
  ): CardElement => ({
    id,
    kind: 'text',
    field,
    x_mm: row.x_mm,
    y_mm: over.y_mm ?? row.y_mm,
    width_mm: row.width_mm,
    height_mm: over.height_mm ?? row.height_mm,
    fontFamily: style.fontFamily,
    fontSize: pt,
    fontWeight: style.fontWeight,
    italic: style.italic,
    underline: style.underline,
    color: style.color,
    align: style.align,
    lineHeight: 1,
  });

  const elements: CardElement[] = [];
  if (inner.image) {
    elements.push({
      id: 'picture',
      kind: 'picture',
      field: 'picture',
      x_mm: inner.image.x_mm,
      y_mm: inner.image.y_mm,
      width_mm: inner.image.width_mm,
      height_mm: inner.image.height_mm,
      fit: 'contain',
    });
  }
  const rows = inner.lines;
  let height = h;
  if (lines >= 3 && rows.length >= 3) {
    const first = rows[0];
    const rest = rows[2];
    // Rows: code, name (both name size), price, spec (spec size). A library accessory has no code
    // or price, a product normally no description: the empty rows drop and the rest move up, so a
    // library card prints name then spec, a product code, name, LP (and its description under it).
    const nameTop = first.y_mm + first.height_mm;
    const priceTop = nameTop + first.height_mm;
    const specTop = priceTop + rest.height_mm;
    elements.push(text('code', 'code', first, nameStyle, props.nameFontSize));
    elements.push(text('name', 'name', first, nameStyle, props.nameFontSize, { y_mm: nameTop }));
    elements.push(text('price', 'price', rest, specStyle, props.specFontSize, { y_mm: priceTop }));
    elements.push(text('spec', 'spec', rest, specStyle, props.specFontSize, { y_mm: specTop }));
    // One more spec line than the legacy card holds, so the description never overlaps the price.
    height = h + rest.height_mm;
  } else {
    elements.push(text('name', 'name', rows[0], nameStyle, props.nameFontSize));
    if (rows[1]) elements.push(text('spec', 'spec', rows[1], specStyle, props.specFontSize));
  }
  return { width_mm: w, height_mm: height, elements };
}

/** The per-box keys: they live on the box in a tag template, never in a shared design. */
const PER_BOX_KEYS = ['kind', 'subjectSlot', 'subjectPart', 'presetId'] as const;

export type AccessoryDesign = Omit<AccessoriesLayerProps, (typeof PER_BOX_KEYS)[number]>;

/** The box props without the per-box keys: what "Save as accessories template" stores. */
export function accessoryDesign(props: AccessoriesLayerProps): AccessoryDesign {
  const copy: Record<string, unknown> = { ...props };
  for (const key of PER_BOX_KEYS) delete copy[key];
  return copy as unknown as AccessoryDesign;
}

/** A design applied to a box: the design's props, the box's own per-box keys kept, `presetId` set
 *  (null detaches). Per-box keys smuggled inside `design` are ignored. */
export function applyAccessoryDesign(
  props: AccessoriesLayerProps,
  design: AccessoryDesign,
  presetId: string | null,
): AccessoriesLayerProps {
  const next: Record<string, unknown> = { ...accessoryDesign(design as AccessoriesLayerProps), kind: 'accessories' };
  if (props.subjectSlot !== undefined) next.subjectSlot = props.subjectSlot;
  if (props.subjectPart !== undefined) next.subjectPart = props.subjectPart;
  if (presetId) next.presetId = presetId;
  return next as unknown as AccessoriesLayerProps;
}

/** Two full sample accessories (every field filled) for styling a card in the designer, so every
 *  element shows whatever the preview data holds. */
export function accessoryDesignSamples(): TagAccessory[] {
  const colours = [
    { name: 'Black', hex: '#1f2937' },
    { name: 'Grey', hex: '#9ca3af' },
  ];
  return [1, 2].map((n) => ({
    kind: 'accessory' as const,
    id: `design-sample-${n}`,
    name: 'Accessory name',
    spec: 'Spec line',
    remark: 'Remark',
    code: 'CODE',
    list_price: 68,
    image: null,
    images: [],
    colours,
  }));
}

// ---------------------------------------------------------------------------
// Designer helpers
// ---------------------------------------------------------------------------

export type CardEditTarget = 'card' | 'footer';

/** A new element of `kind`, centred in `area` (card or footer, millimetres). A card text reads the
 *  name; a footer text is a fixed note (nothing per accessory to read there). */
export function newCardElement(
  kind: CardElement['kind'],
  target: CardEditTarget,
  area: { w: number; h: number },
  id: string,
): CardElement {
  const size = (() => {
    switch (kind) {
      case 'picture':
        return { w: 12, h: 12 };
      case 'colour_dots':
        return { w: 12, h: 3 };
      case 'shape':
        return { w: 10, h: 4 };
      default:
        return { w: 20, h: 4 };
    }
  })();
  const w = Math.min(size.w, area.w);
  const h = Math.min(size.h, area.h);
  const base: CardElement = {
    id,
    kind,
    x_mm: Math.round(((area.w - w) / 2) * 100) / 100,
    y_mm: Math.round(((area.h - h) / 2) * 100) / 100,
    width_mm: w,
    height_mm: h,
  };
  switch (kind) {
    case 'picture':
      return { ...base, field: 'picture', fit: 'contain' };
    case 'colour_dots':
      return { ...base, field: 'colours', dotDirection: 'row' };
    case 'shape':
      return { ...base, shape: 'rounded_rect', fill: '#e5e7eb', stroke: '', cornerRadius_mm: 1 };
    default:
      return target === 'footer'
        ? { ...base, field: null, text: 'Note', fontSize: 5, fontWeight: 400, align: 'left' }
        : { ...base, field: 'name', fontSize: 6, fontWeight: 400, align: 'left' };
  }
}

/** Order-independent JSON, to compare two designs. */
export function designKey(design: unknown): string {
  const sort = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(sort);
    if (value && typeof value === 'object') {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>)
          .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
          .map(([key, item]) => [key, sort(item)]),
      );
    }
    return value;
  };
  return JSON.stringify(sort(design));
}

/** The design each linked box carries, by preset id (first box wins), with its comparison key. */
export function linkedBoxDesigns(
  layers: readonly { props: { kind: string } }[] | null | undefined,
): Map<string, { design: AccessoryDesign; key: string }> {
  const out = new Map<string, { design: AccessoryDesign; key: string }>();
  for (const layer of layers ?? []) {
    const props = layer?.props as unknown as AccessoriesLayerProps | undefined;
    if (!props || props.kind !== 'accessories' || !props.presetId || out.has(props.presetId)) continue;
    const design = accessoryDesign(props);
    out.set(props.presetId, { design, key: designKey(design) });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Snapping while an element is dragged in the card / footer editor
// ---------------------------------------------------------------------------

export const ELEMENT_SNAP_MM = 1;

export interface ElementGuide {
  orientation: 'horizontal' | 'vertical';
  /** Millimetres inside the card (or footer). */
  position_mm: number;
}

interface Box {
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
}

/** The nearest alignment of `[start, start + size]` (start, centre, end) to any target, within `limit`. */
function snapAxis(start: number, size: number, targets: number[], limit: number) {
  let best: { delta: number; guide: number } | null = null;
  for (const edge of [start, start + size / 2, start + size]) {
    for (const target of targets) {
      const delta = target - edge;
      if (Math.abs(delta) <= limit && (!best || Math.abs(delta) < Math.abs(best.delta))) {
        best = { delta, guide: target };
      }
    }
  }
  return best;
}

/**
 * Where a dragged element lands: its left / centre / right and top / middle / bottom pulled onto the
 * card's edges and centre lines and onto the other elements' edges and centres, within
 * `ELEMENT_SNAP_MM`, with a guide for each axis that snapped.
 */
export function snapElement(
  moving: Box,
  others: readonly Box[],
  area: { width_mm: number; height_mm: number },
  limit = ELEMENT_SNAP_MM,
): { x_mm: number; y_mm: number; guides: ElementGuide[] } {
  const xs = [0, area.width_mm / 2, area.width_mm];
  const ys = [0, area.height_mm / 2, area.height_mm];
  for (const other of others) {
    xs.push(other.x_mm, other.x_mm + other.width_mm / 2, other.x_mm + other.width_mm);
    ys.push(other.y_mm, other.y_mm + other.height_mm / 2, other.y_mm + other.height_mm);
  }
  const sx = snapAxis(moving.x_mm, moving.width_mm, xs, limit);
  const sy = snapAxis(moving.y_mm, moving.height_mm, ys, limit);
  const guides: ElementGuide[] = [];
  if (sx) guides.push({ orientation: 'vertical', position_mm: sx.guide });
  if (sy) guides.push({ orientation: 'horizontal', position_mm: sy.guide });
  return { x_mm: moving.x_mm + (sx?.delta ?? 0), y_mm: moving.y_mm + (sy?.delta ?? 0), guides };
}
