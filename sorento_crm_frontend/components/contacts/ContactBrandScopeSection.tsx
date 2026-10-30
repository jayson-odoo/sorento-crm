'use client';

import { useMemo, useState } from 'react';

import AllowedItemClassesPicker from '@/components/contacts/AllowedItemClassesPicker';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import {
  useContactBrandScopeMutations,
  useContactBrandScopeQuery,
} from '@/hooks/useContactBrandScope';

interface Draft {
  brandIds: string[];
  classCodes: string[];
}

const sameSet = (a: string[], b: string[]) =>
  a.length === b.length && a.every((id) => b.includes(id));

/**
 * Contact Profile -> Brands. The brands the chatbot and MCP may tell this contact about (empty
 * = every brand) and, under them, the allowed item classes (empty = every class), the same
 * picker the tag Access settings Brands row shows. One wholesale Save.
 */
export default function ContactBrandScopeSection({ contactId }: { contactId: string }) {
  const { data, isLoading, isError, error } = useContactBrandScopeQuery(contactId);
  const brandsQuery = useBrandSelectQuery();
  const { save } = useContactBrandScopeMutations(contactId);

  // null = untouched: the pickers show what the server holds until the first edit.
  const [draft, setDraft] = useState<Draft | null>(null);
  const saved = useMemo<Draft>(
    () => ({ brandIds: data?.brand_ids ?? [], classCodes: data?.allowed_item_class_codes ?? [] }),
    [data],
  );
  const current = draft ?? saved;
  const options = useMemo(
    () => (brandsQuery.data ?? []).map((b) => ({ value: b.id, label: b.brand_name })),
    [brandsQuery.data],
  );
  const classOptions = useMemo(
    () => (data?.item_class_options ?? []).map((o) => ({ value: o.code, label: o.name })),
    [data],
  );
  // A brand that no longer exists must not show as a raw id chip. Until the brand list loads
  // the saved ids are kept as they are, so Save never silently drops one.
  const known = useMemo(() => new Set(options.map((o) => o.value)), [options]);
  const value = current.brandIds.filter((id) => !brandsQuery.data || known.has(id));

  const isDirty =
    draft !== null &&
    (!sameSet(value, saved.brandIds) || !sameSet(current.classCodes, saved.classCodes));

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
        onChange={(brandIds) => setDraft({ brandIds, classCodes: current.classCodes })}
        options={options}
        placeholder="All brands"
        emptyMessage="No brands found"
        clearable
        loadError={brandsQuery.error}
        onRetry={() => brandsQuery.refetch()}
        disabled={save.isPending}
      />
      <AllowedItemClassesPicker
        id="contact-item-classes"
        value={current.classCodes}
        onChange={(classCodes) => setDraft({ brandIds: value, classCodes })}
        options={classOptions}
        disabled={save.isPending}
      />
      <div>
        <Button
          type="button"
          size="sm"
          disabled={!isDirty || save.isPending}
          onClick={() =>
            save.mutate(
              { brandIds: value, allowedItemClassCodes: current.classCodes },
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
