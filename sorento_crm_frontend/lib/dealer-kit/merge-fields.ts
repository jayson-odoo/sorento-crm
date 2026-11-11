/**
 * `{{path}}` inside a tag's text, resolved once for every surface (D55-D56).
 *
 * A text layer used to be one of two things: free text, or ONE whole product
 * field through `slot_binding`. Marketing does not write tags that way. A line
 * reads "800 x 500 x 220 mm in stainless steel", which names two fields inside
 * one sentence, so before this the designer typed both by hand and the tag
 * stopped following the product the moment the master data changed.
 *
 * The token set is fixed and small, and every `product.*` and `set.*` path
 * answers through `resolveSlotText` - the SAME slot the tag already binds by.
 * That is why `product.code` and `set.code` are one question asked twice: a set
 * block's code IS its set code, and a token reading empty because the block
 * turned out to be a set would be a trap rather than a rule.
 *
 * What is NOT here, on purpose: filters, arithmetic and conditionals. The plan
 * names the trigger instead (D55) - the first real request for a price minus a
 * deposit, or "show X only when Y", is when a formula layer gets designed.
 *
 * The import of `resolveSlotText` from `product-block` and the import of
 * `renderMergeFields` back from here are a deliberate pair: both are used
 * inside function bodies, never at module scope, so neither module needs the
 * other to have finished loading.
 */

import { isRich, richPlainText } from './rich-text';
import { comboPartField, comboPartsHtml } from './combo-parts';
import { comboPositions } from './combo-slots';
import { formatTagPrice } from './price-badge';
import { comboOf, resolveSlotText, slotLabel, subjectOf } from './product-block';
import type {
  SlotBinding,
  SubjectSlot,
  TagBindingData,
  TagLayer,
  TagSlots,
  TagSpecValue,
} from './tag-template-types';

/**
 * `editor` draws an unresolvable token as itself so the designer can see what
 * will fill; `print` draws nothing, because a customer must never read
 * `{{spec.material}}` off a price tag.
 */
export type MergeFieldMode = 'print' | 'editor';

/** How the Insert field dialog sorts the catalogue into sections. */
export type MergeFieldGroup =
  | 'Product'
  | 'Specs'
  | 'Set'
  | 'Line'
  | 'Combo'
  | 'Combo positions'
  | 'Parts'
  | 'Spec sheet';

/** AC-A7: an older pinned/cached payload predating `currency` renders this,
 *  never an empty string or the raw token - same default the backend column
 *  carries (`products.currency`, `DEFAULT_CURRENCY` in `pricing.py`). */
const DEFAULT_TAG_CURRENCY = 'MYR';

export interface MergeField {
  /** `product.code`. What goes inside the braces. */
  path: string;
  /** `{{product.code}}`. What is inserted and what the dialog shows in mono. */
  token: string;
  /** What a person calls the field. Never the raw path. */
  label: string;
  group: MergeFieldGroup;
  /** The picker shows the label alone (a combo part's token carries an id nobody should read). */
  hideToken?: boolean;
}

/** One key of the spec registry, as `GET /dealer-kit/spec-keys` answers it. */
export interface SpecKeyOption {
  key: string;
  label: string;
  unit?: string | null;
}

/**
 * A token, with whitespace tolerated inside the braces.
 *
 * Built fresh on every call rather than held as a module constant: a global
 * regex carries `lastIndex` between calls, and a shared one would skip the
 * first token of every other render.
 */
function tokenPattern(): RegExp {
  return /\{\{\s*([A-Za-z0-9_.]+)\s*\}\}/g;
}

/**
 * The paths that are just a slot binding under another name.
 *
 * One table, so a token and the equivalent slot-bound layer can never resolve
 * differently, and so a new slot reaches merge fields by being added here alone.
 */
const PATH_SLOTS: Record<string, Exclude<SlotBinding, null>> = {
  'product.code': 'code',
  'product.name': 'name',
  'product.dimensions': 'dimensions',
  'product.spec_lines': 'spec_lines',
  'product.price_tag_description': 'price_tag_description',
  'product.list_price': 'list_price',
  'product.sell_price': 'sell_price',
  'product.included_accessories': 'included_accessories',
  'set.code': 'code',
  'set.name': 'name',
  'set.members': 'set_members',
};

/**
 * O1: the fields a `{{slot.*}}` token may read, each one a `product.<field>` path above, so a
 * position token and a position-bound layer resolve through the same code.
 *
 * `kinds` limits a field to the positions that have it. PRICETAG-PICK-SELLPRICE: `sell_price` is
 * the combo's own "Sell price if picked" for one choice (`combo.choices[].options[].sell_price`),
 * so only a choice-group pick has one; it is read by `pickSellPrice`, not `product.sell_price`
 * (that is the part's promo offer, a different number).
 */
const SLOT_TOKEN_FIELDS: { field: string; label: string; kinds?: SubjectSlot['kind'][] }[] = [
  { field: 'code', label: 'code' },
  { field: 'name', label: 'name' },
  { field: 'list_price', label: 'list price' },
  { field: 'price_tag_description', label: 'price tag description' },
  { field: 'sell_price', label: 'sell price (if picked)', kinds: ['pick'] },
];

function slotFieldAllowed(slot: SubjectSlot, field: string): boolean {
  const entry = SLOT_TOKEN_FIELDS.find((f) => f.field === field);
  return Boolean(entry) && (!entry!.kinds || entry!.kinds.includes(slot.kind));
}

/** The combo's sell price for the pick at this position, bare like other tag prices; empty
 *  (never `RM 0`) when the combo leaves it blank or the position has no pick. Matched by
 *  product, not index: a real line places only the chosen option. */
function pickSellPrice(data: TagBindingData, slots: TagSlots, slot: Extract<SubjectSlot, { kind: 'pick' }>): string {
  const group = slots.groups[slot.group];
  const pick = group?.picks[slot.index];
  if (!pick) return '';
  const choices = comboOf(data)?.choices ?? [];
  const options = (choices.find((choice) => choice.role === group.role) ?? choices[slot.group])?.options ?? [];
  const option =
    options.find((o) => pick.product_id && o.product_id === pick.product_id) ??
    options.find((o) => o.code === pick.code);
  return option?.sell_price == null ? '' : formatTagPrice(Number(option.sell_price), false);
}

/** The token path for a position and field, numbered from 1 like the UI labels. */
export function slotTokenPath(slot: SubjectSlot, field: string): string {
  switch (slot.kind) {
    case 'main':
      return `slot.main.${field}`;
    case 'fixed':
      return `slot.fixed.${slot.index + 1}.${field}`;
    case 'pick':
      return `slot.pick.${slot.group + 1}.${slot.index + 1}.${field}`;
    case 'upgrade':
      return `slot.upgrade.${slot.index + 1}.${field}`;
    case 'variants':
      // "All variants" reads the main product for any field (only its icons differ).
      return `slot.main.${field}`;
  }
}

/** Read `slot.<kind>.<numbers>.<field>` back into a 0-based position, or null when malformed. */
function parseSlotToken(path: string): { slot: SubjectSlot; field: string } | null {
  const [head, kind, ...rest] = path.split('.');
  if (head !== 'slot') return null;
  const field = rest.pop();
  const numbers = rest.map((n) => (/^[1-9][0-9]*$/.test(n) ? Number(n) - 1 : NaN));
  if (!field || numbers.some(Number.isNaN)) return null;
  if (kind === 'main' && numbers.length === 0) return { slot: { kind: 'main' }, field };
  if (kind === 'fixed' && numbers.length === 1) return { slot: { kind: 'fixed', index: numbers[0] }, field };
  if (kind === 'upgrade' && numbers.length === 1) return { slot: { kind: 'upgrade', index: numbers[0] }, field };
  if (kind === 'pick' && numbers.length === 2) {
    return { slot: { kind: 'pick', group: numbers[0], index: numbers[1] }, field };
  }
  return null;
}

/** The groups a price tag template offers in Insert field (the spec sheet's own are for its templates). */
export const PRICE_TAG_FIELD_GROUPS: MergeFieldGroup[] = ['Product', 'Specs', 'Set', 'Line', 'Combo', 'Combo positions'];

/** How each fixed path is named in the dialog. */
const FIELD_LABELS: { path: string; label: string; group: MergeFieldGroup }[] = [
  { path: 'product.code', label: 'Code', group: 'Product' },
  { path: 'product.name', label: 'Name', group: 'Product' },
  { path: 'product.dimensions', label: 'Dimensions', group: 'Product' },
  { path: 'product.spec_lines', label: 'Spec lines', group: 'Product' },
  { path: 'product.price_tag_description', label: 'Price tag description', group: 'Product' },
  { path: 'product.description', label: 'Description', group: 'Product' },
  { path: 'product.spec_sheet_description', label: 'Spec sheet description', group: 'Product' },
  { path: 'product.list_price', label: 'List price', group: 'Product' },
  { path: 'product.sell_price', label: 'Sell price', group: 'Product' },
  { path: 'product.currency', label: 'Currency', group: 'Product' },
  { path: 'product.included_accessories', label: 'Accessories', group: 'Product' },
  { path: 'set.code', label: 'Set code', group: 'Set' },
  { path: 'set.name', label: 'Set name', group: 'Set' },
  { path: 'set.members', label: 'Members', group: 'Set' },
  { path: 'line.quantity', label: 'Quantity', group: 'Line' },
  // D23: the resolved parts on this line's tag, joined with ", " (codes and
  // names as two separate tokens, since a design might want either or both).
  { path: 'line.parts', label: 'Parts (codes)', group: 'Line' },
  { path: 'line.parts_names', label: 'Parts (names)', group: 'Line' },
  { path: 'combo.name', label: 'Combo name', group: 'Combo' },
  { path: 'combo.description', label: 'Combo description', group: 'Combo' },
  { path: 'combo.free_items', label: 'Combo accessories included', group: 'Combo' },
  // COMBO-SETTINGS-UX: every part, printed through the combo's own "Each part prints as" line.
  { path: 'combo.parts', label: 'All parts as a list', group: 'Combo' },
  // PS-SPEC-SHEET: filled on a project spec sheet page only; blank on a price tag.
  { path: 'product.brand', label: 'Brand', group: 'Spec sheet' },
  { path: 'line.area', label: 'Area', group: 'Spec sheet' },
  { path: 'line.comment', label: 'Comment', group: 'Spec sheet' },
  { path: 'line.marker', label: 'Marker', group: 'Spec sheet' },
  { path: 'doc.project_title', label: 'Project title', group: 'Spec sheet' },
  { path: 'doc.ref', label: 'Ref (your ref, else quotation no)', group: 'Spec sheet' },
  { path: 'doc.your_ref', label: 'Your ref', group: 'Spec sheet' },
  { path: 'doc.quotation_no', label: 'Quotation no', group: 'Spec sheet' },
  { path: 'doc.prepared_by', label: 'Prepared by', group: 'Spec sheet' },
  { path: 'doc.prepared_by_phone', label: 'Prepared by phone', group: 'Spec sheet' },
  { path: 'doc.date', label: 'Date', group: 'Spec sheet' },
];

/** PS-SPEC-SHEET: the document fields a spec sheet row carries (`LineTagData.doc`). */
const DOC_FIELDS = new Set([
  'project_title',
  'ref',
  'your_ref',
  'quotation_no',
  'prepared_by',
  'prepared_by_phone',
  'date',
]);

/** Paths only a spec sheet page answers. In the editor, previewed against a plain product,
 *  they show as the token itself so the designer can see what will fill the spot. */
function isSpecSheetPath(path: string): boolean {
  return (
    path.startsWith('doc.') ||
    path === 'line.area' ||
    path === 'line.comment' ||
    path === 'line.marker' ||
    path === 'product.brand'
  );
}

/** The specs the bound thing carries. A set has none of its own (D58).
 *  D7: `layer`'s own subject wins when the layer has one, same as every
 *  other product-data read - a part's specs, not the parent's. */
function specsOf(data: TagBindingData, layer?: Pick<TagLayer, 'props'>): TagSpecValue[] {
  const subject = layer ? subjectOf(data, layer) : data;
  if (!subject) return [];
  if (subject.kind === 'product') return subject.product.specs ?? [];
  if (subject.kind === 'line') return subject.line.specs ?? [];
  return [];
}

/**
 * `407`, never `407 mm` (D20/AC-S15-1): the unit is the designer's to type,
 * so a composed string like `L{{spec.dim_length}}XW{{spec.dim_width}}mm`
 * does not print a doubled unit. `product.dimensions` (the composed slot
 * string) is unchanged - this is only the bare `{{spec.*}}` token.
 */
function specText(spec: TagSpecValue): string {
  return spec.value;
}

/**
 * What one path resolves to, or null when this data cannot answer it.
 *
 * Null rather than an empty string, because the caller decides what an
 * unanswered token looks like and the two modes decide it differently.
 *
 * D7: `layer`'s own subject applies to `spec.*` and the `product.*`/`set.*`
 * paths in `PATH_SLOTS` - the tokens AC-S4-1 names as subject-aware. The
 * three `line.*` paths read the LINE regardless of any subject: a quantity
 * and a line's own parts list are facts about the line, not about whichever
 * product a layer happens to be pointed at.
 *
 * AC-S4-13: `product.price_tag_description`'s stored text is itself a
 * TEMPLATE now, not plain text - it is rendered once more, against the SAME
 * subject's own data, before it reaches the caller. `String.replace`'s
 * single left-to-right scan already makes this one pass with no recursion:
 * a spec VALUE that happens to contain the literal text `{{product.name}}`
 * is part of the replacement STRING, never rescanned for further tokens.
 * AC-S4-17: that nested render goes through `renderPriceTagDescription`, not
 * a plain `renderMergeFields` call - see that function's own comment.
 */
function resolvePath(
  path: string,
  data: TagBindingData,
  layer?: Pick<TagLayer, 'props'>,
  mode: MergeFieldMode = 'print',
): string | null {
  if (path === 'product.price_tag_description') {
    const subject = subjectOf(data, layer);
    if (!subject) return null;
    const raw = resolveSlotText({ slot_binding: 'price_tag_description', props: layer?.props }, data);
    if (raw == null) return null;
    return renderPriceTagDescription(isRich(raw) ? richPlainText(raw) : raw, subject, mode);
  }

  if (path.startsWith('spec.')) {
    const key = path.slice('spec.'.length);
    const spec = specsOf(data, layer).find((row) => row.key === key);
    return spec ? specText(spec) : null;
  }

  // COMBO-SETTINGS-UX: a per-part field of the combo description, tied to the part's product.
  const partValue = comboPartField(data, path);
  if (partValue !== null) return partValue;

  if (path === 'combo.all_parts') {
    // "All parts (one line each)" before it is inserted: the default line for every part.
    return richPlainText(comboPartsHtml(data, true));
  }

  if (path === 'combo.parts') {
    // A plain layer reads the list as plain lines; a rich one splices it (`product-block`).
    return richPlainText(comboPartsHtml(data));
  }

  if (path === 'combo.name' || path === 'combo.description' || path === 'combo.free_items') {
    // Empty, never the raw token, on a line with no combo or an older payload (AC-4.2).
    const combo = comboOf(data);
    const field = path.slice('combo.'.length) as 'name' | 'description' | 'free_items';
    const value = combo?.[field] ?? '';
    return field === 'description' && isRich(value) ? richPlainText(value) : value;
  }

  if (path.startsWith('doc.')) {
    const field = path.slice('doc.'.length);
    if (!DOC_FIELDS.has(field) || data.kind !== 'line' || !data.line.doc) return null;
    return data.line.doc[field as keyof typeof data.line.doc] ?? '';
  }

  if (path === 'line.area' || path === 'line.comment' || path === 'line.marker') {
    if (data.kind !== 'line' || !data.line.doc) return null;
    const field = path.slice('line.'.length) as 'area' | 'comment' | 'marker';
    return data.line[field] ?? '';
  }

  // The product's plain catalogue description (`products.description`), for the subject this
  // layer reads (a part or position its own, else the line's / product's). A set has none.
  if (path === 'product.description') {
    const subject = subjectOf(data, layer);
    if (subject?.kind === 'product') return subject.product.description ?? '';
    if (subject?.kind === 'line') return subject.line.description ?? '';
    return subject ? '' : null;
  }

  // The spec sheet text: the field, else the plain description (the backend already falls back;
  // this covers a row frozen before it).
  if (path === 'product.spec_sheet_description') {
    const subject = subjectOf(data, layer);
    if (subject?.kind === 'product') {
      return subject.product.spec_sheet_description ?? subject.product.description ?? '';
    }
    if (subject?.kind === 'line') return subject.line.spec_sheet_description ?? subject.line.description ?? '';
    return subject ? '' : null;
  }

  if (path === 'product.brand') {
    const subject = subjectOf(data, layer);
    if (subject?.kind === 'product') return subject.product.brand ?? null;
    if (subject?.kind === 'line') return subject.line.brand ?? null;
    return null;
  }

  if (path === 'line.quantity') {
    return data.kind === 'line' ? String(data.line.quantity) : null;
  }

  if (path === 'line.parts' || path === 'line.parts_names') {
    // D23: null when the binding is not a line at all (the token's
    // unanswered form); an empty string when it is a line with no parts.
    if (data.kind !== 'line') return null;
    const parts = data.line.parts ?? [];
    return parts
      .map((part) => (path === 'line.parts' ? part.code : part.name))
      .join(', ');
  }

  // AC-A5/A6/A7: the SUBJECT's own currency, not a slot binding - a part
  // subject (D7) reads that PART's currency, never the parent's. An older
  // pinned/cached row predating this field falls back to MYR, never an
  // empty string or the raw token.
  if (path === 'product.currency') {
    const subject = subjectOf(data, layer);
    if (!subject) return DEFAULT_TAG_CURRENCY;
    const source =
      subject.kind === 'product'
        ? subject.product
        : subject.kind === 'set'
          ? subject.set
          : subject.line;
    return source.currency ?? DEFAULT_TAG_CURRENCY;
  }

  if (path.startsWith('slot.')) {
    // O1: a position of its own, through the same `subjectOf` position code a bound layer uses.
    // Empty (never the main product, never the token) for a position the line does not have.
    const parsed = parseSlotToken(path);
    if (!parsed || !slotFieldAllowed(parsed.slot, parsed.field)) return '';
    const slots = data.kind === 'line' ? data.line.slots : data.kind === 'product' ? data.product.slots : undefined;
    if (!slots) return '';
    if (parsed.slot.kind === 'pick' && parsed.field === 'sell_price') return pickSellPrice(data, slots, parsed.slot);
    const at = { props: { kind: 'text', subjectSlot: parsed.slot } } as unknown as Pick<TagLayer, 'props'>;
    return resolvePath(`product.${parsed.field}`, data, at, mode) ?? '';
  }

  const slot = PATH_SLOTS[path];
  if (!slot) return null;
  return resolveSlotText({ slot_binding: slot, props: layer?.props }, data);
}

/** Whether any `{{token}}` appears in this text. */
export function hasMergeField(text: string | null | undefined): boolean {
  return Boolean(text) && tokenPattern().test(text as string);
}

/**
 * Whether `text` holds at least one `{{product.*}}` or `{{spec.*}}` token -
 * the only ones a subject picker can affect (D7/AC-S4-1). A text layer
 * reading only `{{line.*}}`/`{{set.*}}` tokens is about the LINE, not a
 * specific product on it, and gets no picker.
 */
export function hasSubjectAwareToken(text: string | null | undefined): boolean {
  if (!text) return false;
  for (const match of text.matchAll(tokenPattern())) {
    const path = match[1];
    if (path.startsWith('product.') || path.startsWith('spec.')) return true;
  }
  return false;
}

/**
 * The one `{{path}}` this text is, if the trimmed text is EXACTLY one token
 * and nothing else - `null` for mixed text ("Code {{product.code}}"), plain
 * text, or no text at all.
 *
 * What this exists for (S3): the inline editor opens on `props.text` verbatim
 * for an unbound layer, so a layer whose whole content is `{{product.code}}`
 * showed the raw token rather than the code it resolves to on the canvas. A
 * layer is only a candidate for showing the RESOLVED value when it is a sole
 * token - mixed text still opens raw, exactly as before, because there is no
 * single value to show in its place.
 */
export function soleMergeField(text: string | null | undefined): string | null {
  if (!text) return null;
  const trimmed = text.trim();
  const match = trimmed.match(/^\{\{\s*([A-Za-z0-9_.]+)\s*\}\}$/);
  return match ? trimmed : null;
}

/**
 * Replace every `{{path}}` in `text` with what the bound data says.
 *
 * Called by `layerText` for the canvas and by the print page for the PDF, so
 * the proof a salesperson approves and the sheet that reaches the printer say
 * the same words.
 */
export function renderMergeFields(
  text: string,
  data: TagBindingData | null | undefined,
  mode: MergeFieldMode,
  layer?: Pick<TagLayer, 'props'>,
): string {
  if (!text) return text;

  return text.replace(tokenPattern(), (whole, path: string) => {
    const value = data ? resolvePath(path, data, layer, mode) : null;
    if (value != null) return value;
    // With nothing bound and nothing previewed, the editor shows the token so
    // the designer can see which field will fill this spot. Print never does.
    // A spec sheet field has nothing to preview against a product, so it shows too.
    if (mode === 'editor' && isSpecSheetPath(path)) return whole;
    return mode === 'editor' && !data ? whole : '';
  });
}

/**
 * `product.price_tag_description`'s own nested render (AC-S4-17) - the ONE
 * place a stored template's LINES matter, because a description is typed
 * one sentence per line and a token with nothing to say must not leave a
 * blank line sitting between two real ones on the printed tag.
 *
 * Scoped tightly to this one caller: an ordinary text layer's own
 * `renderMergeFields` call is untouched, so `A\n{{spec.x}}\nB` on a plain
 * layer still renders `A\n\nB` - collapsing THAT would be a surprise on
 * every other tag in the system for one field's sake.
 *
 * A line with no `{{token}}` on it at all is kept exactly as typed, blank or
 * not - that is the author's own line break, not a resolver's decision. A
 * line that carries a token is rendered through the ordinary
 * `renderMergeFields`, then right-trimmed (never left-trimmed - a token
 * resolving empty at the START of a line, e.g. `{{product.name}} in
 * {{spec.material}}` on a name-equals-code product, still opens on the
 * space that follows it, exactly as `renderMergeFields` alone would print
 * it): empty after that means the line said nothing at all and is dropped
 * together with its own newline; anything left is kept trimmed.
 */
export function renderPriceTagDescription(
  template: string,
  data: TagBindingData | null | undefined,
  mode: MergeFieldMode,
  layer?: Pick<TagLayer, 'props'>,
): string {
  if (!template) return template;

  const kept: string[] = [];
  for (const line of template.split('\n')) {
    if (!hasMergeField(line)) {
      kept.push(line);
      continue;
    }
    const rendered = renderMergeFields(line, data, mode, layer).replace(/\s+$/, '');
    if (rendered === '') continue;
    kept.push(rendered);
  }
  return kept.join('\n');
}

/**
 * Every field the Insert field dialog offers, grouped.
 *
 * The spec group comes from the registry rather than from a list in here, so a
 * key added on the master-data screen appears in the dialog with no code
 * change (D58).
 *
 * `groups` narrows the catalog to only the named groups (S11) - a product's
 * own price tag description cannot address a line, a set or a combo part, so
 * the Specifications tab restricts to `['Product', 'Specs']`. Omitted, every
 * group is offered, unchanged from before this parameter existed.
 */
export function mergeFieldCatalog(
  specKeys: SpecKeyOption[],
  groups?: MergeFieldGroup[],
  slots?: TagSlots | null,
): MergeField[] {
  const fixed = FIELD_LABELS.map(({ path, label, group }) => ({
    path,
    token: `{{${path}}}`,
    label,
    group,
  }));

  const specs: MergeField[] = specKeys.map((key) => ({
    path: `spec.${key.key}`,
    token: `{{spec.${key.key}}}`,
    label: key.unit ? `${key.label} (${key.unit})` : key.label,
    group: 'Specs' as const,
  }));

  // O1: the previewed combo's own positions with their codes, else the generic counts.
  const positions: MergeField[] = comboPositions(slots).flatMap(({ slot, code, group }) =>
    SLOT_TOKEN_FIELDS.filter(({ field }) => slotFieldAllowed(slot, field)).map(({ field, label }) => {
      const path = slotTokenPath(slot, field);
      const known = field === 'code' && code ? `: ${code}` : '';
      return {
        path,
        token: `{{${path}}}`,
        label: `${slotLabel(slot, slots)} ${label}${known}`,
        group: 'Combo positions' as const,
      };
    }),
  );

  // Product first, then the specs a designer is most likely hunting for, then
  // the two groups that only apply to some blocks.
  const all = [
    ...fixed.filter((field) => field.group === 'Product'),
    ...specs,
    ...fixed.filter((field) => field.group === 'Set'),
    ...fixed.filter((field) => field.group === 'Line'),
    ...fixed.filter((field) => field.group === 'Combo'),
    ...positions,
    // PS-SPEC-SHEET: offered on spec sheet templates; a price tag editor passes `groups`
    // without it, so it never shows there.
    ...fixed.filter((field) => field.group === 'Spec sheet'),
  ];

  return groups ? all.filter((field) => groups.includes(field.group)) : all;
}