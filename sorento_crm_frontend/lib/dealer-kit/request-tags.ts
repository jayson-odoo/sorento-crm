/**
 * Turning a price tag request's lines into tags, and tags into printed sheets (D51).
 *
 * A line's tag is a `PlacedTag` cloned from a TEMPLATE and bound to the line's
 * item. Designing it edits that clone; the template it came from is never
 * written to from the request designer, which is the whole reason the clone
 * exists.
 *
 * Sheet arrangement is a consequence of the tags rather than a thing the user
 * has to do: every line's tag is laid out in line order, quantity times, on the
 * request's imposition preset. A copy somebody dragged in the Arrange view is
 * PINNED by line and copy index, so re-arranging keeps it and flows the rest
 * around it.
 */

import {
  bindTemplateLayers,
  buildProductBlock,
  buildSetStarterBlock,
  PRODUCT_BLOCK_SIZE,
  SET_BLOCK_SIZE,
} from './product-block';
import { lineFamily } from './line-family';
import type {
  GroupBinding,
  ImpositionConfig,
  LineTagData,
  PlacedTag,
  ProductTagData,
  TagLayer,
  TagSheet,
  TagSheetDoc,
  TagTemplate,
} from './tag-template-types';

// ---------------------------------------------------------------------------
// What a line has to look like for any of this to work
// ---------------------------------------------------------------------------

/** The part of a request line these helpers read. */
export interface TagRequestLine {
  id: string;
  line_type: 'product' | 'product_set';
  product_id: string | null;
  product_set_id: string | null;
  quantity: number;
}

// ---------------------------------------------------------------------------
// Which template a line starts from
// ---------------------------------------------------------------------------

/**
 * The template a line's tag is cloned from unless somebody picks another one.
 *
 * The family comes from the code prefix (`lineFamily`), so a sink combo opens
 * on the sink combo tag; a family with no template of its own falls back to
 * `ala_carte`, the plainest layout, and then to whatever exists, because a tag
 * that cannot be started is worse than a tag in the wrong layout.
 */
export function defaultTemplateFor(
  line: Pick<TagRequestLine, 'line_type'>,
  templates: TagTemplate[],
  code?: string,
): TagTemplate | null {
  if (templates.length === 0) return null;
  const family = lineFamily(line, code);
  return (
    templates.find((t) => t.family === family) ??
    templates.find((t) => t.family === 'ala_carte') ??
    templates[0]
  );
}

/** What the tag's groups are about: this line's product, or its set. */
export function bindingForLine(line: TagRequestLine): GroupBinding {
  return line.line_type === 'product_set'
    ? { product_set_id: line.product_set_id ?? undefined }
    : { product_id: line.product_id ?? undefined };
}

/**
 * The synthetic `TagTemplate.id` a starter carries. Never a real
 * `tag_templates` row, so anything that treats a template id as a foreign key
 * - the versions/publish machinery included - has to special-case this one.
 */
export const STARTER_TEMPLATE_ID = 'starter';

/**
 * The starter a line opens on when there is not one PUBLISHED template to
 * clone from (D6/D13): a product block - or, for a set line, a set block - at
 * the default block footprint, bound to the line's real product/set. The
 * design page must never dead-end on a silent "Preparing this line..."
 * (#476), so this stands in for a real template: a synthetic doc built from
 * the already-resolved line and never written back as a `tag_templates` row.
 *
 * `buildProductBlock`/`buildSetStarterBlock` do not know the line, so
 * whatever binding they seed their group with is provisional; `bindTemplateLayers`
 * below re-binds it to `bindingForLine(line)` the same way `tagForLine` binds
 * a real template's clone, so the starter's binding is never a stand-in id
 * (e.g. the line's own id) masquerading as a product/set id.
 */
export function starterTemplateFor(
  line: TagRequestLine,
  data: LineTagData | undefined,
  newId: () => string,
): TagTemplate {
  const opts = { newId, x_mm: 0, y_mm: 0, z_index: 0 };
  const isSet = line.line_type === 'product_set';

  const layers = isSet
    ? buildSetStarterBlock(
        {
          code: data?.code ?? '',
          name: data?.name ?? '',
          set_members: data?.set_members ?? '',
          list_price: data?.list_price ?? null,
          offer_price: data?.show_promo_price ? (data?.sell_price ?? null) : null,
        },
        opts,
      )
    : buildProductBlock(
        {
          // Never read for binding purposes - bindTemplateLayers below
          // overwrites the group's binding with the line's real product id.
          id: '',
          code: data?.code ?? '',
          name: data?.name ?? '',
          dimensions: data?.dimensions ?? '',
          spec_lines: data?.spec_lines ? data.spec_lines.split('\n') : [],
          specs: data?.specs ?? [],
          images: data?.images ?? [],
          list_price: data?.list_price ?? null,
          offer_price: data?.show_promo_price ? (data?.sell_price ?? null) : null,
          promotion_id: null,
        } satisfies ProductTagData,
        opts,
      );

  const size = isSet ? SET_BLOCK_SIZE : PRODUCT_BLOCK_SIZE;

  return {
    id: STARTER_TEMPLATE_ID,
    name: 'Starter',
    family: 'ala_carte',
    doc: {
      layers: bindTemplateLayers(layers, bindingForLine(line)),
      width_mm: size.width_mm,
      height_mm: size.height_mm,
    },
    print_size: { width_mm: size.width_mm, height_mm: size.height_mm },
    created_at: '',
    updated_at: '',
  };
}

// ---------------------------------------------------------------------------
// The tag itself
// ---------------------------------------------------------------------------

/**
 * A fresh tag for this line, cloned from `template`.
 *
 * The clone is deep: an edit on the tag must never reach the template, which is
 * shared by every future request in that family. The size is the template's
 * PRINT size rather than its document size, because that is what gets cut.
 */
export function tagForLine(
  line: TagRequestLine,
  template: TagTemplate,
  newId: string,
  position: { x_mm: number; y_mm: number } = { x_mm: 0, y_mm: 0 },
): PlacedTag {
  const layers = structuredClone(template.doc.layers) as TagLayer[];
  return {
    id: newId,
    template_id: template.id,
    request_line_id: line.id,
    x_mm: position.x_mm,
    y_mm: position.y_mm,
    width_mm: template.print_size.width_mm,
    height_mm: template.print_size.height_mm,
    layers: bindTemplateLayers(layers, bindingForLine(line)),
  };
}

// ---------------------------------------------------------------------------
// Imposition
// ---------------------------------------------------------------------------

export interface LayoutSlot {
  x_mm: number;
  y_mm: number;
}

/**
 * Where a tag of this size sits on one sheet of the chosen preset.
 *
 * The slot count is the sheet's capacity, which is what decides how many sheets
 * a request needs.
 */
export function impositionSlots(
  imposition: ImpositionConfig,
  tagW: number,
  tagH: number,
): LayoutSlot[] {
  const { page_width_mm, page_height_mm, bleed_mm, gap_mm, preset } = imposition;
  const usableW = page_width_mm - 2 * bleed_mm;
  const usableH = page_height_mm - 2 * bleed_mm;

  if (preset === 'a4_3up') {
    // One column, three rows, centred.
    const startX = bleed_mm + (usableW - tagW) / 2;
    const totalH = 3 * tagH + 2 * gap_mm;
    const startY = bleed_mm + (usableH - totalH) / 2;
    return [
      { x_mm: startX, y_mm: startY },
      { x_mm: startX, y_mm: startY + tagH + gap_mm },
      { x_mm: startX, y_mm: startY + 2 * (tagH + gap_mm) },
    ];
  }

  if (preset === 'a4_2x2') {
    const totalW = 2 * tagW + gap_mm;
    const totalH = 2 * tagH + gap_mm;
    const startX = bleed_mm + (usableW - totalW) / 2;
    const startY = bleed_mm + (usableH - totalH) / 2;
    return [
      { x_mm: startX, y_mm: startY },
      { x_mm: startX + tagW + gap_mm, y_mm: startY },
      { x_mm: startX, y_mm: startY + tagH + gap_mm },
      { x_mm: startX + tagW + gap_mm, y_mm: startY + tagH + gap_mm },
    ];
  }

  // Custom: a single tag, centred.
  return [
    {
      x_mm: bleed_mm + (usableW - tagW) / 2,
      y_mm: bleed_mm + (usableH - tagH) / 2,
    },
  ];
}

// ---------------------------------------------------------------------------
// Arranging the copies
// ---------------------------------------------------------------------------

/** One line's tag and how many of it the request asked for. */
export interface ArrangeItem {
  tag: PlacedTag;
  quantity: number;
}

/** Where a copy was dragged to, if it was. */
export interface PinnedPlacement {
  sheet: number;
  x_mm: number;
  y_mm: number;
}

/**
 * The identity of one printed copy.
 *
 * Keyed on the LINE rather than on the tag, so a pin survives the tag being
 * re-cloned from another template, and so a document written before copy ids
 * existed still pins its first copy.
 */
export function placementKey(lineId: string, copyIndex: number): string {
  return `${lineId}#${copyIndex}`;
}

/** The placement id a copy carries in the saved document. */
function copyId(tagId: string, copyIndex: number): string {
  return `${tagId}-c${copyIndex}`;
}

interface Copy {
  id: string;
  key: string;
  tag: PlacedTag;
}

/** Every copy that has to be printed, in line order then copy order. */
export function copiesOf(items: ArrangeItem[]): Copy[] {
  const copies: Copy[] = [];
  for (const item of items) {
    const count = Math.max(1, Math.floor(item.quantity || 1));
    for (let index = 0; index < count; index += 1) {
      copies.push({
        id: copyId(item.tag.id, index),
        key: placementKey(item.tag.request_line_id, index),
        tag: item.tag,
      });
    }
  }
  return copies;
}

/**
 * Lay every copy out on as many sheets as it takes.
 *
 * The slot grid is sized off the LARGEST tag in the request, so a mixed request
 * still prints without two tags overlapping. A pinned copy keeps the sheet and
 * the position it was dragged to and consumes no slot, which is what makes the
 * rest flow around it rather than leaving a hole where it used to be.
 */
export function autoArrange(
  items: ArrangeItem[],
  imposition: ImpositionConfig,
  pinned: Record<string, PinnedPlacement> = {},
): TagSheet[] {
  const copies = copiesOf(items);
  if (copies.length === 0) return [{ id: 'sheet-1', tags: [] }];

  const tagW = Math.max(...copies.map((c) => c.tag.width_mm));
  const tagH = Math.max(...copies.map((c) => c.tag.height_mm));
  const slots = impositionSlots(imposition, tagW, tagH);
  const perSheet = Math.max(1, slots.length);

  const placements: { sheet: number; tag: PlacedTag }[] = [];
  let flowIndex = 0;

  for (const copy of copies) {
    const pin = pinned[copy.key];
    const sheet = pin ? pin.sheet : Math.floor(flowIndex / perSheet);
    const slot = pin ?? slots[flowIndex % perSheet];
    if (!pin) flowIndex += 1;

    placements.push({
      sheet,
      tag: {
        ...copy.tag,
        id: copy.id,
        x_mm: slot.x_mm,
        y_mm: slot.y_mm,
        // The document has to say which copies were DRAGGED, because every copy
        // carries a position and a position cannot tell the two apart.
        pinned: Boolean(pin),
      },
    });
  }

  const sheetCount = Math.max(1, ...placements.map((p) => p.sheet + 1));
  const sheets: TagSheet[] = Array.from({ length: sheetCount }, (_, index) => ({
    id: `sheet-${index + 1}`,
    tags: [],
  }));
  for (const placement of placements) {
    sheets[placement.sheet].tags.push(placement.tag);
  }
  return sheets;
}

// ---------------------------------------------------------------------------
// Reading a saved arrangement back
// ---------------------------------------------------------------------------

/** The copy index a saved placement id carries, or 0 for a document written before them. */
function copyIndexOf(placementId: string): number {
  const match = /-c(\d+)$/.exec(placementId);
  return match ? Number(match[1]) : 0;
}

/** The pin key one placed copy answers to, wherever it came from. */
export function pinKeyForPlacement(
  tag: Pick<PlacedTag, 'id' | 'request_line_id'>,
): string {
  return placementKey(tag.request_line_id, copyIndexOf(tag.id));
}

/**
 * Every manual drag the saved document is carrying, ready to be re-applied.
 *
 * Only `pinned: true` counts. This used to read EVERY placed tag as a pin,
 * which meant one save and reopen froze the whole sheet: switching the
 * imposition preset re-imposed nothing, and bumping a line's quantity stacked
 * the new copy on top of copy 0 because every slot was already claimed. A
 * document saved before the flag existed therefore opens unpinned and is
 * re-imposed, which leaves the sheet correct rather than frozen.
 */
export function pinnedFromDoc(doc: TagSheetDoc | null): Record<string, PinnedPlacement> {
  const pinned: Record<string, PinnedPlacement> = {};
  if (!doc) return pinned;
  doc.sheets.forEach((sheet, sheetIndex) => {
    for (const tag of sheet.tags) {
      if (tag.pinned !== true) continue;
      pinned[placementKey(tag.request_line_id, copyIndexOf(tag.id))] = {
        sheet: sheetIndex,
        x_mm: tag.x_mm,
        y_mm: tag.y_mm,
      };
    }
  });
  return pinned;
}

/**
 * The per-line tags a saved document is carrying.
 *
 * The first copy of each line is the master: every copy holds the same layers,
 * so re-opening a saved design finds each line's tag exactly as it was drawn.
 */
export function tagsFromDoc(doc: TagSheetDoc | null): Map<string, PlacedTag> {
  const masters = new Map<string, PlacedTag>();
  if (!doc) return masters;
  for (const sheet of doc.sheets) {
    for (const tag of sheet.tags) {
      const existing = masters.get(tag.request_line_id);
      if (existing && copyIndexOf(existing.id) <= copyIndexOf(tag.id)) continue;
      masters.set(tag.request_line_id, {
        ...tag,
        id: tag.id.replace(/-c\d+$/, ''),
        x_mm: 0,
        y_mm: 0,
      });
    }
  }
  return masters;
}
