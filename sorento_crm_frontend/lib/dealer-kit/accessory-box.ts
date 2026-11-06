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
import type {
  AccessoriesLayerProps,
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

// ---------------------------------------------------------------------------
// Which list (A3)
// ---------------------------------------------------------------------------

function partAtSlot(
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
  /** The frame actually drawn: closed up around the cards; 0 x 0 when nothing shows. */
  boxWidth_mm: number;
  boxHeight_mm: number;
  /** The header band (inside the frame, above the cards); null with no header text. */
  header: AccessoryRect | null;
  /** The round "+" badge, null when switched off. */
  badge: AccessoryRect | null;
}

type LayoutProps = Pick<
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
>;

/** The header band's height; 0 when the header text is blank. */
export function accessoryHeaderHeight(
  props: Pick<AccessoriesLayerProps, 'headerText' | 'headerFontSize'>,
): number {
  if (!props.headerText || !props.headerText.trim()) return 0;
  return Math.max(0, props.headerFontSize) * PT_TO_MM * LINE + 1;
}

/**
 * The text a card prints, line by line: a library accessory its name then its spec; a product its
 * code, its description and "LP: RM 68" (owner, 6 Nov ~10:45). The first line is the bold one.
 */
export function accessoryCardLines(item: TagAccessory): string[] {
  if (item.kind === 'product') {
    const lines = [item.code ?? '', item.name].filter(
      (line) => line && line.trim(),
    );
    if (item.list_price != null)
      lines.push(`LP: ${formatTagPrice(item.list_price)}`);
    return lines;
  }
  return [item.name, item.spec ?? ''].filter((line) => line && line.trim());
}

/** How many text lines every card in a box reserves: 3 once a product is listed, else 2. */
export function accessoryLineCount(items: readonly TagAccessory[]): number {
  return items.some((item) => item.kind === 'product') ? 3 : 2;
}

/** The first (bold) line at the name size, every other line at the spec size, so every card in a
 *  box is the same height whatever it holds. */
function textBlockHeight(
  props: Pick<AccessoriesLayerProps, 'nameFontSize' | 'specFontSize'>,
  lines: number,
): number {
  const rest = Math.max(0, lines - 1);
  return (
    (Math.max(0, props.nameFontSize) + rest * Math.max(0, props.specFontSize)) *
    PT_TO_MM *
    LINE
  );
}

function cardSize(
  props: LayoutProps,
  boxWidth_mm: number,
  lines: number,
): { w: number; h: number } {
  const image = Math.max(0, props.imageSize_mm);
  const text = textBlockHeight(props, lines);
  if (props.direction === 'horizontal') {
    return {
      w: Math.max(0, props.cardWidth_mm),
      h: image + text + 3 * ACCESSORY_CARD_PAD_MM,
    };
  }
  return {
    w: Math.max(0, boxWidth_mm - 2 * ACCESSORY_BOX_PAD_MM),
    h: Math.max(image, text) + 2 * ACCESSORY_CARD_PAD_MM,
  };
}

const EPS = 1e-9;

/**
 * Where everything in the box goes for `count` accessories.
 *
 * Vertical: cards stack top to bottom at the box's inner width. Horizontal: cards run left to
 * right, each `cardWidth_mm` wide. As many WHOLE cards as fit are kept; the frame then closes up
 * around them from the bottom (vertical) or the right (horizontal), its top-left corner staying
 * put. Nothing to show (no accessories, or not even one card fits) draws nothing at all.
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
    header: null,
    badge: null,
  });
  if (total === 0) return empty(0);

  const pad = ACCESSORY_BOX_PAD_MM;
  const gap = Math.max(0, props.gap_mm);
  const headerH = accessoryHeaderHeight(props);
  const top = pad + headerH;
  const { w, h } = cardSize(props, boxWidth_mm, lines);
  if (!(w > 0) || !(h > 0)) return empty(total);

  const cards: AccessoryRect[] = [];
  if (props.direction === 'horizontal') {
    if (top + h > boxHeight_mm - pad + EPS) return empty(total);
    while (
      cards.length < total &&
      pad + (cards.length + 1) * w + cards.length * gap <=
        boxWidth_mm - pad + EPS
    ) {
      cards.push({
        x_mm: pad + cards.length * (w + gap),
        y_mm: top,
        width_mm: w,
        height_mm: h,
      });
    }
  } else {
    while (
      cards.length < total &&
      top + (cards.length + 1) * h + cards.length * gap <=
        boxHeight_mm - pad + EPS
    ) {
      cards.push({
        x_mm: pad,
        y_mm: top + cards.length * (h + gap),
        width_mm: w,
        height_mm: h,
      });
    }
  }
  const shown = cards.length;
  if (shown === 0) return empty(total);

  const last = cards[shown - 1];
  const outW =
    props.direction === 'horizontal'
      ? last.x_mm + last.width_mm + pad
      : boxWidth_mm;
  const outH =
    props.direction === 'horizontal'
      ? boxHeight_mm
      : last.y_mm + last.height_mm + pad;
  const badgeSize = Math.max(3.5, headerH > 0 ? headerH : 4);
  return {
    cards,
    shown,
    dropped: total - shown,
    boxWidth_mm: outW,
    boxHeight_mm: outH,
    header:
      headerH > 0
        ? {
            x_mm: pad,
            y_mm: pad * 0.5,
            width_mm: outW - 2 * pad,
            height_mm: headerH,
          }
        : null,
    badge: props.showBadge
      ? {
          x_mm: pad * 0.5,
          y_mm: pad * 0.5,
          width_mm: badgeSize,
          height_mm: badgeSize,
        }
      : null,
  };
}

/**
 * Inside one card: the picture and the two text lines, relative to the card's own corner.
 * Vertical cards put the picture left and the text beside it; horizontal cards put the picture on
 * top and the text centred under it. No picture: the text takes the picture's space (A8).
 */
export function accessoryCardInner(
  card: AccessoryRect,
  props: Pick<
    AccessoriesLayerProps,
    'direction' | 'imageSize_mm' | 'nameFontSize' | 'specFontSize'
  >,
  hasImage: boolean,
  lines = 2,
): {
  image: AccessoryRect | null;
  lines: AccessoryRect[];
  align: 'left' | 'center';
} {
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
  if (props.direction === 'horizontal') {
    const image = hasImage
      ? { x_mm: p, y_mm: p, width_mm: card.width_mm - 2 * p, height_mm: img }
      : null;
    const textTop = hasImage ? p + img + p : (card.height_mm - blockH) / 2;
    return {
      image,
      lines: rows(p, textTop, card.width_mm - 2 * p),
      align: 'center',
    };
  }
  const image = hasImage
    ? {
        x_mm: p,
        y_mm: (card.height_mm - img) / 2,
        width_mm: img,
        height_mm: img,
      }
    : null;
  const textX = hasImage ? p + img + p : p;
  const textW = Math.max(0, card.width_mm - textX - p);
  return {
    image,
    lines: rows(textX, (card.height_mm - blockH) / 2, textW),
    align: 'left',
  };
}

/** Points to millimetres, for a renderer sizing text in mm. */
export function ptToMm(pt: number): number {
  return pt * PT_TO_MM;
}
