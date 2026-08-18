/**
 * productDiscontinuedScopes.ts - pure mapping helpers (AC-18).
 *
 * Round-trips rows <-> the wire payload, and pins the two semantics rules the
 * plan locks: an all-brands scope subsumes any specific-brand scopes for the
 * same company, and an all-companies scope can only ever mean all brands.
 */
import { describe, it, expect } from 'vitest';
import type { ProductDiscontinuedScope } from '@/app/models/user';
import {
  ALL_BRANDS_LABEL,
  ALL_COMPANIES_LABEL,
  createAllScopeRow,
  describeScopeRow,
  isScopeRowBrandsUnknown,
  rowsToScopePayload,
  scopeRowsHaveUnknownBrands,
  scopesToRows,
  type ScopeRow,
} from './productDiscontinuedScopes';

describe('createAllScopeRow', () => {
  it('is the (null company, no brands) sentinel row', () => {
    const row = createAllScopeRow();
    expect(row.companyId).toBeNull();
    expect(row.brandIds).toEqual([]);
    expect(row.key).toBeTruthy();
  });

  it('gives every row a distinct key', () => {
    const a = createAllScopeRow();
    const b = createAllScopeRow();
    expect(a.key).not.toBe(b.key);
  });
});

describe('scopesToRows', () => {
  it('null/undefined/empty all produce zero rows', () => {
    expect(scopesToRows(null)).toEqual([]);
    expect(scopesToRows(undefined)).toEqual([]);
    expect(scopesToRows([])).toEqual([]);
  });

  it('groups scopes of the same company into one row', () => {
    const scopes: ProductDiscontinuedScope[] = [
      { company_id: 'co-1', company_name: 'Sorento', brand_id: 'br-1', brand_name: 'Mocha' },
      { company_id: 'co-1', company_name: 'Sorento', brand_id: 'br-2', brand_name: 'Nova' },
    ];
    const rows = scopesToRows(scopes);
    expect(rows).toHaveLength(1);
    expect(rows[0].companyId).toBe('co-1');
    expect(rows[0].companyName).toBe('Sorento');
    expect(rows[0].brandIds.sort()).toEqual(['br-1', 'br-2']);
    expect(rows[0].brandLabels).toEqual({ 'br-1': 'Mocha', 'br-2': 'Nova' });
  });

  it('a null-company scope becomes a row with companyId null', () => {
    const rows = scopesToRows([{ company_id: null, brand_id: null }]);
    expect(rows).toHaveLength(1);
    expect(rows[0].companyId).toBeNull();
    expect(rows[0].brandIds).toEqual([]);
  });

  it('an all-brands scope for a company subsumes any specific-brand scopes for it', () => {
    // Ordering matters: the specific-brand row arrives first, then the
    // all-brands row for the same company collapses it back to empty.
    const scopes: ProductDiscontinuedScope[] = [
      { company_id: 'co-1', brand_id: 'br-1', brand_name: 'Mocha' },
      { company_id: 'co-1', brand_id: null },
    ];
    const rows = scopesToRows(scopes);
    expect(rows).toHaveLength(1);
    expect(rows[0].brandIds).toEqual([]);
    expect(rows[0].brandLabels).toEqual({});
  });

  it('two different companies produce two separate rows', () => {
    const scopes: ProductDiscontinuedScope[] = [
      { company_id: 'co-1', company_name: 'Sorento', brand_id: null },
      { company_id: 'co-2', company_name: 'Mocha', brand_id: null },
    ];
    const rows = scopesToRows(scopes);
    expect(rows.map((r) => r.companyId).sort()).toEqual(['co-1', 'co-2']);
  });
});

describe('rowsToScopePayload', () => {
  it('an all-companies row becomes one (null, null) entry', () => {
    const rows: ScopeRow[] = [createAllScopeRow()];
    expect(rowsToScopePayload(rows)).toEqual([{ company_id: null, brand_id: null }]);
  });

  it('all-companies forces brand null even if brandIds were somehow populated', () => {
    const rows: ScopeRow[] = [
      { key: 'k1', companyId: null, brandIds: ['br-1'], brandLabels: {} },
    ];
    expect(rowsToScopePayload(rows)).toEqual([{ company_id: null, brand_id: null }]);
  });

  it('a company row with no brands means all brands (single null-brand entry)', () => {
    const rows: ScopeRow[] = [
      { key: 'k1', companyId: 'co-1', brandIds: [], brandLabels: {} },
    ];
    expect(rowsToScopePayload(rows)).toEqual([{ company_id: 'co-1', brand_id: null }]);
  });

  it('a company row with brands flattens to one entry per brand', () => {
    const rows: ScopeRow[] = [
      {
        key: 'k1',
        companyId: 'co-1',
        brandIds: ['br-1', 'br-2'],
        brandLabels: {},
      },
    ];
    expect(rowsToScopePayload(rows)).toEqual([
      { company_id: 'co-1', brand_id: 'br-1' },
      { company_id: 'co-1', brand_id: 'br-2' },
    ]);
  });

  it('dedupes identical (company, brand) pairs across rows', () => {
    const rows: ScopeRow[] = [
      { key: 'k1', companyId: 'co-1', brandIds: ['br-1'], brandLabels: {} },
      { key: 'k2', companyId: 'co-1', brandIds: ['br-1'], brandLabels: {} },
    ];
    expect(rowsToScopePayload(rows)).toEqual([{ company_id: 'co-1', brand_id: 'br-1' }]);
  });

  it('an empty row list produces an empty payload (silence)', () => {
    expect(rowsToScopePayload([])).toEqual([]);
  });
});

describe('scopesToRows -> rowsToScopePayload round-trip', () => {
  it('preserves a mixed all/specific set through the round trip', () => {
    const scopes: ProductDiscontinuedScope[] = [
      { company_id: null, brand_id: null },
      { company_id: 'co-1', brand_id: 'br-1', brand_name: 'Mocha' },
      { company_id: 'co-1', brand_id: 'br-2', brand_name: 'Nova' },
    ];
    const rows = scopesToRows(scopes);
    const payload = rowsToScopePayload(rows);
    expect(payload.sort((a, b) => (a.brand_id ?? '').localeCompare(b.brand_id ?? ''))).toEqual(
      [
        { company_id: null, brand_id: null },
        { company_id: 'co-1', brand_id: 'br-1' },
        { company_id: 'co-1', brand_id: 'br-2' },
      ].sort((a, b) => (a.brand_id ?? '').localeCompare(b.brand_id ?? '')),
    );
  });
});

describe('a row whose brands never loaded is not all brands', () => {
  const errored = (brandIds: string[]): ScopeRow => ({
    key: 'k1',
    companyId: 'co-1',
    brandIds,
    brandLabels: {},
    brandsLoadError: true,
  });

  it('an errored row with nothing picked is unknown, not all-brands', () => {
    expect(isScopeRowBrandsUnknown(errored([]))).toBe(true);
    expect(scopeRowsHaveUnknownBrands([errored([])])).toBe(true);
  });

  it('a SAVED all-brands row stays savable when its brand list fails to load', () => {
    // It was already saved as "every brand in this company"; a failed lookup does
    // not turn that into an unknown, and blocking it would freeze the whole dialog
    // for an admin without the brands permission.
    const saved: ScopeRow = { ...errored([]), savedAllBrands: true };
    expect(isScopeRowBrandsUnknown(saved)).toBe(false);
    expect(scopeRowsHaveUnknownBrands([saved])).toBe(false);
    expect(rowsToScopePayload([saved])).toEqual([
      { company_id: 'co-1', brand_id: null },
    ]);
  });

  it('an errored row that kept its saved brands is still savable', () => {
    expect(isScopeRowBrandsUnknown(errored(['br-1']))).toBe(false);
    expect(scopeRowsHaveUnknownBrands([errored(['br-1'])])).toBe(false);
  });

  it('an all-companies row is never blocked (it has no brand list to load)', () => {
    const row: ScopeRow = { ...createAllScopeRow(), brandsLoadError: true };
    expect(isScopeRowBrandsUnknown(row)).toBe(false);
  });

  it('the unknown row is dropped from the payload rather than saved as all brands', () => {
    const good: ScopeRow = {
      key: 'k2',
      companyId: 'co-2',
      brandIds: ['br-9'],
      brandLabels: {},
    };
    expect(rowsToScopePayload([errored([]), good])).toEqual([
      { company_id: 'co-2', brand_id: 'br-9' },
    ]);
  });
});

describe('an all-brands company scope survives the round trip as a null brand', () => {
  it('null brand -> empty brandIds -> null brand again', () => {
    const scopes: ProductDiscontinuedScope[] = [
      { company_id: 'co-1', company_name: 'Sorento', brand_id: null },
    ];
    const rows = scopesToRows(scopes);
    expect(rows).toHaveLength(1);
    expect(rows[0].brandIds).toEqual([]);
    // Marked as a saved all-brands decision, so a later brand-load failure cannot
    // mistake it for a pick that was never made.
    expect(rows[0].savedAllBrands).toBe(true);
    expect(describeScopeRow(rows[0])).toBe(`Sorento: ${ALL_BRANDS_LABEL}`);
    expect(rowsToScopePayload(rows)).toEqual([{ company_id: 'co-1', brand_id: null }]);
  });
});

describe('describeScopeRow', () => {
  it('describes an all-companies row', () => {
    expect(describeScopeRow(createAllScopeRow())).toBe(
      `${ALL_COMPANIES_LABEL}: ${ALL_BRANDS_LABEL}`,
    );
  });

  it('describes a company with all brands', () => {
    const row: ScopeRow = {
      key: 'k1',
      companyId: 'co-1',
      companyName: 'Sorento',
      brandIds: [],
      brandLabels: {},
    };
    expect(describeScopeRow(row)).toBe(`Sorento: ${ALL_BRANDS_LABEL}`);
  });

  it('describes a company with named brands, joined by comma', () => {
    const row: ScopeRow = {
      key: 'k1',
      companyId: 'co-1',
      companyName: 'Sorento',
      brandIds: ['br-1', 'br-2'],
      brandLabels: { 'br-1': 'Mocha', 'br-2': 'Nova' },
    };
    expect(describeScopeRow(row)).toBe('Sorento: Mocha, Nova');
  });

  it('falls back to a resolver when the row carries no companyName', () => {
    const row: ScopeRow = {
      key: 'k1',
      companyId: 'co-1',
      brandIds: [],
      brandLabels: {},
    };
    expect(describeScopeRow(row, (id) => (id === 'co-1' ? 'Resolved Co' : undefined))).toBe(
      `Resolved Co: ${ALL_BRANDS_LABEL}`,
    );
  });

  it('falls back to "Unknown company" / "Unknown brand" when nothing resolves', () => {
    const row: ScopeRow = {
      key: 'k1',
      companyId: 'co-1',
      brandIds: ['br-1'],
      brandLabels: {},
    };
    expect(describeScopeRow(row)).toBe('Unknown company: Unknown brand');
  });
});
