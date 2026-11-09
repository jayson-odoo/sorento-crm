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
  ACCESSORY_CARD_PAD_MM,
  accessoryCardInner,
  accessoryChrome,
  accessoryHeaderHeight,
  partAtSlot,
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
  TagAccessoryBoxStyle,
  TagBindingData,
  TagLayerProps,
  TextLayerProps,
} from './tag-template-types';

const EPS = 1e-9;
/** The smallest the cards shrink to before whole cards are dropped (owner ruling Q2). */
export const CARD_SHRINK_MIN = 0.7;

export type CardBoxProps = LayoutProps &
  Pick<AccessoriesLayerProps, 'card' | 'footer' | 'shrinkMin' | 'columns'>;

export interface CardBoxLayout extends AccessoryBoxLayout {
  /** The factor every card is drawn at (1 = its design size). */
  scale: number;
  /** The footer area, null when hidden. Not scaled. */
  footer: AccessoryRect | null;
  /** Columns actually drawn (a grid may draw fewer than asked when the card is too wide). 0 = nothing drawn. */
  columns: number;
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
    columns: 0,
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

  const innerW = boxWidth_mm - 2 * pad;
  if (props.columns !== undefined && props.columns !== null) {
    // S6 grid: cards fill left to right, wrap to the next row, every card the same size.
    const availH = boxHeight_mm - top - pad - footerH;
    const wanted =
      props.columns === 'auto'
        ? Math.floor((innerW + gap + EPS) / (card.width_mm + gap))
        : Math.floor(props.columns);
    let cols = Math.max(1, Math.min(total, wanted));
    const rowsFor = (n: number) => Math.ceil(total / n);
    const fitFor = (n: number) =>
      Math.min(
        1,
        (innerW - (n - 1) * gap) / (n * card.width_mm),
        (availH - (rowsFor(n) - 1) * gap) / (rowsFor(n) * card.height_mm),
      );
    let scale = Math.max(fitFor(cols), min);
    // Narrower than the grid at the smallest scale: fewer columns, never a card past the box.
    while (cols > 1 && cols * card.width_mm * scale + (cols - 1) * gap > innerW + EPS) {
      cols -= 1;
      scale = Math.max(fitFor(cols), min);
    }
    const cw = card.width_mm * scale;
    const ch = card.height_mm * scale;
    if (cw > innerW + EPS || !(ch > 0)) return empty(total);
    const maxRows = Math.floor((availH + gap + EPS) / (ch + gap));
    const gridShown = Math.min(total, Math.max(0, maxRows) * cols);
    if (gridShown === 0) return empty(total);
    const gridCards: AccessoryRect[] = [];
    for (let i = 0; i < gridShown; i += 1) {
      gridCards.push({
        x_mm: pad + (i % cols) * (cw + gap),
        y_mm: top + Math.floor(i / cols) * (ch + gap),
        width_mm: cw,
        height_mm: ch,
      });
    }
    const gridBottom = gridCards[gridShown - 1].y_mm + ch;
    const gridOutH = gridBottom + footerH + pad;
    return {
      cards: gridCards,
      shown: gridShown,
      dropped: total - gridShown,
      boxWidth_mm: boxWidth_mm,
      boxHeight_mm: gridOutH,
      ...accessoryChrome(props, boxWidth_mm, gridOutH),
      scale,
      columns: cols,
      footer:
        footerH > 0
          ? { x_mm: pad, y_mm: gridBottom, width_mm: Math.max(0, boxWidth_mm - 2 * pad), height_mm: footerH }
          : null,
    };
  }

  const vertical = props.direction !== 'horizontal';
  const availMain = vertical ? boxHeight_mm - top - pad - footerH : innerW;
  const availCross = vertical ? innerW : boxHeight_mm - top - pad - footerH;
  const cardMain = vertical ? card.height_mm : card.width_mm;
  const cardCross = vertical ? card.width_mm : card.height_mm;

  const fit = Math.min(1, (availMain - (total - 1) * gap) / (total * cardMain), availCross / cardCross);
  const scale = fit >= min ? fit : min;

  const mainAt = cardMain * scale;
  if (cardCross * scale > availCross + EPS || !(mainAt > 0)) return empty(total);
  const shown = Math.min(total, Math.max(0, Math.floor((availMain + gap + EPS) / (mainAt + gap))));
  // NaN-safe: a design missing a number (e.g. no gap) lays out nothing rather than throwing.
  if (!(shown > 0)) return empty(total);

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
    columns: vertical ? 1 : shown,
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
export type ResolvedCardElement = CardElement & {
  src?: string | null;
  /** Designer only: a picture element drawn as a neutral placeholder (never printed). */
  placeholder?: boolean;
};

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
    // The freed space starts below every KEPT element that overlaps the dropped one's column and reaches
    // into it from above (dots over the picture's lower part): the name never jumps into the picture.
    const freeFrom = visible.reduce((from, other, index) => {
      if (index === dropped || gone[index] || tops[index] >= bottom - EPS) return from;
      if (!overlapsX(visible[dropped], other)) return from;
      return Math.max(from, tops[index] + other.height_mm);
    }, tops[dropped]);
    const shift = Math.min(...below.map((index) => tops[index])) - freeFrom;
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
 * Card 1 while it is being edited: EVERY visible element at its own rect, none dropped for an empty
 * field and none moved up, so what is drawn sits exactly where its frame is. A picture is a
 * placeholder. The faded cards keep the real rule (`cardElementsFor`).
 */
export function cardElementsForDesign(item: TagAccessory, card: CardLayout): ResolvedCardElement[] {
  // A field this accessory has nothing for is drawn from the sample, so the element stays visible to place.
  const [sample] = accessoryDesignSamples();
  return (card.elements ?? [])
    .filter((element) => !element.hidden)
    .map((element): ResolvedCardElement => {
      switch (element.kind) {
        case 'picture':
          return { ...element, src: null, placeholder: true };
        case 'colour_dots': {
          const picked = element.colours && element.colours.length > 0 ? element.colours : null;
          const own = cardFieldValue(item, 'colours') as string[];
          const colours = picked ?? (own.length > 0 ? own : (cardFieldValue(sample, 'colours') as string[]));
          return { ...element, colours };
        }
        case 'text': {
          if (!element.field) return { ...element, text: element.text ?? '' };
          const own = textOf(cardFieldValue(item, element.field));
          const value = own ?? cardFieldValue(sample, element.field);
          return { ...element, text: typeof value === 'string' ? value : '' };
        }
        default:
          return { ...element };
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
  // Never shorter than the lowest row plus the card's inner margin, whatever the font sizes.
  const lowest = Math.max(0, ...elements.map((element) => element.y_mm + element.height_mm));
  return { width_mm: w, height_mm: Math.max(height, lowest + ACCESSORY_CARD_PAD_MM), elements };
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

/**
 * What a box under card editing draws: the previewed list, so the faded cards show what will really
 * print (CARD V1); the two samples only when there is no list to show (A7).
 */
export function accessoryEditItems(previewed: TagAccessory[] | null | undefined): TagAccessory[] {
  return previewed && previewed.length > 0 ? previewed : accessoryDesignSamples();
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

/**
 * PRICETAG-HEADER-DRAG: where a dragged box header lands, in mm from the box's top-left. It snaps
 * (left / centre / right, top / middle / bottom) onto the box's edges and centre lines and onto the
 * frame's edges (so its middle can sit on the top border), then is kept inside the box.
 */
export function snapHeader(
  header: Box,
  frame: Box | null,
  box: { width_mm: number; height_mm: number },
): { x_mm: number; y_mm: number; guides: ElementGuide[] } {
  const snapped = snapElement(header, frame ? [frame] : [], box);
  const clamp = (v: number, max: number) => Math.min(Math.max(0, max), Math.max(0, v));
  return {
    x_mm: clamp(snapped.x_mm, box.width_mm - header.width_mm),
    y_mm: clamp(snapped.y_mm, box.height_mm - header.height_mm),
    guides: snapped.guides,
  };
}

// ---------------------------------------------------------------------------
// Live link between boxes and a saved template
// ---------------------------------------------------------------------------

type LinkLayer = { id: string; props: { kind: string } };

function boxProps(layer: LinkLayer | undefined): AccessoriesLayerProps | null {
  const props = layer?.props as unknown as AccessoriesLayerProps | undefined;
  return props && props.kind === 'accessories' ? props : null;
}

/** Preset ids linked by at least one box. */
export function linkedPresetIds(layers: readonly LinkLayer[] | null | undefined): string[] {
  const ids = new Set<string>();
  for (const layer of layers ?? []) {
    const props = boxProps(layer);
    if (props?.presetId) ids.add(props.presetId);
  }
  return [...ids];
}

/**
 * The design of the LAST box linked to `presetId` whose design differs from `baselineKey`, else null.
 * With no baseline (a box inserted from a stale menu, pasted from another tab) nothing is "changed":
 * that box follows the server instead of being pushed.
 */
export function changedLinkedDesign(
  layers: readonly LinkLayer[] | null | undefined,
  presetId: string,
  baselineKey: string | undefined,
): AccessoryDesign | null {
  let changed: AccessoryDesign | null = null;
  for (const layer of layers ?? []) {
    const props = boxProps(layer);
    if (!props || props.presetId !== presetId) continue;
    const design = accessoryDesign(props);
    if (baselineKey !== undefined && designKey(design) !== baselineKey) changed = design;
  }
  return changed;
}

/** Every box linked to `presetId` takes `design` (its own position, size and "Reads from" kept). */
export function setLinkedDesign<T extends LinkLayer>(layers: readonly T[], presetId: string, design: AccessoryDesign): T[] {
  return layers.map((layer) => {
    const props = boxProps(layer);
    return props?.presetId === presetId
      ? ({ ...layer, props: applyAccessoryDesign(props, design, presetId) } as unknown as T)
      : layer;
  });
}

/** Every box linked to `presetId` loses the link and keeps its design. */
export function detachLinked<T extends LinkLayer>(layers: readonly T[], presetId: string): T[] {
  return layers.map((layer) => {
    const props = boxProps(layer);
    return props?.presetId === presetId
      ? ({ ...layer, props: { ...props, presetId: null } } as unknown as T)
      : layer;
  });
}

/** A correction to apply to a live box: only when its design still equals `expectedKey`. */
export interface LayerPropsPatch {
  layerId: string;
  /** `designKey(accessoryDesign(props))` of the box when the correction was worked out. */
  expectedKey: string;
  props: AccessoriesLayerProps;
}

export type LinkAction =
  | { kind: 'detach'; id: string }
  | { kind: 'set'; id: string; design: AccessoryDesign };

/** The live-box patches that carry out `actions`, worked out from the layers as they were saved. */
export function linkCorrectionPatches(
  layers: readonly LinkLayer[] | null | undefined,
  actions: readonly LinkAction[],
): LayerPropsPatch[] {
  const patches: LayerPropsPatch[] = [];
  for (const layer of layers ?? []) {
    const props = boxProps(layer);
    if (!props?.presetId) continue;
    const action = actions.find((candidate) => candidate.id === props.presetId);
    if (!action) continue;
    patches.push({
      layerId: layer.id,
      expectedKey: designKey(accessoryDesign(props)),
      props:
        action.kind === 'detach'
          ? ({ ...props, presetId: null } as AccessoriesLayerProps)
          : applyAccessoryDesign(props, action.design, action.id),
    });
  }
  return patches;
}

/**
 * What a copy of linked boxes (a request's tag) must do to follow the saved templates: detach where the
 * template is gone, take the template's design where the box differs from it. `find` answers null for a
 * deleted template; one that cannot be read is left alone.
 */
export async function linkRefreshActions(
  layers: readonly LinkLayer[] | null | undefined,
  find: (presetId: string) => Promise<{ design: AccessoryDesign } | null>,
): Promise<LinkAction[]> {
  const actions: LinkAction[] = [];
  for (const id of linkedPresetIds(layers)) {
    let record: { design: AccessoryDesign } | null;
    try {
      record = await find(id);
    } catch {
      continue;
    }
    if (!record) {
      actions.push({ kind: 'detach', id });
      continue;
    }
    const key = designKey(record.design);
    const stale = (layers ?? []).some((layer) => {
      const props = boxProps(layer);
      return props?.presetId === id && designKey(accessoryDesign(props)) !== key;
    });
    if (stale) actions.push({ kind: 'set', id, design: record.design });
  }
  return actions;
}

/** `layers` with `actions` carried out (the patches applied to a plain array). */
export function applyLinkActions<T extends LinkLayer>(layers: readonly T[], actions: readonly LinkAction[]): T[] {
  const patches = new Map(linkCorrectionPatches(layers, actions).map((patch) => [patch.layerId, patch]));
  return layers.map((layer) =>
    patches.has(layer.id) ? ({ ...layer, props: patches.get(layer.id)!.props } as unknown as T) : layer,
  );
}

/** Whether `changes` alter the box's DESIGN (not its per-box "Reads from" or its link). */
export function accessoryDesignChanged(props: AccessoriesLayerProps, changes: Partial<AccessoriesLayerProps>): boolean {
  return designKey(accessoryDesign({ ...props, ...changes })) !== designKey(accessoryDesign(props));
}

/**
 * The box style the previewed owner names, branching exactly like `accessoriesOf`: a position picked
 * reads that part's; a request line's part (-1 = the main product's row) that part's; a request line its
 * own (already resolved); a product preview with a combo the combo's (never the product's), else the
 * product's. Null when there is none, on an older payload, or with no data.
 */
export function accessoryBoxStyleOf(
  data: TagBindingData | null | undefined,
  layer: { props?: TagLayerProps } | undefined,
): TagAccessoryBoxStyle | null {
  if (!data) return null;
  const props = layer?.props?.kind === 'accessories' ? layer.props : undefined;
  const slot = props?.subjectSlot;
  if (slot && (data.kind === 'line' || data.kind === 'product')) {
    const slots = data.kind === 'line' ? data.line.slots : data.product.slots;
    return partAtSlot(slots, slot)?.accessory_box_style ?? null;
  }
  const part = props?.subjectPart;
  if (part !== undefined && data.kind === 'line') {
    if (part === -1) return data.line.slots?.main?.accessory_box_style ?? null;
    return data.line.parts[part]?.accessory_box_style ?? null;
  }
  if (data.kind === 'line') return data.line.accessory_box_style ?? null;
  if (data.kind === 'product') {
    const combo = data.product.combo;
    if (combo) return combo.accessory_box_style ?? null;
    return data.product.accessory_box_style ?? null;
  }
  return null;
}

/** The props a box draws: its own, or with the previewed owner's box style applied (position, size,
 *  "Reads from" and its own `presetId` kept). */
export function effectiveBoxProps(
  props: AccessoriesLayerProps,
  style: TagAccessoryBoxStyle | null | undefined,
): AccessoriesLayerProps {
  return style
    ? applyAccessoryDesign(props, style.design as unknown as AccessoryDesign, props.presetId ?? null)
    : props;
}
