/**
 * Per-part fields in the ONE combo description box (COMBO-SETTINGS-UX, owner ruling 10 Nov 20:1x).
 *
 * A field is tied to the PART, never to its position, so reordering parts can never move text onto
 * another part:
 * - `{{part.main.<field>}}`: the combo's main (host) product;
 * - `{{part.<product id, no dashes>.<field>}}`: one part, by its product. A combo lists a product
 *   once, and a combo copied to a colour sibling keeps the same parts, so the reference survives
 *   both; a part removed later prints blank;
 * - `{{group.<hex of the group name>.<field>}}`: a choice group (2+ parts), printing whichever
 *   option the line picked.
 * Only `[A-Za-z0-9_.]` appears in a path, the characters every `{{token}}` reader accepts. The editor
 * shows each token as a chip named by its part (`partChipLabel`), never the raw reference.
 *
 * Resolution is `comboPartField` in `combo-parts.ts`; this file only names and builds tokens.
 */

import type { MergeField } from './merge-fields';

/** What the Insert field Parts group needs of a combo part (a `ProductComboPartRow` fits). */
export interface ComboPartLike {
  product_id: string;
  code: string;
  label?: string | null;
  choice_group: string | null;
  is_upgrade?: boolean;
}

/** The main (host) product as the Parts group names it. */
export interface MainPartLike {
  code: string;
  label?: string | null;
}

/** The path that inserts "All parts (one line each)": replaced by `allPartsHtml` at insert time. */
export const ALL_PARTS_PATH = 'combo.all_parts';

const hex = (text: string) =>
  [...new TextEncoder().encode(text)].map((byte) => byte.toString(16).padStart(2, '0')).join('');

function unhex(value: string): string | null {
  if (!/^(?:[a-f0-9]{2})+$/.test(value)) return null;
  const bytes = new Uint8Array(value.match(/../g)!.map((pair) => parseInt(pair, 16)));
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

/** `part.<32 hex>`: one part, by its product id. */
export const partRef = (productId: string) => `part.${refOf(productId)}`;

/** `group.<hex>`: one choice group, by its name. */
export const groupRef = (role: string) => `group.${hex(role)}`;

/** A path read back: who it is about and which field. Null for anything else. */
export function parsePartPath(
  path: string,
): { kind: 'main' } & { field: string } | { kind: 'part'; ref: string; field: string } | { kind: 'group'; role: string; field: string } | null {
  const parts = path.split('.');
  if (parts.length !== 3) return null;
  const [ns, ref, field] = parts;
  if (ns === 'part' && ref === 'main') return { kind: 'main', field };
  if (ns === 'part' && /^[a-z0-9]+$/.test(ref)) return { kind: 'part', ref, field };
  if (ns === 'group') {
    const role = unhex(ref);
    return role === null ? null : { kind: 'group', role, field };
  }
  return null;
}

/** Product id without dashes, lower case: how a `part.` path names it. */
export const refOf = (productId: string | null | undefined) =>
  (productId ?? '').replace(/[^A-Za-z0-9]/g, '').toLowerCase();

const PART_FIELD_NAMES: { field: string; label: string }[] = [
  { field: 'code', label: 'code' },
  { field: 'label', label: 'label' },
  { field: 'name', label: 'name' },
  { field: 'dimensions_lwh', label: 'dimensions (LxWxH)' },
  { field: 'price_tag_description', label: 'price tag description' },
  { field: 'list_price', label: 'list price' },
];
const GROUP_FIELD_NAMES = [...PART_FIELD_NAMES, { field: 'sell_price', label: 'sell price (if picked)' }];

/** "CABINET - SRTBF11829", or the code alone when the part has no label. */
const nameOf = (code: string, label?: string | null) => (label?.trim() ? `${label.trim()} - ${code}` : code);

/** The groups that are a choice: 2+ non-upgrade parts (a one-part group is a fixed part). */
function choiceGroups(parts: ComboPartLike[]): Set<string> {
  const sizes = new Map<string, number>();
  for (const part of parts) {
    if (!part.is_upgrade && part.choice_group) sizes.set(part.choice_group, (sizes.get(part.choice_group) ?? 0) + 1);
  }
  return new Set([...sizes].filter(([, size]) => size > 1).map(([role]) => role));
}

/** Who the Parts group lists, in order: the main product, then each part, each choice group once. */
function owners(parts: ComboPartLike[], main: MainPartLike): { ref: string; name: string; group: boolean }[] {
  const choices = choiceGroups(parts);
  const out = [{ ref: 'part.main', name: nameOf(main.code, main.label), group: false }];
  const seen = new Set<string>();
  for (const part of parts) {
    if (part.is_upgrade) continue;
    if (part.choice_group && choices.has(part.choice_group)) {
      if (seen.has(part.choice_group)) continue;
      seen.add(part.choice_group);
      out.push({ ref: groupRef(part.choice_group), name: `${part.choice_group} (picked)`, group: true });
    } else {
      out.push({ ref: partRef(part.product_id), name: nameOf(part.code, part.label), group: false });
    }
  }
  return out;
}

/** The Parts group of Insert field: "All parts", then every part's fields, named by the part. */
export function partFieldCatalog(parts: ComboPartLike[], main: MainPartLike): MergeField[] {
  const all: MergeField = {
    path: ALL_PARTS_PATH,
    token: `{{${ALL_PARTS_PATH}}}`,
    label: 'All parts (one line each)',
    group: 'Parts',
    hideToken: true,
  };
  return [
    all,
    ...owners(parts, main).flatMap(({ ref, name, group }) =>
      (group ? GROUP_FIELD_NAMES : PART_FIELD_NAMES).map(({ field, label }) => ({
        path: `${ref}.${field}`,
        token: `{{${ref}.${field}}}`,
        label: `${name}: ${label}`,
        group: 'Parts' as const,
        hideToken: true,
      })),
    ),
  ];
}

/**
 * "All parts (one line each)": one editable line per part, bold "code (label)" then its dimensions,
 * the default part line as separate per-part fields. A part with no label gets its code alone, so no
 * "( )" prints. Parts added to the combo later are not added here.
 */
export function allPartsHtml(parts: ComboPartLike[], main: MainPartLike): string {
  const labelled = new Map<string, boolean>([['part.main', !!main.label?.trim()]]);
  for (const part of parts) labelled.set(partRef(part.product_id), !!part.label?.trim());
  return owners(parts, main)
    .map(({ ref }) => {
      const head = labelled.get(ref) ? `{{${ref}.code}} ({{${ref}.label}})` : `{{${ref}.code}}`;
      return `<p><strong>${head}</strong></p><p>{{${ref}.dimensions_lwh}}</p>`;
    })
    .join('');
}

/** A chip's name for a part path ("BASIN - SRTWB2380: code"), null for any other path. */
export function partChipLabel(path: string, parts: ComboPartLike[], main: MainPartLike): string | null {
  const parsed = parsePartPath(path);
  if (!parsed) return null;
  const fieldName =
    GROUP_FIELD_NAMES.find((entry) => entry.field === parsed.field)?.label ?? parsed.field;
  if (parsed.kind === 'main') return `${nameOf(main.code, main.label)}: ${fieldName}`;
  if (parsed.kind === 'part') {
    const part = parts.find((p) => refOf(p.product_id) === parsed.ref);
    return part ? `${nameOf(part.code, part.label)}: ${fieldName}` : `Removed part: ${fieldName}`;
  }
  return choiceGroups(parts).has(parsed.role)
    ? `${parsed.role} (picked): ${fieldName}`
    : `Removed group "${parsed.role}": ${fieldName}`;
}
