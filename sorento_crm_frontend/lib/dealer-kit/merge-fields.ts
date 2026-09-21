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

import { resolveSlotText, subjectOf } from './product-block';
import type {
  SlotBinding,
  TagBindingData,
  TagLayer,
  TagSpecValue,
} from './tag-template-types';

/**
 * `editor` draws an unresolvable token as itself so the designer can see what
 * will fill; `print` draws nothing, because a customer must never read
 * `{{spec.material}}` off a price tag.
 */
export type MergeFieldMode = 'print' | 'editor';

/** How the Insert field dialog sorts the catalogue into sections. */
export type MergeFieldGroup = 'Product' | 'Specs' | 'Set' | 'Line';

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

/** How each fixed path is named in the dialog. */
const FIELD_LABELS: { path: string; label: string; group: MergeFieldGroup }[] = [
  { path: 'product.code', label: 'Code', group: 'Product' },
  { path: 'product.name', label: 'Name', group: 'Product' },
  { path: 'product.dimensions', label: 'Dimensions', group: 'Product' },
  { path: 'product.spec_lines', label: 'Spec lines', group: 'Product' },
  { path: 'product.price_tag_description', label: 'Price tag description', group: 'Product' },
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
];

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
    return renderMergeFields(raw, subject, mode);
  }

  if (path.startsWith('spec.')) {
    const key = path.slice('spec.'.length);
    const spec = specsOf(data, layer).find((row) => row.key === key);
    return spec ? specText(spec) : null;
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
    return mode === 'editor' && !data ? whole : '';
  });
}

/**
 * Every field the Insert field dialog offers, grouped.
 *
 * The spec group comes from the registry rather than from a list in here, so a
 * key added on the master-data screen appears in the dialog with no code
 * change (D58).
 */
export function mergeFieldCatalog(specKeys: SpecKeyOption[]): MergeField[] {
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

  // Product first, then the specs a designer is most likely hunting for, then
  // the two groups that only apply to some blocks.
  return [
    ...fixed.filter((field) => field.group === 'Product'),
    ...specs,
    ...fixed.filter((field) => field.group === 'Set'),
    ...fixed.filter((field) => field.group === 'Line'),
  ];
}