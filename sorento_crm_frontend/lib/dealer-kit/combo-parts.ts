/**
 * `{{combo.parts}}`: every part of a combo as a list (COMBO-SETTINGS-UX rule 3, owner 10 Nov).
 *
 * The combo stores ONE rich line template, "Each part prints as" (`combo.parts_line`), written with
 * `{{part.*}}` fields; this repeats it for the main product, then each fixed part, then the chosen
 * option of each pick-one group (on a request line the slots hold only what was chosen). Upgrades are
 * not parts of the package and are not listed.
 *
 * The answer is rich HTML, so the existing rich renderer (`richBlocksWithFields`) draws it with the
 * line's own bold / colour, the same way it draws a rich description. Two rules for empty fields,
 * so a part with nothing on record does not print noise: brackets left empty go (with the space
 * before them), and a paragraph that held a part field and came out blank is dropped.
 */

import { isRich, richPlainText, toEditorHtml } from './rich-text';
import type { TagBindingData, TagPartData } from './tag-template-types';

/** What a combo with no line of its own prints per part: "SRTBF11829 (CABINET)" in bold, then "L780xW480xH400mm". */
export const DEFAULT_PARTS_LINE =
  '<p><strong>{{part.code}} ({{part.label}})</strong></p><p>{{part.dimensions_lwh}}</p>';

/** The fields the "Insert part field" picker offers, in the order the owner named them. */
export const PART_FIELDS: { path: string; label: string }[] = [
  { path: 'part.code', label: 'Code' },
  { path: 'part.label', label: 'Label' },
  { path: 'part.name', label: 'Name' },
  { path: 'part.price_tag_description', label: 'Price tag description' },
  { path: 'part.dimensions_lwh', label: 'Dimensions (L780xW480xH400mm)' },
  { path: 'part.dimensions', label: 'Dimensions (780 x 480 x 400 mm)' },
];

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
const escapeHtml = (value: string) => value.replace(/[&<>"]/g, (ch) => ESCAPES[ch]);

/** The part's text for one field: plain, one line (a multi-line description is joined with spaces). */
function fieldValue(part: TagPartData, label: string, field: string): string {
  const raw =
    field === 'code'
      ? part.code
      : field === 'label'
        ? label
        : field === 'name'
          ? part.name
          : field === 'price_tag_description'
            ? part.price_tag_description
            : field === 'dimensions_lwh'
              ? part.dimensions_lwh
              : field === 'dimensions'
                ? part.dimensions
                : '';
  const text = isRich(raw) ? richPlainText(raw) : (raw ?? '');
  return (
    text
      // A value is text: braces go, so a label typed as `{{combo.parts}}` can never be read as a
      // field again (it would splice the list into itself without end).
      .replace(/\{\{|\}\}/g, '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .join(' ')
  );
}

/** The main product, the fixed parts, then the chosen option of each group, each with its label. */
function listedParts(data: TagBindingData): { part: TagPartData; label: string }[] {
  const slots = data.kind === 'line' ? data.line.slots : data.kind === 'product' ? data.product.slots : null;
  const combo = data.kind === 'line' ? data.line.combo : data.kind === 'product' ? data.product.combo : null;
  if (!slots || !combo) return [];
  const labels = combo.part_labels ?? {};
  const labelOf = (part: TagPartData) => (part.product_id ? (labels[part.product_id] ?? '') : '');
  return [
    ...(slots.main ? [{ part: slots.main, label: combo.main_label ?? '' }] : []),
    ...slots.fixed.map((part) => ({ part, label: labelOf(part) })),
    ...slots.groups.flatMap((group) => group.picks.map((part) => ({ part, label: labelOf(part) }))),
  ];
}

const PART_TOKEN = /\{\{\s*part\.([A-Za-z0-9_]+)\s*\}\}/g;
/** A part line may not pull the list (or the description that holds it) in again. */
const SELF_TOKEN = /\{\{\s*combo\.(?:parts|description)\s*\}\}/g;
const EMPTY_BRACKETS = /(?:\s|&nbsp;)*\((?:\s|&nbsp;)*\)/g;

/** The whole list as rich HTML, '' when the line has no combo or no parts. */
export function comboPartsHtml(data: TagBindingData | null | undefined): string {
  if (!data) return '';
  const combo = data.kind === 'line' ? data.line.combo : data.kind === 'product' ? data.product.combo : null;
  const listed = listedParts(data);
  if (!combo || listed.length === 0) return '';
  const own = combo.parts_line?.trim() ? combo.parts_line : DEFAULT_PARTS_LINE;
  const template = toEditorHtml(own).replace(SELF_TOKEN, '');
  // One chunk per paragraph, so a paragraph that only held an empty field can be dropped.
  const chunks = template.split(/(?<=<\/p>)/);
  return listed
    .map(({ part, label }) =>
      chunks
        .map((chunk) => {
          const hadField = /\{\{\s*part\./.test(chunk);
          const filled = chunk
            .replace(PART_TOKEN, (_whole, field: string) => escapeHtml(fieldValue(part, label, field)))
            .replace(EMPTY_BRACKETS, '');
          const text = filled.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim();
          return hadField && !text ? '' : filled;
        })
        .join(''),
    )
    .join('');
}
