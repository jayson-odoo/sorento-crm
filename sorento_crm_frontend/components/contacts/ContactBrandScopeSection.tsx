'use client';

import { useMemo, useState } from 'react';

import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { useItemClassSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-item-class-select-query';
import {
  useContactBrandScopeMutations,
  useContactBrandScopeQuery,
} from '@/hooks/useContactBrandScope';
import type { ContactItemClassRef } from '@/services/contactBrandScopeService';

type ClassMap = Record<string, string[]>;

interface Draft {
  brandIds: string[];
  classIds: ClassMap;
}

/** Drops classes of brands no longer chosen and empty lists; sorted so equal scopes compare equal. */
function normalise(brandIds: string[], classIds: ClassMap): ClassMap {
  const out: ClassMap = {};
  for (const brandId of brandIds) {
    const ids = classIds[brandId];
    if (ids && ids.length > 0) out[brandId] = Array.from(new Set(ids)).sort();
  }
  return out;
}

const sameSet = (a: string[], b: string[]) =>
  a.length === b.length && a.every((id) => b.includes(id));

const sameClassMap = (a: ClassMap, b: ClassMap) => {
  const keys = Object.keys(a);
  return (
    keys.length === Object.keys(b).length &&
    keys.every((k) => b[k] !== undefined && sameSet(a[k], b[k]))
  );
};

/** The "<brand> classes" picker; renders nothing when the brand has no class to pick. */
function BrandClassPicker({
  brandId,
  brandName,
  value,
  savedClasses,
  onChange,
  disabled,
}: {
  brandId: string;
  brandName: string;
  value: string[];
  savedClasses: ContactItemClassRef[];
  onChange: (ids: string[]) => void;
  disabled: boolean;
}) {
  const query = useItemClassSelectQuery(brandId);
  const options = useMemo(() => {
    const fromSelect = (query.data ?? []).map((c) => ({
      value: c.id,
      label: c.item_class_name,
    }));
    // A saved class the brand select no longer offers (inactive, or no product carries it) keeps
    // its name, so it can still be seen and removed.
    const extra = savedClasses
      .filter((c) => value.includes(c.id) && !fromSelect.some((o) => o.value === c.id))
      .map((c) => ({ value: c.id, label: c.item_class_name }));
    return [...fromSelect, ...extra];
  }, [query.data, savedClasses, value]);

  if (options.length === 0) return null;

  // An id with no known name must not show as a raw id chip.
  const known = new Set(options.map((o) => o.value));
  const shown = value.filter((id) => known.has(id));

  return (
    <div className="grid gap-2 ml-3.5 border-l-2 pl-3">
      <Label htmlFor={`contact-brand-classes-${brandId}`} className="font-normal text-muted-foreground">
        {brandName} classes
      </Label>
      <SearchableMultiSelect
        id={`contact-brand-classes-${brandId}`}
        value={shown}
        onChange={onChange}
        options={options}
        placeholder="All classes"
        emptyMessage="No classes found"
        clearable
        loadError={query.error}
        onRetry={() => query.refetch()}
        disabled={disabled}
      />
    </div>
  );
}

/**
 * Contact Profile -> Brands. The brands the chatbot and MCP may tell this contact about;
 * empty means every brand. Under each chosen brand that has item classes, an optional picker
 * narrows the contact to those classes (empty = every class). One wholesale Save.
 */
export default function ContactBrandScopeSection({ contactId }: { contactId: string }) {
  const { data, isLoading, isError, error } = useContactBrandScopeQuery(contactId);
  const brandsQuery = useBrandSelectQuery();
  const { save } = useContactBrandScopeMutations(contactId);

  // null = untouched: the pickers show what the server holds until the first edit.
  const [draft, setDraft] = useState<Draft | null>(null);
  const saved = useMemo<Draft>(
    () => ({ brandIds: data?.brand_ids ?? [], classIds: data?.brand_class_ids ?? {} }),
    [data],
  );
  const current = draft ?? saved;
  const options = useMemo(
    () => (brandsQuery.data ?? []).map((b) => ({ value: b.id, label: b.brand_name })),
    [brandsQuery.data],
  );
  // A brand that no longer exists must not show as a raw id chip. Until the brand list loads
  // the saved ids are kept as they are, so Save never silently drops one.
  const known = useMemo(() => new Set(options.map((o) => o.value)), [options]);
  const value = current.brandIds.filter((id) => !brandsQuery.data || known.has(id));

  const payloadClassIds = normalise(value, current.classIds);
  const isDirty =
    draft !== null &&
    (!sameSet(value, saved.brandIds) ||
      !sameClassMap(payloadClassIds, normalise(saved.brandIds, saved.classIds)));

  const brandName = (id: string) =>
    options.find((o) => o.value === id)?.label ??
    data?.brands.find((b) => b.id === id)?.brand_name ??
    '';

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-5 w-24" />
        <Skeleton className="mt-3 h-9 w-full" />
      </div>
    );
  }
  if (isError) {
    return (
      <div>
        <p className="text-sm text-muted-foreground">Brands</p>
        <p className="text-sm text-destructive">{error?.message || 'Could not load the brands.'}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      <Label htmlFor="contact-brand-scope">Brands</Label>
      <SearchableMultiSelect
        id="contact-brand-scope"
        value={value}
        onChange={(brandIds) =>
          setDraft({ brandIds, classIds: normalise(brandIds, current.classIds) })
        }
        options={options}
        placeholder="All brands"
        emptyMessage="No brands found"
        clearable
        loadError={brandsQuery.error}
        onRetry={() => brandsQuery.refetch()}
        disabled={save.isPending}
      />
      {value.map((brandId) => (
        <BrandClassPicker
          key={brandId}
          brandId={brandId}
          brandName={brandName(brandId)}
          value={current.classIds[brandId] ?? []}
          savedClasses={data?.item_classes ?? []}
          onChange={(ids) =>
            setDraft({
              brandIds: value,
              classIds: { ...normalise(value, current.classIds), [brandId]: ids },
            })
          }
          disabled={save.isPending}
        />
      ))}
      <div>
        <Button
          type="button"
          size="sm"
          disabled={!isDirty || save.isPending}
          onClick={() =>
            save.mutate(
              { brandIds: value, brandClassIds: payloadClassIds },
              { onSuccess: () => setDraft(null) },
            )
          }
        >
          Save
        </Button>
      </div>
    </div>
  );
}
