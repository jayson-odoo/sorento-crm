'use client';

import { useMemo } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useProductDiscontinuedScopeBrands } from '../../hooks/use-product-discontinued-scope-brands';
import {
  ALL_BRANDS_LABEL,
  ALL_BRANDS_VALUE,
  ALL_COMPANIES_LABEL,
  ALL_COMPANIES_VALUE,
  createAllScopeRow,
  nextScopeRowKey,
  type ScopeRow,
} from '../../lib/productDiscontinuedScopes';

export interface ScopeCompanyOption {
  id: string;
  name: string;
  code?: string;
}

interface ScopeRowFieldsProps {
  row: ScopeRow;
  companies: ScopeCompanyOption[];
  /** Companies already claimed by another row, so one company cannot be split in two. */
  takenCompanyIds: Set<string>;
  allCompaniesTaken: boolean;
  disabled?: boolean;
  onChange: (row: ScopeRow) => void;
  onRemove: () => void;
}

const ScopeRowFields = ({
  row,
  companies,
  takenCompanyIds,
  allCompaniesTaken,
  disabled,
  onChange,
  onRemove,
}: ScopeRowFieldsProps) => {
  const isAllCompanies = row.companyId === null;
  const { data: brands = [], isLoading } = useProductDiscontinuedScopeBrands(
    isAllCompanies ? null : row.companyId,
  );

  const companyOptions = useMemo(
    () => [
      {
        value: ALL_COMPANIES_VALUE,
        label: ALL_COMPANIES_LABEL,
        disabled: allCompaniesTaken && !isAllCompanies,
      },
      ...companies.map((company) => ({
        value: company.id,
        label: company.name,
        searchText: `${company.name} ${company.code ?? ''}`.trim(),
        disabled:
          takenCompanyIds.has(company.id) && company.id !== row.companyId,
      })),
    ],
    [
      companies,
      takenCompanyIds,
      allCompaniesTaken,
      isAllCompanies,
      row.companyId,
    ],
  );

  // Saved brands are merged in so a chip never falls back to rendering its id
  // while the company's brand list is still loading.
  const brandOptions = useMemo(() => {
    const byId = new Map<
      string,
      { value: string; label: string; searchText?: string }
    >();
    for (const brand of brands) {
      byId.set(brand.id, {
        value: brand.id,
        label: brand.brand_name,
        searchText: `${brand.brand_name} ${brand.brand_code}`,
      });
    }
    for (const brandId of row.brandIds) {
      if (!byId.has(brandId)) {
        byId.set(brandId, {
          value: brandId,
          label: row.brandLabels[brandId] || 'Unknown brand',
        });
      }
    }
    return [
      { value: ALL_BRANDS_VALUE, label: ALL_BRANDS_LABEL },
      ...Array.from(byId.values()),
    ];
  }, [brands, row.brandIds, row.brandLabels]);

  const brandValue = row.brandIds.length ? row.brandIds : [ALL_BRANDS_VALUE];

  const handleCompanyChange = (value: string) => {
    const companyId = value === ALL_COMPANIES_VALUE ? null : value;
    const company = companies.find((c) => c.id === companyId);
    // Brands belong to the company that was replaced, so the set resets to all.
    onChange({
      ...row,
      companyId,
      companyName: company?.name ?? null,
      brandIds: [],
      brandLabels: {},
    });
  };

  const handleBrandsChange = (next: string[]) => {
    const hadAllBrands = brandValue.includes(ALL_BRANDS_VALUE);
    const picked = next.filter((value) => value !== ALL_BRANDS_VALUE);
    // Picking "All brands" (or clearing the last brand) collapses back to all.
    const brandIds =
      !hadAllBrands && next.includes(ALL_BRANDS_VALUE) ? [] : picked;
    const brandLabels: Record<string, string> = {};
    for (const brandId of brandIds) {
      const option = brandOptions.find((o) => o.value === brandId);
      if (option) brandLabels[brandId] = option.label;
    }
    onChange({ ...row, brandIds, brandLabels });
  };

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <SearchableSelect
          value={row.companyId ?? ALL_COMPANIES_VALUE}
          onChange={handleCompanyChange}
          options={companyOptions}
          disabled={disabled}
          placeholder="Select a company"
          emptyMessage="No company found."
          triggerClassName="w-full"
        />
      </div>
      <div className="min-w-0 flex-1">
        <SearchableMultiSelect
          value={isAllCompanies ? [ALL_BRANDS_VALUE] : brandValue}
          onChange={handleBrandsChange}
          options={brandOptions}
          disabled={disabled || isAllCompanies}
          placeholder={ALL_BRANDS_LABEL}
          emptyMessage={isLoading ? 'Loading brands...' : 'No brand found.'}
          triggerClassName="w-full"
        />
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onRemove}
        disabled={disabled}
        aria-label="Remove scope"
        title="Remove scope"
      >
        <Trash2 className="size-4" />
      </Button>
    </div>
  );
};

interface ProductDiscontinuedScopeEditorProps {
  rows: ScopeRow[];
  companies: ScopeCompanyOption[];
  disabled?: boolean;
  onChange: (rows: ScopeRow[]) => void;
}

/**
 * Which slice of the catalogue a user is notified about when products are
 * discontinued. One row = one company (or all) plus the brands inside it.
 */
const ProductDiscontinuedScopeEditor = ({
  rows,
  companies,
  disabled,
  onChange,
}: ProductDiscontinuedScopeEditorProps) => {
  const takenCompanyIds = useMemo(
    () =>
      new Set(
        rows
          .map((row) => row.companyId)
          .filter((id): id is string => Boolean(id)),
      ),
    [rows],
  );
  const allCompaniesTaken = rows.some((row) => row.companyId === null);

  // A saved scope can name a company outside the acting admin's own grants. Merge
  // those in from the rows themselves (same trick the brand chips use) or the
  // select renders blank for a value the read view happily shows by name.
  const companyOptions = useMemo(() => {
    const byId = new Map<string, ScopeCompanyOption>();
    for (const company of companies) byId.set(company.id, company);
    for (const row of rows) {
      if (!row.companyId || byId.has(row.companyId)) continue;
      byId.set(row.companyId, {
        id: row.companyId,
        name: row.companyName || 'Unknown company',
      });
    }
    return Array.from(byId.values());
  }, [companies, rows]);

  // With every company claimed and the all-companies row already present there is
  // nothing left for a new row to mean, so Add is closed rather than appending a
  // duplicate all-companies row.
  const hasFreeCompany = companyOptions.some(
    (company) => !takenCompanyIds.has(company.id),
  );
  const canAddRow = !allCompaniesTaken || hasFreeCompany;

  const addRow = () => {
    // A second all-companies row would be a duplicate, so a new row starts on the
    // first company still free.
    const freeCompany = companyOptions.find(
      (company) => !takenCompanyIds.has(company.id),
    );
    if (allCompaniesTaken && !freeCompany) return;
    onChange([
      ...rows,
      allCompaniesTaken
        ? {
            key: nextScopeRowKey(),
            companyId: freeCompany!.id,
            companyName: freeCompany!.name,
            brandIds: [],
            brandLabels: {},
          }
        : createAllScopeRow(),
    ]);
  };

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-medium">Discontinued product scope</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addRow}
          disabled={disabled || !canAddRow}
          title={
            canAddRow ? undefined : 'Every company already has a scope row.'
          }
        >
          <Plus className="size-4" />
          Add scope
        </Button>
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No scope set. This user will not be notified about any discontinued
          product.
        </p>
      ) : (
        <div className="space-y-2">
          {rows.map((row, index) => (
            <ScopeRowFields
              key={row.key}
              row={row}
              companies={companyOptions}
              takenCompanyIds={takenCompanyIds}
              allCompaniesTaken={allCompaniesTaken}
              disabled={disabled}
              onChange={(next) =>
                onChange(
                  rows.map((current, i) => (i === index ? next : current)),
                )
              }
              onRemove={() => onChange(rows.filter((_, i) => i !== index))}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default ProductDiscontinuedScopeEditor;
