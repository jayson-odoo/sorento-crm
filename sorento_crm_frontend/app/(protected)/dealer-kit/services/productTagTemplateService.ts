/**
 * Which tag templates a product may print with (PRICETAG-TEMPLATE-PER-PRODUCT).
 *
 *   GET  /api/v1/dealer-kit/products/{id}/tag-templates            -> ProductTagTemplateItem[]
 *   PUT  /api/v1/dealer-kit/products/{id}/tag-templates            { template_ids, default_template_id } -> same
 *   GET|PUT /api/v1/dealer-kit/combos/{id}/tag-templates           same shapes, for a combo (PRICETAG-LPSP)
 *   POST /api/v1/dealer-kit/tag-templates/{id}/assign/preview      filter -> { matched, already_linked }
 *   POST /api/v1/dealer-kit/tag-templates/{id}/assign              filter + { action } -> { changed }
 *
 * The filter is AND across kinds, OR within one; an all-empty filter is refused (422).
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const DK = '/api/v1/dealer-kit';

export interface ProductTagTemplateItem {
  id: string;
  name: string;
  family: string;
  /** False = linked but offered nowhere until it is published again. */
  published: boolean;
  width_mm: number | null;
  height_mm: number | null;
  /** Compat: a default of either kind. */
  is_default?: boolean;
  /** The template's hand-picked price type; null = not set (offered on LP and SP lines). */
  price_type?: 'list' | 'selling' | 'both' | null;
  /** The link preselected on an LP / SP request line; a lone fitting link counts. */
  default_list?: boolean;
  default_selling?: boolean;
}

/** The wire body of a links save. `default_template_id` must be one of `template_ids`. */
export interface TagTemplateLinks {
  template_ids: string[];
  default_template_id: string | null;
}

/**
 * The default to send back on a save: only one the user chose. The server reports a lone link
 * as the default for display, so with fewer than two links nothing was chosen and nothing is sent.
 */
export function explicitDefaultId(rows: ProductTagTemplateItem[]): string | null {
  return rows.length > 1 ? (rows.find((row) => row.is_default)?.id ?? null) : null;
}

export interface TemplateAssignFilter {
  brand_ids: string[];
  category_ids: string[];
  item_class_ids: string[];
  family_codes: string[];
}

export type TemplateAssignAction = 'add' | 'remove';

/** PS-SPEC-SHEET (#2103) keeps spec sheet pages in the same table; never a price tag. */
export function isPriceTagFamily(family: string): boolean {
  return !family.startsWith('spec_');
}

export function isEmptyAssignFilter(filter: TemplateAssignFilter): boolean {
  return (
    filter.brand_ids.length === 0 &&
    filter.category_ids.length === 0 &&
    filter.item_class_ids.length === 0 &&
    filter.family_codes.length === 0
  );
}

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

export async function listProductTagTemplates(productId: string): Promise<ProductTagTemplateItem[]> {
  return unwrap(
    await apiFetch(`${DK}/products/${encodeURIComponent(productId)}/tag-templates`),
    'Failed to load the price tag templates',
  );
}

export async function setProductTagTemplates(
  productId: string,
  links: TagTemplateLinks,
): Promise<ProductTagTemplateItem[]> {
  return unwrap(
    await apiFetch(`${DK}/products/${encodeURIComponent(productId)}/tag-templates`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(links),
    }),
    'Failed to save the price tag templates',
  );
}

export async function listComboTagTemplates(comboId: string): Promise<ProductTagTemplateItem[]> {
  return unwrap(
    await apiFetch(`${DK}/combos/${encodeURIComponent(comboId)}/tag-templates`),
    'Failed to load the price tag templates',
  );
}

export async function setComboTagTemplates(
  comboId: string,
  links: TagTemplateLinks,
): Promise<ProductTagTemplateItem[]> {
  return unwrap(
    await apiFetch(`${DK}/combos/${encodeURIComponent(comboId)}/tag-templates`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(links),
    }),
    'Failed to save the price tag templates',
  );
}

export async function previewTemplateAssignment(
  templateId: string,
  filter: TemplateAssignFilter,
): Promise<{ matched: number; already_linked: number }> {
  return unwrap(
    await apiFetch(`${DK}/tag-templates/${encodeURIComponent(templateId)}/assign/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filter),
    }),
    'Failed to count the matching products',
  );
}

export async function assignTemplate(
  templateId: string,
  filter: TemplateAssignFilter,
  action: TemplateAssignAction,
): Promise<{ changed: number }> {
  return unwrap(
    await apiFetch(`${DK}/tag-templates/${encodeURIComponent(templateId)}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...filter, action }),
    }),
    'Failed to assign the template',
  );
}

/** Model families (`products.family_code`) for the bulk filter. */
export async function listFamilyCodes(query: string): Promise<string[]> {
  const qs = new URLSearchParams();
  if (query.trim()) qs.set('q', query.trim());
  const suffix = qs.toString();
  return unwrap(
    await apiFetch(`${DK}/tag-templates/family-codes${suffix ? `?${suffix}` : ''}`),
    'Failed to load model families',
  );
}
