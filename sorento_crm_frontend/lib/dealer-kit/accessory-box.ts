/**
 * PRICETAG-ACCESSORIES: the ONE rule that picks and lays out an "Accessories" box, used by the
 * editor canvas (KonvaTagLayer), the request preview (DesignViewer, same Konva layer) and the print
 * page (TagSheetRenderer), so the three cannot disagree (card rule A10, the `feature-icons.ts`
 * pattern).
 *
 * Card: documentation/plans/dealer-kit/CARD-pricetag-accessories-06nov.md (A3, A5-A8).
 * Everything is in millimetres inside the layer's own box; (0, 0) is its top-left corner.
 */
import { formatTagPrice } from './price-badge';
import { richOneLine } from './rich-text';
import type {
  AccessoriesLayerProps,
  AccessoryTextStyle,
  SubjectSlot,
  TagAccessory,
  TagBindingData,
  TagLayerProps,
  TagPartData,
  TagSlots,
} from './tag-template-types';

/** The box's inner margin, every side. */
export const ACCESSORY_BOX_PAD_MM = 1.5;
/** A card's own inner margin. */
export const ACCESSORY_CARD_PAD_MM = 0.8;
const PT_TO_MM = 0.3528;
const LINE = 1.2;

/** A horizontal card narrows to fit more cards in the box, but never below this (crew pass 2). */
export const ACCESSORY_MIN_CARD_WIDTH_MM = 16;

/**
 * The size a new "Accessories" box is added at: fits the owner's examples on a 148 x 105 mm tag,
 * 3 picture-above-text cards (product entries included) or a row of 3 (crew pass 2, 6 Nov: 45 x 40
 * held 2; owner hand test 6 Nov ~15:00: picture above text is the default, so it is taller).
 */
export const ACCESSORY_DEFAULT_BOX_MM = { width_mm: 60, height_mm: 80 };

/** Average advance of a bold capital, in em: deliberately generous, so an estimate that errs
 *  leaves room rather than overflowing. */
const HEADER_EM_PER_CHAR = 0.72;
const HEADER_MIN_PT = 3;

/** Average advance of a regular-weight character, in em (spec lines, LP). */
const LINE_EM_PER_CHAR = 0.6;
const LINE_MIN_PT = 3;

/** The width (mm) a card line takes at `fontSize_pt`, as the layout estimates it. */
export function estimateLineWidth(text: string, fontSize_pt: number, bold: boolean): number {
  return text.trim().length * (bold ? HEADER_EM_PER_CHAR : LINE_EM_PER_CHAR) * fontSize_pt * PT_TO_MM;
}

/**
 * The font size (pt) a card line prints at: its set size when it fits `width_mm`, else shrunk to
 * fit (crew pass 3: no ellipsis on a tag, the header rule). Canvas and print both call this.
 */
export function fitLinePt(text: string, width_mm: number, basePt: number, bold: boolean): number {
  const needed = estimateLineWidth(text, basePt, bold);
  if (!(needed > width_mm) || needed <= 0) return basePt;
  return Math.max(LINE_MIN_PT, (basePt * Math.max(0, width_mm)) / needed);
}

/** The width (mm) the header text takes at `fontSize_pt`, as the layout estimates it. */
export function estimateHeaderWidth(text: string, fontSize_pt: number): number {
  return text.trim().length * HEADER_EM_PER_CHAR * fontSize_pt * PT_TO_MM;
}

// ---------------------------------------------------------------------------
// Which list (A3)
// ---------------------------------------------------------------------------

export function partAtSlot(
  slots: TagSlots | null | undefined,
  slot: SubjectSlot,
): TagPartData | null {
  if (!slots) return null;
  switch (slot.kind) {
    case 'main':
      return slots.main ?? null;
    case 'fixed':
      return slots.fixed[slot.index] ?? null;
    case 'pick':
      return slots.groups[slot.group]?.picks[slot.index] ?? null;
    case 'upgrade':
      return slots.upgrades[slot.index] ?? null;
  }
}

/**
 * The accessories a box shows, in order.
 *
 * No position picked: the TAG's list. A request line carries it resolved (its combo's list on a
 * combo line, else its product's); a designer preview of a product shows the previewed combo's
 * list when a combo is previewed (never falling back to the product's: owner ruling Q1), else the
 * product's. A position picked: that product's own list. A set has none. A row pinned before the
 * list existed reads none.
 */
export function accessoriesOf(
  data: TagBindingData | null | undefined,
  layer: { props?: TagLayerProps } | undefined,
): TagAccessory[] {
  if (!data) return [];
  const props = layer?.props?.kind === 'accessories' ? layer.props : undefined;
  const slot = props?.subjectSlot;
  if (slot && (data.kind === 'line' || data.kind === 'product')) {
    const slots = data.kind === 'line' ? data.line.slots : data.product.slots;
    return partAtSlot(slots, slot)?.accessories ?? [];
  }
  // A request line's part picked in the request designer: that part's own list; -1 the main
  // product's own list (its position row), never the combo's.
  const part = props?.subjectPart;
  if (part !== undefined && data.kind === 'line') {
    if (part === -1) return data.line.slots?.main?.accessories ?? [];
    return data.line.parts[part]?.accessories ?? [];
  }
  if (data.kind === 'line') return data.line.accessories ?? [];
  if (data.kind === 'product') {
    const combo = data.product.combo;
    if (combo) return combo.accessories ?? [];
    return data.product.accessories ?? [];
  }
  return [];
}

/** Two named sample cards, so an unbound box can still be styled in the designer (A7). */
export function sampleAccessories(): TagAccessory[] {
  return [
    { id: 'sample-1', name: 'Accessory name', spec: 'Spec line', image: null },
    { id: 'sample-2', name: 'Accessory name', spec: 'Spec line', image: null },
  ];
}

// ---------------------------------------------------------------------------
// Layout (A5, A6, A7)
// ---------------------------------------------------------------------------

export interface AccessoryRect {
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface AccessoryBoxLayout {
  /** One per accessory that fits, in list order. */
  cards: AccessoryRect[];
  shown: number;
  /** Accessories that do not fit and are not drawn (never a card cut in half). */
  dropped: number;
  /** The box actually used: closed up around the cards; 0 x 0 when nothing shows. */
  boxWidth_mm: number;
  boxHeight_mm: number;
  /** The border and fill: the whole box, or from the header's middle down when the header sits on
   *  the border; null with the frame switched off. */
  frame: AccessoryRect | null;
  /** The header band; null when hidden or blank. `onBorder`: drawn over the frame's top edge, on
   *  the header background, breaking the border behind it. */
  header: (AccessoryRect & { fontSize_pt: number; onBorder: boolean }) | null;
  /** The round "+" badge, null when switched off. */
  badge: AccessoryRect | null;
}

export type LayoutProps = Pick<
  AccessoriesLayerProps,
  | 'direction'
  | 'headerText'
  | 'headerFontSize'
  | 'showBadge'
  | 'imageSize_mm'
  | 'nameFontSize'
  | 'specFontSize'
  | 'gap_mm'
  | 'cardWidth_mm'
  | 'itemLayout'
  | 'showHeader'
  | 'showFrame'
  | 'headerOnBorder'
  | 'headerStyle'
>;

/**
 * Picture above text ('stacked') or left of it ('side'). A box saved before the option existed
 * keeps what it drew: vertical boxes drew side, horizontal boxes drew stacked.
 */
export function itemLayoutOf(
  props: Pick<AccessoriesLayerProps, 'itemLayout' | 'direction'>,
): 'stacked' | 'side' {
  return props.itemLayout ?? (props.direction === 'horizontal' ? 'stacked' : 'side');
}

/** The header band's height; 0 when the header is hidden or its text is blank. */
export function accessoryHeaderHeight(
  props: Pick<AccessoriesLayerProps, 'headerText' | 'headerFontSize' | 'showHeader'>,
): number {
  if (props.showHeader === false) return 0;
  if (!props.headerText || !props.headerText.trim()) return 0;
  return Math.max(0, props.headerFontSize) * PT_TO_MM * LINE + 1;
}

/** How one text line of a card is set: role defaults, then the box's own style for that role. */
export interface AccessoryLineStyle {
  fontFamily: string | null;
  bold: boolean;
  fontWeight: number;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
  align: 'left' | 'center' | 'right';
  letterSpacing: number;
  color: string;
}

function resolveStyle(
  style: AccessoryTextStyle | undefined,
  defaults: { fontWeight: number; align: 'left' | 'center' | 'right'; color: string; fontFamily?: string },
): AccessoryLineStyle {
  const fontWeight = style?.fontWeight ?? defaults.fontWeight;
  return {
    fontFamily: style?.fontFamily || defaults.fontFamily || null,
    fontWeight,
    bold: fontWeight >= 600,
    italic: Boolean(style?.italic),
    underline: Boolean(style?.underline),
    strikethrough: Boolean(style?.strikethrough),
    align: style?.align ?? defaults.align,
    letterSpacing: style?.letterSpacing ?? 0,
    color: style?.color || defaults.color,
  };
}

/**
 * Line `n` of a card (0 = the name, or a product's code; the rest = spec lines): the name style
 * for the first line, the spec style for the others. Centred under a picture, left beside one.
 */
export function accessoryLineStyle(
  props: Pick<
    AccessoriesLayerProps,
    'nameStyle' | 'specStyle' | 'textColor' | 'itemLayout' | 'direction' | 'fontFamily'
  >,
  n: number,
): AccessoryLineStyle {
  const align = itemLayoutOf(props) === 'stacked' ? 'center' : 'left';
  return n === 0
    ? resolveStyle(props.nameStyle, {
        fontWeight: 700, align, color: props.textColor, fontFamily: props.fontFamily,
      })
    : resolveStyle(props.specStyle, {
        fontWeight: 400, align, color: props.textColor, fontFamily: props.fontFamily,
      });
}

/** The header's style: bold, centred, the header colour, unless the box sets otherwise. */
export function accessoryHeaderStyle(
  props: Pick<AccessoriesLayerProps, 'headerStyle' | 'headerColor' | 'fontFamily'>,
): AccessoryLineStyle {
  return resolveStyle(props.headerStyle, {
    fontWeight: 700, align: 'center', color: props.headerColor, fontFamily: props.fontFamily,
  });
}

/**
 * The text a card prints, line by line: a library accessory its name then its spec; a product its
 * code, its description and "LP: RM 68" (owner, 6 Nov ~10:45). The first line is the name line.
 */
export function accessoryCardLines(item: TagAccessory): string[] {
  if (item.kind === 'product') {
    const lines = [item.code ?? '', item.name].filter((line) => line && line.trim());
    if (item.list_price != null) lines.push(`LP: ${formatTagPrice(item.list_price)}`);
    return lines;
  }
  // A rich spec (the designed card reads the markup) prints as one plain line on the legacy card.
  return [item.name, richOneLine(item.spec)].filter((line) => line && line.trim());
}

/** How many text lines every card in a box reserves: 3 once a product is listed, else 2. */
export function accessoryLineCount(items: readonly TagAccessory[]): number {
  return items.some((item) => item.kind === 'product') ? 3 : 2;
}

/** The first line at the name size, every other line at the spec size, so every card in a box is
 *  the same height whatever it holds. */
function textBlockHeight(
  props: Pick<AccessoriesLayerProps, 'nameFontSize' | 'specFontSize'>,
  lines: number,
): number {
  const rest = Math.max(0, lines - 1);
  return (
    (Math.max(0, props.nameFontSize) + rest * Math.max(0, props.specFontSize)) * PT_TO_MM * LINE
  );
}

export function cardSize(props: LayoutProps, boxWidth_mm: number, lines: number): { w: number; h: number } {
  const image = Math.max(0, props.imageSize_mm);
  const text = textBlockHeight(props, lines);
  const h =
    itemLayoutOf(props) === 'stacked'
      ? image + text + 3 * ACCESSORY_CARD_PAD_MM
      : Math.max(image, text) + 2 * ACCESSORY_CARD_PAD_MM;
  const w =
    props.direction === 'horizontal'
      ? Math.max(0, props.cardWidth_mm)
      : Math.max(0, boxWidth_mm - 2 * ACCESSORY_BOX_PAD_MM);
  return { w, h };
}

const EPS = 1e-9;

/**
 * Where everything in the box goes for `count` accessories.
 *
 * Vertical: cards stack top to bottom at the box's inner width. Horizontal: cards run left to
 * right, each `cardWidth_mm` wide (narrowed to fit more). As many WHOLE cards as fit are kept;
 * the box then closes up around them from the bottom (vertical) or the right (horizontal), its
 * top-left corner staying put. Nothing to show draws nothing at all.
 *
 * Header inside the frame: a band under the frame's top edge. Header on the border (legend): the
 * band straddles the frame's top edge, centred and only as wide as its text, so the frame starts
 * at the band's middle.
 */
export function accessoryBoxLayout(
  count: number,
  props: LayoutProps,
  boxWidth_mm: number,
  boxHeight_mm: number,
  lines = 2,
): AccessoryBoxLayout {
  const total = Math.max(0, Math.floor(count));
  const empty = (dropped: number): AccessoryBoxLayout => ({
    cards: [],
    shown: 0,
    dropped,
    boxWidth_mm: 0,
    boxHeight_mm: 0,
    frame: null,
    header: null,
    badge: null,
  });
  if (total === 0) return empty(0);

  const pad = ACCESSORY_BOX_PAD_MM;
  const gap = Math.max(0, props.gap_mm);
  const headerH = accessoryHeaderHeight(props);
  const onBorder = Boolean(props.headerOnBorder) && headerH > 0;
  // Cards start under the header either way: on the border the band runs from 0 to headerH;
  // inside the frame it starts half a pad down.
  const top = onBorder ? headerH + pad * 0.5 : pad + headerH;
  const { w, h } = cardSize(props, boxWidth_mm, lines);
  if (!(w > 0) || !(h > 0)) return empty(total);

  const cards: AccessoryRect[] = [];
  if (props.direction === 'horizontal') {
    if (top + h > boxHeight_mm - pad + EPS) return empty(total);
    // Every card the same width (card Q-M2 (a)): the set width when it fits, else narrowed so more
    // whole cards fit, never below the minimum (or the set width, if that is smaller).
    const inner = boxWidth_mm - 2 * pad;
    const floor = Math.min(w, ACCESSORY_MIN_CARD_WIDTH_MM);
    const widthFor = (n: number) => Math.min(w, (inner - (n - 1) * gap) / n);
    let n = total;
    while (n > 0 && widthFor(n) < floor - EPS) n -= 1;
    const cardW = n > 0 ? widthFor(n) : 0;
    for (let i = 0; i < n; i += 1) {
      cards.push({ x_mm: pad + i * (cardW + gap), y_mm: top, width_mm: cardW, height_mm: h });
    }
  } else {
    while (
      cards.length < total &&
      top + (cards.length + 1) * h + cards.length * gap <= boxHeight_mm - pad + EPS
    ) {
      cards.push({ x_mm: pad, y_mm: top + cards.length * (h + gap), width_mm: w, height_mm: h });
    }
  }
  const shown = cards.length;
  if (shown === 0) return empty(total);

  const last = cards[shown - 1];
  const outW = props.direction === 'horizontal' ? last.x_mm + last.width_mm + pad : boxWidth_mm;
  const outH = props.direction === 'horizontal' ? boxHeight_mm : last.y_mm + last.height_mm + pad;
  return {
    cards,
    shown,
    dropped: total - shown,
    boxWidth_mm: outW,
    boxHeight_mm: outH,
    ...accessoryChrome(props, outW, outH),
  };
}

/**
 * The box's frame, header band and "+" badge for a box closed up to `outW` x `outH`. Shared by the
 * legacy layout and the designed-card layout (`cardBoxLayout`) so the two draw the same chrome.
 */
export function accessoryChrome(
  props: LayoutProps & Pick<AccessoriesLayerProps, 'showFrame'>,
  outW: number,
  outH: number,
): Pick<AccessoryBoxLayout, 'frame' | 'header' | 'badge'> {
  const pad = ACCESSORY_BOX_PAD_MM;
  const headerH = accessoryHeaderHeight(props);
  const onBorder = Boolean(props.headerOnBorder) && headerH > 0;
  const frameTop = onBorder ? headerH / 2 : 0;
  const badgeSize = Math.max(3.5, headerH > 0 ? headerH : 4);
  // The header clears the badge (crew pass, 6 Nov: at 45 mm the "+" hid the first letter): the same
  // inset on both sides, so the text stays centred in the box.
  const headerInset = props.showBadge ? pad * 0.5 + badgeSize + 0.5 : pad;
  const room = Math.max(0, outW - 2 * headerInset);
  const bold = (props.headerStyle?.fontWeight ?? 700) >= 600;
  // Shrink to fit, never truncate (crew pass 2: "ACCESSORIES I..." at 45 mm).
  const textW = estimateLineWidth(props.headerText ?? '', props.headerFontSize, bold);
  const headerPt =
    textW > room && textW > 0
      ? Math.max(HEADER_MIN_PT, (props.headerFontSize * room) / textW)
      : props.headerFontSize;
  // On the border the band is only as wide as its text (plus a little air either side), so the
  // border shows left and right of it; inside the frame it spans the room it has.
  const bandW = onBorder
    ? Math.min(room, estimateLineWidth(props.headerText ?? '', headerPt, bold) + 2 * pad)
    : room;
  return {
    frame:
      props.showFrame === false
        ? null
        : { x_mm: 0, y_mm: frameTop, width_mm: outW, height_mm: outH - frameTop },
    header:
      headerH > 0
        ? {
            x_mm: onBorder ? (outW - bandW) / 2 : headerInset,
            y_mm: onBorder ? 0 : pad * 0.5,
            width_mm: bandW,
            height_mm: headerH,
            fontSize_pt: headerPt,
            onBorder,
          }
        : null,
    badge: props.showBadge
      ? { x_mm: pad * 0.5, y_mm: frameTop + pad * 0.5, width_mm: badgeSize, height_mm: badgeSize }
      : null,
  };
}

/**
 * Inside one card: the picture and its text lines, relative to the card's own corner. Picture
 * above text: picture on top, lines centred under it. Picture left of text: picture left, lines
 * beside it. No picture: the text takes the picture's space (A8).
 */
export function accessoryCardInner(
  card: AccessoryRect,
  props: Pick<
    AccessoriesLayerProps,
    'direction' | 'itemLayout' | 'imageSize_mm' | 'nameFontSize' | 'specFontSize'
  >,
  hasImage: boolean,
  lines = 2,
): { image: AccessoryRect | null; lines: AccessoryRect[]; align: 'left' | 'center' } {
  const p = ACCESSORY_CARD_PAD_MM;
  const img = Math.max(0, props.imageSize_mm);
  const firstH = Math.max(0, props.nameFontSize) * PT_TO_MM * LINE;
  const restH = Math.max(0, props.specFontSize) * PT_TO_MM * LINE;
  const blockH = textBlockHeight(props, lines);
  const rows = (x: number, top: number, width: number): AccessoryRect[] =>
    Array.from({ length: Math.max(1, lines) }, (_, i) => ({
      x_mm: x,
      y_mm: top + (i === 0 ? 0 : firstH + (i - 1) * restH),
      width_mm: width,
      height_mm: i === 0 ? firstH : restH,
    }));
  if (itemLayoutOf(props) === 'stacked') {
    const image = hasImage
      ? { x_mm: p, y_mm: p, width_mm: card.width_mm - 2 * p, height_mm: img }
      : null;
    const textTop = hasImage ? p + img + p : (card.height_mm - blockH) / 2;
    return { image, lines: rows(p, textTop, card.width_mm - 2 * p), align: 'center' };
  }
  const image = hasImage
    ? { x_mm: p, y_mm: (card.height_mm - img) / 2, width_mm: img, height_mm: img }
    : null;
  const textX = hasImage ? p + img + p : p;
  const textW = Math.max(0, card.width_mm - textX - p);
  return { image, lines: rows(textX, (card.height_mm - blockH) / 2, textW), align: 'left' };
}

/** Points to millimetres, for a renderer sizing text in mm. */
export function ptToMm(pt: number): number {
  return pt * PT_TO_MM;
}
