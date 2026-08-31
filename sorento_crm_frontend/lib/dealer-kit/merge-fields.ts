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

import { resolveSlotText } from './product-block';
import type { SlotBinding, TagBindingData, TagSpecValue } from './tag-template-types';

/**
 * `editor` draws an unresolvable token as itself so the designer can see what
 * will fill; `print` draws nothing, because a customer must never read
 * `{{spec.material}}` off a price tag.
 */
export type MergeFieldMode = 'print' | 'editor';

/** How the Insert field dialog sorts the catalogue into sections. */
export type MergeFieldGroup = 'Product' | 'Specs' | 'Set' | 'Line';

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
  { path: 'product.list_price', label: 'List price', group: 'Product' },
  { path: 'product.sell_price', label: 'Sell price', group: 'Product' },
  { path: 'product.included_accessories', label: 'Accessories', group: 'Product' },
  { path: 'set.code', label: 'Set code', group: 'Set' },
  { path: 'set.name', label: 'Set name', group: 'Set' },
  { path: 'set.members', label: 'Members', group: 'Set' },
  { path: 'line.quantity', label: 'Quantity', group: 'Line' },
];

/** The specs the bound thing carries. A set has none of its own (D58). */
function specsOf(data: TagBindingData): TagSpecValue[] {
  if (data.kind === 'product') return data.product.specs ?? [];
  if (data.kind === 'line') return data.line.specs ?? [];
  return [];
}

/** `407 mm`, or `stainless steel` where the registry records no unit. */
function specText(spec: TagSpecValue): string {
  return spec.unit ? `${spec.value} ${spec.unit}` : spec.value;
}

/**
 * What one path resolves to, or null when this data cannot answer it.
 *
 * Null rather than an empty string, because the caller decides what an
 * unanswered token looks like and the two modes decide it differently.
 */
function resolvePath(path: string, data: TagBindingData): string | null {
  if (path.startsWith('spec.')) {
    const key = path.slice('spec.'.length);
    const spec = specsOf(data).find((row) => row.key === key);
    return spec ? specText(spec) : null;
  }

  if (path === 'line.quantity') {
    return data.kind === 'line' ? String(data.line.quantity) : null;
  }

  const slot = PATH_SLOTS[path];
  if (!slot) return null;
  return resolveSlotText({ slot_binding: slot }, data);
}

/** Whether any `{{token}}` appears in this text. */
export function hasMergeField(text: string | null | undefined): boolean {
  return Boolean(text) && tokenPattern().test(text as string);
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
): string {
  if (!text) return text;

  return text.replace(tokenPattern(), (whole, path: string) => {
    const value = data ? resolvePath(path, data) : null;
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