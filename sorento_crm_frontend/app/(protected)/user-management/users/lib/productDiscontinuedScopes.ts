/**
 * Product-discontinued notification scopes - pure mapping helpers.
 *
 * A scope is one (company, brand) pair on a user:
 *   company_id null = every company, brand_id null = every brand in that company.
 * The editor and the read view both work on ROWS (one company + a set of brands),
 * which is how a person thinks about "my slice of the catalogue"; these helpers are
 * the only place rows and the wire-level scope list are converted into each other.
 */
import type { ProductDiscontinuedScope } from '@/app/models/user';

/** Sentinel option values (never sent to the API - they map to null). */
export const ALL_COMPANIES_VALUE = '__all_companies__';
export const ALL_BRANDS_VALUE = '__all_brands__';

export const ALL_COMPANIES_LABEL = 'All companies';
export const ALL_BRANDS_LABEL = 'All brands';

export interface ScopeRow {
  /** Local-only React key; never sent to the API. */
  key: string;
  /** null = all companies. */
  companyId: string | null;
  /** Name as saved on the scope, so the read view never has to resolve an id. */
  companyName?: string | null;
  /** Empty = all brands in the company. */
  brandIds: string[];
  /** brand id -> brand name, carried from the saved scopes so chips show names. */
  brandLabels: Record<string, string>;
}

let rowSeq = 0;

export function nextScopeRowKey(): string {
  rowSeq += 1;
  return `scope-row-${rowSeq}`;
}

export function createAllScopeRow(): ScopeRow {
  return {
    key: nextScopeRowKey(),
    companyId: null,
    brandIds: [],
    brandLabels: {},
  };
}

/**
 * Group the saved scopes into one row per company. An all-brands scope wins over
 * specific-brand scopes for the same company, because it already covers them.
 */
export function scopesToRows(
  scopes: ProductDiscontinuedScope[] | null | undefined,
): ScopeRow[] {
  const byCompany = new Map<string, ScopeRow>();
  const allBrands = new Set<string>();

  for (const scope of scopes ?? []) {
    const companyKey = scope.company_id ?? ALL_COMPANIES_VALUE;
    let row = byCompany.get(companyKey);
    if (!row) {
      row = {
        key: nextScopeRowKey(),
        companyId: scope.company_id ?? null,
        companyName: scope.company_name ?? null,
        brandIds: [],
        brandLabels: {},
      };
      byCompany.set(companyKey, row);
    }
    if (!row.companyName && scope.company_name)
      row.companyName = scope.company_name;
    if (scope.brand_id) {
      if (!row.brandIds.includes(scope.brand_id))
        row.brandIds.push(scope.brand_id);
      if (scope.brand_name) row.brandLabels[scope.brand_id] = scope.brand_name;
    } else {
      allBrands.add(companyKey);
    }
  }

  for (const companyKey of allBrands) {
    const row = byCompany.get(companyKey);
    if (row) {
      row.brandIds = [];
      row.brandLabels = {};
    }
  }

  return Array.from(byCompany.values());
}

/** Flatten rows back to the wire shape: one entry per (company, brand) pair. */
export function rowsToScopePayload(
  rows: ScopeRow[],
): { company_id: string | null; brand_id: string | null }[] {
  const seen = new Set<string>();
  const payload: { company_id: string | null; brand_id: string | null }[] = [];

  for (const row of rows) {
    // All companies can only ever mean all brands.
    const brandIds =
      row.companyId === null || row.brandIds.length === 0
        ? [null]
        : row.brandIds;
    for (const brandId of brandIds) {
      const dedupeKey = `${row.companyId ?? ''}:${brandId ?? ''}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      payload.push({ company_id: row.companyId, brand_id: brandId });
    }
  }

  return payload;
}

/** Human label for one row, e.g. "Sorento: Mocha, Nova" or "All companies: All brands". */
export function describeScopeRow(
  row: ScopeRow,
  resolveCompanyName?: (companyId: string) => string | undefined,
): string {
  const company =
    row.companyId === null
      ? ALL_COMPANIES_LABEL
      : row.companyName ||
        resolveCompanyName?.(row.companyId) ||
        'Unknown company';
  const brands = row.brandIds.length
    ? row.brandIds
        .map((id) => row.brandLabels[id] || 'Unknown brand')
        .join(', ')
    : ALL_BRANDS_LABEL;
  return `${company}: ${brands}`;
}
