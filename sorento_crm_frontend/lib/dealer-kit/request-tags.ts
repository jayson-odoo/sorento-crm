/**
 * Turning a price tag request's lines into tags, and tags into printed sheets (D51).
 *
 * A line's tag is a `PlacedTag` cloned from a TEMPLATE and bound to the line's
 * item. Designing it edits that clone; the template it came from is never
 * written to from the request designer, which is the whole reason the clone
 * exists.
 *
 * Sheet arrangement is a consequence of the tags rather than a thing the user
 * has to do: every tag is laid out in line order, quantity times, GROUPED BY
 * SIZE (S7) - a size group packs its own sheets at zero gap inside a fixed 5mm
 * printable margin, turning 90deg when that seats more, before the next size
 * starts a fresh sheet. Nothing to drag: a manual pin (pre-S7) is gone, every
 * arrange re-flows the whole request from its lines.
 *
 * Since S3 (D3) a LINE may carry several TAGS: an open choice group is split
 * into one tag per candidate, each with its own design and price. Everything
 * here therefore keys on the request TAG; the line is still what says which
 * product a tag binds to, which is why every helper takes the pair.
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
  TagTemplateDoc,
  TagTemplateFamily,
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

/**
 * The part of a request TAG these helpers read, with the line it prints (D3).
 *
 * The line comes along because binding is still a LINE fact - a tag prints its
 * line's product, whichever candidate it resolved - while identity, quantity
 * and geometry are the tag's.
 */
export interface TagRequestTag {
  id: string;
  quantity: number;
  /** r10 S6: marked Not printed - arrange seats no copy of it. */
  print_excluded?: boolean;
  line: TagRequestLine;
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
 * below re-binds it to `bindingForLine(line)` the same way `tagForTag` binds
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
          barcode: data?.barcode ?? null,
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
 * A fresh placement for this request tag, cloned from `template`.
 *
 * The clone is deep: an edit on the tag must never reach the template, which is
 * shared by every future request in that family. The size is the template's
 * PRINT size rather than its document size, because that is what gets cut.
 *
 * Binding comes from the tag's LINE - two tags split off the same line print
 * the same host product and differ only in the candidate they resolved.
 */
export function tagForTag(
  requestTag: TagRequestTag,
  template: TagTemplate,
  newId: string,
  position: { x_mm: number; y_mm: number } = { x_mm: 0, y_mm: 0 },
): PlacedTag {
  const layers = structuredClone(template.doc.layers) as TagLayer[];
  const line = requestTag.line;
  return {
    id: newId,
    template_id: template.id,
    request_tag_id: requestTag.id,
    x_mm: position.x_mm,
    y_mm: position.y_mm,
    width_mm: template.print_size.width_mm,
    height_mm: template.print_size.height_mm,
    layers: bindTemplateLayers(layers, bindingForLine(line)),
  };
}

// ---------------------------------------------------------------------------
// Tag size control (D24, S9)
// ---------------------------------------------------------------------------

/** One choice in the tag-size control's dropdown. */
export interface TagSizePreset {
  label: string;
  width_mm: number;
  height_mm: number;
}

/**
 * The size choices offered in the request designer's tag-size control (D24):
 * every PUBLISHED template's print size (`templates` is already
 * `listPublishedTemplates()`'s result, so no separate published filter is
 * needed here), deduped by size, plus the starter block's own footprint -
 * always present, so the list is never empty even before any template has
 * loaded. "Custom" is not a member of this list; the control itself offers
 * it alongside these as the escape hatch for typing an arbitrary size.
 */
export function tagSizePresets(templates: TagTemplate[]): TagSizePreset[] {
  const seen = new Set<string>();
  const presets: TagSizePreset[] = [];
  const add = (label: string, width_mm: number, height_mm: number) => {
    const key = `${width_mm}x${height_mm}`;
    if (seen.has(key)) return;
    seen.add(key);
    presets.push({ label, width_mm, height_mm });
  };

  for (const t of templates) {
    add(
      `${t.name} (${t.print_size.width_mm} x ${t.print_size.height_mm} mm)`,
      t.print_size.width_mm,
      t.print_size.height_mm,
    );
  }
  add(
    `Starter (${PRODUCT_BLOCK_SIZE.width_mm} x ${PRODUCT_BLOCK_SIZE.height_mm} mm)`,
    PRODUCT_BLOCK_SIZE.width_mm,
    PRODUCT_BLOCK_SIZE.height_mm,
  );

  return presets;
}

// ---------------------------------------------------------------------------
// Save as template (S4, PLAN D1)
// ---------------------------------------------------------------------------

/** What `templateFromTag` needs beyond the tag's own layers/size. */
export interface TemplateFromTagInput {
  name: string;
  family: TagTemplateFamily;
  /** Fresh id generator, so a saved template shares none of its layer ids
   *  with the tag it was cloned from (AC-S4-9) - callers pass their own
   *  monotonic id source, the same one every other clone in this file uses. */
  newId: () => string;
}

/**
 * Turn a designed tag into a template payload (AC-S4-6/7/9, D1).
 *
 * Every layer gets a fresh id (group `children` remapped alongside), so the
 * saved template shares nothing with the tag it came from - editing one can
 * never reach into the other. Bound layers (`slot_binding` set) lose their
 * `text_override`: a slot binding is what makes a template apply to every
 * product in the family, and a value typed for THIS line is not that. Unbound
 * text - a hand-typed heading, say - has no binding to fall back to and stays
 * exactly as typed.
 */
export function templateFromTag(
  tag: PlacedTag,
  input: TemplateFromTagInput,
): { name: string; family: TagTemplateFamily; doc: TagTemplateDoc; print_size: { width_mm: number; height_mm: number } } {
  const idMap = new Map<string, string>();
  for (const layer of tag.layers) idMap.set(layer.id, input.newId());

  const layers: TagLayer[] = tag.layers.map((layer) => {
    const clone: TagLayer = {
      ...structuredClone(layer),
      id: idMap.get(layer.id) as string,
      text_override: layer.slot_binding ? null : layer.text_override,
    };
    if (clone.props.kind === 'group') {
      clone.props = {
        ...clone.props,
        children: clone.props.children
          .map((childId) => idMap.get(childId))
          .filter((childId): childId is string => Boolean(childId)),
      };
    }
    return clone;
  });

  return {
    name: input.name,
    family: input.family,
    doc: { layers, width_mm: tag.width_mm, height_mm: tag.height_mm },
    print_size: { width_mm: tag.width_mm, height_mm: tag.height_mm },
  };
}

/**
 * Resize one line's tag footprint - the outer plate size `autoArrange` lays
 * sheets out with, not the layers inside it. Every copy of the line shares
 * this one `PlacedTag` (`copiesOf`), so a single update here is what "changing
 * it applies to all copies of that line" means; a pinned copy's position is
 * untouched because `autoArrange` looks it up by line+copy-index regardless
 * of size (AC-S9-3).
 */
export function resizeTag(tag: PlacedTag, width_mm: number, height_mm: number): PlacedTag {
  return { ...tag, width_mm, height_mm };
}

/** "Apply to all lines" (AC-S9-3): one size, every line's tag. */
export function resizeAllTags(
  tags: Record<string, PlacedTag>,
  width_mm: number,
  height_mm: number,
): Record<string, PlacedTag> {
  const next: Record<string, PlacedTag> = {};
  for (const [lineId, tag] of Object.entries(tags)) {
    next[lineId] = resizeTag(tag, width_mm, height_mm);
  }
  return next;
}

/**
 * A template document's `print_size` mirror (S1): `doc.width_mm/height_mm`
 * and the template's own top-level `print_size` are two copies of the same
 * fact, and this is the ONE place either the create or the update path
 * reads it from - a doc resized without going through this could leave the
 * two disagreeing forever, since nothing else compares them.
 */
export function printSizeOf(doc: {
  width_mm: number;
  height_mm: number;
}): { width_mm: number; height_mm: number } {
  return { width_mm: doc.width_mm, height_mm: doc.height_mm };
}

/** The floor every tag size control clamps up to (S9 review S3). */
export const MIN_TAG_SIZE_MM = 10;

/** The bounds a tag's own size may be set to on the given sheet. */
export interface TagSizeBounds {
  min_mm: number;
  max_width_mm: number;
  max_height_mm: number;
}

/**
 * The size bounds a tag may be set to (D24, S9 review S3; S7: no longer
 * per-imposition - every sheet is the same A4 page with the same 5mm
 * printable margin, so the ceiling is a constant, page minus 10mm per axis
 * (AC-S7-7)): a size that could never physically fit is refused rather than
 * drawn wrong.
 */
export function tagSizeBounds(): TagSizeBounds {
  return {
    min_mm: MIN_TAG_SIZE_MM,
    max_width_mm: USABLE_WIDTH_MM,
    max_height_mm: USABLE_HEIGHT_MM,
  };
}

/**
 * Resolve a typed size against `bounds`.
 *
 * Below the minimum clamps UP to it - a benign floor, the same as every
 * other mm field in this editor. Above what the sheet can hold is REFUSED
 * outright rather than silently shrunk to fit: a designer who typed 400mm
 * asked for something specific, and drawing a different number than the one
 * they typed without saying so is the worse failure of the two.
 */
export function resolveTagSize(
  width_mm: number,
  height_mm: number,
  bounds: TagSizeBounds,
): { ok: true; width_mm: number; height_mm: number } | { ok: false; reason: string } {
  if (width_mm > bounds.max_width_mm || height_mm > bounds.max_height_mm) {
    return {
      ok: false,
      reason: `Largest that fits this sheet is ${bounds.max_width_mm} x ${bounds.max_height_mm} mm`,
    };
  }
  return {
    ok: true,
    width_mm: Math.max(bounds.min_mm, width_mm),
    height_mm: Math.max(bounds.min_mm, height_mm),
  };
}

// ---------------------------------------------------------------------------
// Apply this design to all lines (S5, D3, D11)
// ---------------------------------------------------------------------------

/**
 * "Apply this design to all lines" (AC-S5-1/2/5): the SELECTED tag's design,
 * cloned onto every other tag on the request - and for the "Use template..."
 * picker's "Apply to all lines" checkbox, `tags[sourceTagId]` is a pristine
 * `tagForTag` clone the caller already stashed under the source tag, so this
 * one function covers both surfaces (D3).
 *
 * Every clone gets FRESH layer ids (group `children` remapped alongside), so
 * no two tags ever share an id - the same reason `templateFromTag`
 * remaps ids, just fanned out to N lines instead of one template. Unlike
 * `templateFromTag`, `text_override` is copied VERBATIM (D3): this is one
 * line's tag becoming every line's tag, not a tag becoming a reusable
 * template, so a hand-typed price note is exactly what "apply to all lines"
 * is supposed to spread.
 *
 * `bindTemplateLayers` re-points each clone's group binding at the TARGET
 * tag's own line's product/set - a straight copy would leave every other tag
 * pointing at the source line's item - and clears a stale barcode override the
 * same way a fresh clone from a template does.
 *
 * A tag that already had a placement keeps its position/pin (AC-S5-2): those
 * live on the `PlacedTag` a caller may be carrying position/pin state on, and
 * losing them here would silently un-arrange whatever was dragged. A tag with
 * no placement yet gets one too (AC-S5-5), so it never later clones from the
 * request's default template and quietly undoes the bulk apply.
 */
/**
 * A layer array, fresh ids throughout (group `children` remapped alongside)
 * so no two tags ever share one - the cloning step both
 * `applyDesignToAllTags` and `applyDesignToSiblings` (S6) need, pulled out
 * once they were the same nine lines twice.
 */
function cloneLayersWithFreshIds(layers: TagLayer[], newId: () => string): TagLayer[] {
  const idMap = new Map<string, string>();
  for (const layer of layers) idMap.set(layer.id, newId());
  return layers.map((layer) => {
    const clone: TagLayer = {
      ...structuredClone(layer),
      id: idMap.get(layer.id) as string,
    };
    if (clone.props.kind === 'group') {
      clone.props = {
        ...clone.props,
        children: clone.props.children
          .map((childId) => idMap.get(childId))
          .filter((childId): childId is string => Boolean(childId)),
      };
    }
    return clone;
  });
}

export function applyDesignToAllTags(
  tags: Record<string, PlacedTag>,
  requestTags: TagRequestTag[],
  sourceTagId: string,
  newId: () => string,
): Record<string, PlacedTag> {
  const source = tags[sourceTagId];
  if (!source) return tags;

  const next: Record<string, PlacedTag> = { ...tags };
  for (const requestTag of requestTags) {
    if (requestTag.id === sourceTagId) continue;

    const layers = cloneLayersWithFreshIds(source.layers, newId);
    const existing = next[requestTag.id];
    next[requestTag.id] = {
      id: newId(),
      template_id: source.template_id,
      request_tag_id: requestTag.id,
      x_mm: existing?.x_mm ?? 0,
      y_mm: existing?.y_mm ?? 0,
      width_mm: source.width_mm,
      height_mm: source.height_mm,
      layers: bindTemplateLayers(layers, bindingForLine(requestTag.line)),
    };
  }
  return next;
}

/**
 * "Update <template>" with its sibling checkbox on (S6, AC-S6-4): the
 * SOURCE tag's current design - layout AND size - cloned onto every OTHER
 * tag on the request whose CURRENT placement's `template_id` matches the same
 * template. Unlike `applyDesignToAllTags`, a tag NOT already on this template
 * (a different template, or no placement at all) is left untouched rather than
 * switched onto it - Update republishes T for whoever is already using it, it
 * does not make more tags use it.
 */
export function applyDesignToSiblings(
  tags: Record<string, PlacedTag>,
  requestTags: TagRequestTag[],
  sourceTagId: string,
  templateId: string,
  newId: () => string,
): Record<string, PlacedTag> {
  const source = tags[sourceTagId];
  if (!source) return tags;

  const next: Record<string, PlacedTag> = { ...tags };
  for (const requestTag of requestTags) {
    if (requestTag.id === sourceTagId) continue;
    const existing = next[requestTag.id];
    if (!existing || existing.template_id !== templateId) continue;

    next[requestTag.id] = {
      id: newId(),
      template_id: source.template_id,
      request_tag_id: requestTag.id,
      x_mm: existing.x_mm,
      y_mm: existing.y_mm,
      width_mm: source.width_mm,
      height_mm: source.height_mm,
      layers: bindTemplateLayers(
        cloneLayersWithFreshIds(source.layers, newId),
        bindingForLine(requestTag.line),
      ),
    };
  }
  return next;
}

// ---------------------------------------------------------------------------
// Imposition (S7): every arranged sheet is the same portrait A4 page with the
// same 5mm printable margin - nothing left to configure PER SHEET, only per
// SIZE GROUP (see "Arranging the copies" below).
// ---------------------------------------------------------------------------

export interface LayoutSlot {
  x_mm: number;
  y_mm: number;
}

/** How many of a tag this size fit on one sheet, and the grid shape (S6, D8). */
export interface ImpositionFit {
  cols: number;
  rows: number;
  perSheet: number;
}

/**
 * A doc saved before S6 carries `preset: 'a4_3up'`/`'a4_2x2'` - every preset
 * has laid out identically since S6 (AC-S6-4), but nothing ever WROTE 'auto'
 * back. Kept for a doc that still carries the old value; S7 no longer reads
 * `imposition` off a saved doc at all (`DEFAULT_IMPOSITION` below is written
 * on every arrange), so this is now dead code kept for API continuity only.
 */
export function normaliseImpositionPreset(imposition: ImpositionConfig): ImpositionConfig {
  if (imposition.preset === 'a4_3up' || imposition.preset === 'a4_2x2') {
    return { ...imposition, preset: 'auto' };
  }
  return imposition;
}

/** The A4 page every arranged sheet prints on (S7, Q2): always portrait, no
 *  per-request choice. */
const PAGE_WIDTH_MM = 210;
const PAGE_HEIGHT_MM = 297;

/** The printable margin every arranged sheet keeps on every edge (S7, Q3) -
 *  the registration margin a printer needs, not a design choice. */
export const PRINT_MARGIN_MM = 5;

const USABLE_WIDTH_MM = PAGE_WIDTH_MM - 2 * PRINT_MARGIN_MM;
const USABLE_HEIGHT_MM = PAGE_HEIGHT_MM - 2 * PRINT_MARGIN_MM;

/**
 * Real print tolerance (S7): every tag size field in this editor shows one
 * decimal place, so a size chosen to divide the usable block evenly (e.g.
 * 200mm / 3 cols = 66.666...7mm, shown and stored as 66.7mm) reads a few
 * hundredths of a millimetre "over" taken back literally (3 x 66.7 = 200.1).
 * A physical cut tolerates far more than that, so the fit math folds a small
 * allowance into the floor rather than under-counting a grid the owner
 * measured and sized on purpose.
 */
const FIT_TOLERANCE_MM = 0.5;

/** Every arranged doc's `imposition` (S7): fixed, written on every arrange -
 *  a doc saved under the old page/bleed/gap fields (or the even older
 *  presets) is fully replaced rather than merged (AC-S7-7). */
export const DEFAULT_IMPOSITION: ImpositionConfig = {
  preset: 'auto',
  page_width_mm: PAGE_WIDTH_MM,
  page_height_mm: PAGE_HEIGHT_MM,
  bleed_mm: PRINT_MARGIN_MM,
  gap_mm: 0,
};

/** Hard ceiling per axis (S2): kept as a safety net against a pathological
 *  tiny tag size producing a five- or six-figure slot count. */
const MAX_IMPOSITION_AXIS = 200;

/**
 * How many tags of this size fit one sheet, per axis.
 *
 * `floor((usable + gap + tolerance) / (tag + gap))` folds the last gap into
 * the division so N tags separated by N-1 gaps compares correctly against the
 * usable span (usable = page minus bleed on both sides), and folds in
 * `FIT_TOLERANCE_MM` (S7, see above). Either axis floors to 0 when the tag
 * does not fit at all, which floors `perSheet` to 0 too (AC-S6-3).
 *
 * A blank/invalid field (`NaN`) or `tag + gap === 0` (division by zero,
 * `Infinity`) is not a valid grid - `Number.isFinite` catches both and folds
 * them to 0, same as "does not fit" (S2). A grid that DOES fit is still
 * clamped to `MAX_IMPOSITION_AXIS` per axis.
 */
export function impositionFit(
  page_width_mm: number,
  page_height_mm: number,
  bleed_mm: number,
  gap_mm: number,
  tag_width_mm: number,
  tag_height_mm: number,
): ImpositionFit {
  const usableW = page_width_mm - 2 * bleed_mm;
  const usableH = page_height_mm - 2 * bleed_mm;
  const rawCols = Math.floor((usableW + gap_mm + FIT_TOLERANCE_MM) / (tag_width_mm + gap_mm));
  const rawRows = Math.floor((usableH + gap_mm + FIT_TOLERANCE_MM) / (tag_height_mm + gap_mm));
  const cols = Number.isFinite(rawCols) ? Math.min(MAX_IMPOSITION_AXIS, Math.max(0, rawCols)) : 0;
  const rows = Number.isFinite(rawRows) ? Math.min(MAX_IMPOSITION_AXIS, Math.max(0, rawRows)) : 0;
  return { cols, rows, perSheet: cols * rows };
}

/**
 * A per-size PRINT grid, named on a template's `print_size` or a saved size
 * preset (S7, AC-S7-11/12/15): `cols x rows` cells across the usable block,
 * `turn` seats the tag rotated 90deg in each cell.
 */
export interface SheetGridConfig {
  cols: number;
  rows: number;
  turn: boolean;
}

/**
 * Resolves the CONFIGURED grid for one size group at arrange time (AC-S7-15):
 * the group's own template's `print_size.sheet` when it names this exact
 * size, else a saved size preset with the same size, else null (arrange
 * derives instead). The request designer builds this from its already-loaded
 * templates and saved sizes; this module stays free of data fetching.
 */
export type SizeGridLookup = (
  width_mm: number,
  height_mm: number,
  templateId: string,
) => SheetGridConfig | null;

/**
 * What one size prints as, resolved (S7): either the CONFIGURED grid (cell =
 * usable block / cols x rows), or the DERIVED best fit - `impositionFit` at
 * gap 0 inside the printable margin, for rotation 0 and rotation 90, the
 * rotation with more per sheet winning (tie: 0) - AC-S7-1/2. A configured
 * grid whose cell cannot hold the (possibly turned) tag is REFUSED:
 * `refusedCell` names the cell it did not fit (AC-S7-13) and the result falls
 * back to the derived fit.
 */
export interface SizeGridInfo {
  cols: number;
  rows: number;
  rotation: 0 | 90;
  perSheet: number;
  configured: boolean;
  refusedCell?: { width_mm: number; height_mm: number };
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

function deriveSizeGrid(width_mm: number, height_mm: number): SizeGridInfo {
  const straight = impositionFit(PAGE_WIDTH_MM, PAGE_HEIGHT_MM, PRINT_MARGIN_MM, 0, width_mm, height_mm);
  const turned = impositionFit(PAGE_WIDTH_MM, PAGE_HEIGHT_MM, PRINT_MARGIN_MM, 0, height_mm, width_mm);
  return turned.perSheet > straight.perSheet
    ? { cols: turned.cols, rows: turned.rows, rotation: 90, perSheet: turned.perSheet, configured: false }
    : { cols: straight.cols, rows: straight.rows, rotation: 0, perSheet: straight.perSheet, configured: false };
}

export function resolveSizeGrid(
  width_mm: number,
  height_mm: number,
  configured: SheetGridConfig | null,
): SizeGridInfo {
  if (!configured || configured.cols <= 0 || configured.rows <= 0) {
    return deriveSizeGrid(width_mm, height_mm);
  }

  const cellW = USABLE_WIDTH_MM / configured.cols;
  const cellH = USABLE_HEIGHT_MM / configured.rows;
  const rotation: 0 | 90 = configured.turn ? 90 : 0;
  const placedW = rotation === 90 ? height_mm : width_mm;
  const placedH = rotation === 90 ? width_mm : height_mm;

  if (placedW <= cellW + FIT_TOLERANCE_MM && placedH <= cellH + FIT_TOLERANCE_MM) {
    return {
      cols: configured.cols,
      rows: configured.rows,
      rotation,
      perSheet: configured.cols * configured.rows,
      configured: true,
    };
  }

  // AC-S7-13: the configured cell cannot hold the tag - name it and derive.
  return {
    ...deriveSizeGrid(width_mm, height_mm),
    refusedCell: { width_mm: round1(cellW), height_mm: round1(cellH) },
  };
}

/**
 * Row-major slots for a `cols x rows` grid of `slotW x slotH` boxes, centred
 * in the printable margin - the SAME code path for a derived fit (slot = the
 * placed tag's own size, so the block centres, AC-S7-1) and a configured grid
 * (slot = the cell size, so the grid fills the block exactly and centring is
 * a no-op, AC-S7-12) - adjacent slots always touch (AC-S7-3).
 */
function gridSlots(cols: number, rows: number, slotW: number, slotH: number): LayoutSlot[] {
  if (cols <= 0 || rows <= 0) return [];
  const totalW = cols * slotW;
  const totalH = rows * slotH;
  const startX = PRINT_MARGIN_MM + (USABLE_WIDTH_MM - totalW) / 2;
  const startY = PRINT_MARGIN_MM + (USABLE_HEIGHT_MM - totalH) / 2;
  const slots: LayoutSlot[] = [];
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      slots.push({ x_mm: startX + col * slotW, y_mm: startY + row * slotH });
    }
  }
  return slots;
}

/**
 * The one overflowing, centred slot a tag too big for the page in either
 * rotation still gets (AC-S7-10) - every copy needs somewhere to go, or the
 * next reload finds no tag for that line at all.
 */
function overflowSlot(placedW: number, placedH: number): LayoutSlot {
  return {
    x_mm: PRINT_MARGIN_MM + (USABLE_WIDTH_MM - placedW) / 2,
    y_mm: PRINT_MARGIN_MM + (USABLE_HEIGHT_MM - placedH) / 2,
  };
}

// ---------------------------------------------------------------------------
// Arranging the copies
// ---------------------------------------------------------------------------

/** One request tag's placement and how many copies of it to print. */
export interface ArrangeItem {
  tag: PlacedTag;
  quantity: number;
  /** r10 S6 (AC-S6-8): a tag marked Not printed gets no copy and no slot,
   *  so it never reaches a sheet, the sheet counts or the export. */
  print_excluded?: boolean;
}

/** The placement id a copy carries in the saved document. */
function copyId(tagId: string, copyIndex: number): string {
  return `${tagId}-c${copyIndex}`;
}

interface Copy {
  id: string;
  tag: PlacedTag;
}

/** Every copy that has to be printed, in line order then copy order. */
export function copiesOf(items: ArrangeItem[]): Copy[] {
  const copies: Copy[] = [];
  for (const item of items) {
    if (item.print_excluded) continue;
    const count = Math.max(1, Math.floor(item.quantity || 1));
    for (let index = 0; index < count; index += 1) {
      copies.push({ id: copyId(item.tag.id, index), tag: item.tag });
    }
  }
  return copies;
}

/** What one arranged sheet holds (S7) - not stored in the doc (AC-S7-7: the
 *  doc gains no new field), so the caller keeps this alongside `doc.sheets`
 *  for display only ("Small Price Tag SP - 3 x 9, 27 of 30", AC-S7-6). */
export interface SheetPlacement {
  template_id: string;
  width_mm: number;
  height_mm: number;
  rotation: 0 | 90;
  cols: number;
  rows: number;
  /** The TRUE fit capacity - 0 when the tag does not fit the page in either
   *  rotation (AC-S7-10), even though that sheet still holds one overflowing
   *  copy. */
  capacity: number;
}

export interface ArrangeResult {
  sheets: TagSheet[];
  placement: SheetPlacement[];
}

/**
 * Lay every copy out on as many sheets as its SIZE GROUP needs (S7): copies
 * are grouped by `(width_mm, height_mm)`, biggest group first by area (a
 * stable sort keeps a tie in first-seen/line order), and each group starts a
 * FRESH sheet - two different sizes never share one (AC-S7-5). Within a
 * group, `resolveSizeGrid` decides the layout once (a configured grid, else
 * the derived best fit) and every sheet that group needs repeats it -
 * AC-S7-1/2/3/12/13.
 */
export function autoArrange(
  items: ArrangeItem[],
  gridForSize: SizeGridLookup = () => null,
): ArrangeResult {
  const copies = copiesOf(items);
  if (copies.length === 0) return { sheets: [{ id: 'sheet-1', tags: [] }], placement: [] };

  const groups = new Map<
    string,
    { width_mm: number; height_mm: number; template_id: string; copies: Copy[] }
  >();
  for (const copy of copies) {
    const key = `${copy.tag.width_mm}x${copy.tag.height_mm}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        width_mm: copy.tag.width_mm,
        height_mm: copy.tag.height_mm,
        template_id: copy.tag.template_id,
        copies: [],
      };
      groups.set(key, group);
    }
    group.copies.push(copy);
  }

  const ordered = [...groups.values()].sort(
    (a, b) => b.width_mm * b.height_mm - a.width_mm * a.height_mm,
  );

  const sheets: TagSheet[] = [];
  const placement: SheetPlacement[] = [];

  for (const group of ordered) {
    const configured = gridForSize(group.width_mm, group.height_mm, group.template_id);
    const grid = resolveSizeGrid(group.width_mm, group.height_mm, configured);
    const placedW = grid.rotation === 90 ? group.height_mm : group.width_mm;
    const placedH = grid.rotation === 90 ? group.width_mm : group.height_mm;

    const slots =
      grid.perSheet === 0
        ? [overflowSlot(placedW, placedH)]
        : gridSlots(
            grid.cols,
            grid.rows,
            grid.configured ? USABLE_WIDTH_MM / grid.cols : placedW,
            grid.configured ? USABLE_HEIGHT_MM / grid.rows : placedH,
          );
    const slotsPerSheet = Math.max(1, slots.length);
    const sheetsNeeded = Math.ceil(group.copies.length / slotsPerSheet);

    for (let s = 0; s < sheetsNeeded; s += 1) {
      const sheetCopies = group.copies.slice(s * slotsPerSheet, (s + 1) * slotsPerSheet);
      sheets.push({
        id: `sheet-${sheets.length + 1}`,
        tags: sheetCopies.map((copy, slotIndex) => ({
          ...copy.tag,
          id: copy.id,
          x_mm: slots[slotIndex].x_mm,
          y_mm: slots[slotIndex].y_mm,
          rotation: grid.rotation,
        })),
      });
      placement.push({
        template_id: group.template_id,
        width_mm: group.width_mm,
        height_mm: group.height_mm,
        rotation: grid.rotation,
        cols: grid.cols,
        rows: grid.rows,
        capacity: grid.perSheet,
      });
    }
  }

  return { sheets, placement };
}

// ---------------------------------------------------------------------------
// Reading a saved arrangement back
// ---------------------------------------------------------------------------

/** The copy index a saved placement id carries, or 0 for a document written before them. */
function copyIndexOf(placementId: string): number {
  const match = /-c(\d+)$/.exec(placementId);
  return match ? Number(match[1]) : 0;
}

/**
 * The per-TAG placements a saved document is carrying, keyed by request tag id.
 *
 * The first copy of each tag is the master: every copy holds the same layers,
 * so re-opening a saved design finds each tag exactly as it was drawn. A doc
 * saved before S7 may carry `pinned: true` on some placements - no longer
 * read (S7 drops pins entirely, AC-S7-4), so it re-flows exactly like any
 * other saved doc.
 */
export function tagsFromDoc(doc: TagSheetDoc | null): Map<string, PlacedTag> {
  const masters = new Map<string, PlacedTag>();
  if (!doc) return masters;
  for (const sheet of doc.sheets) {
    for (const tag of sheet.tags) {
      const existing = masters.get(tag.request_tag_id);
      if (existing && copyIndexOf(existing.id) <= copyIndexOf(tag.id)) continue;
      masters.set(tag.request_tag_id, {
        ...tag,
        id: tag.id.replace(/-c\d+$/, ''),
        x_mm: 0,
        y_mm: 0,
      });
    }
  }
  return masters;
}
