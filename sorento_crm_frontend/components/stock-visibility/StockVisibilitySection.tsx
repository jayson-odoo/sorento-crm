'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import {
  useDealerPoolWarehouses,
  useStockVisibilityMutations,
  useStockVisibilityQuery,
  useStockVisibilityWarehouseSearch,
} from '@/hooks/useStockVisibility';
import {
  STOCK_VISIBILITY_MODE_LABELS,
  STOCK_VISIBILITY_MODE_ORDER,
  stockVisibilityScopeKey,
  type StockVisibilityMode,
  type StockVisibilityPolicy,
  type StockVisibilityScope,
  type StockVisibilityWarehouse,
} from '@/services/stockVisibilityService';

/**
 * Stock visibility policy card (PLAN-stock-visibility-policy, S1).
 *
 * The same card serves all three tiers - a contact, a contact access type, and the
 * global default - because they hold the same two fields and differ only in which row
 * they write. The tier arrives as `scope`; there is no second copy of this component.
 *
 * What the admin reads first is the policy in force TODAY and where it comes from, so
 * the badge is beside the heading and the two fields are pre-filled with the effective
 * values. On a tier that inherits, pressing Save turns those values into a row of its
 * own; Remove deletes that row and the card falls back to what it inherits.
 *
 * S1 note - empty Locations means every active warehouse (the stored `warehouse_ids` is
 * NULL). The data model also allows an empty list, meaning no stock at all, which the
 * PLAN defers to the pass that retires the `is_allowed_stock` Respond field. Until then
 * the UI has one control and no way to sit between the two readings.
 */

export interface StockVisibilitySectionProps {
  scope: StockVisibilityScope;
  /** Heading above the fields. Pass null where the surrounding card already titles it. */
  heading?: string | null;
  className?: string;
}

type Draft = { mode: StockVisibilityMode; warehouseIds: string[] };

const MODE_OPTIONS: SearchableSelectOption[] = STOCK_VISIBILITY_MODE_ORDER.map((mode) => ({
  value: mode,
  label: STOCK_VISIBILITY_MODE_LABELS[mode],
}));

/** `CODE - name`, so a warehouse is legible and no UUID ever reaches the screen. */
function warehouseLabel(warehouse: StockVisibilityWarehouse): string {
  return warehouse.name ? `${warehouse.code} - ${warehouse.name}` : warehouse.code;
}

function toOption(warehouse: StockVisibilityWarehouse): SearchableMultiSelectOption {
  return { value: warehouse.id, label: warehouseLabel(warehouse) };
}

export function sourceBadgeText(policy: StockVisibilityPolicy): string {
  if (policy.source === 'contact') return 'Contact override';
  if (policy.source === 'access_type') {
    return policy.source_label ? `Access type: ${policy.source_label}` : 'Access type';
  }
  return 'Default';
}

function sameIds(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.every((value, index) => value === right[index]);
}

export function StockVisibilitySection({
  scope,
  heading = 'Stock visibility',
  className,
}: StockVisibilitySectionProps) {
  const { data, isLoading, isError, error } = useStockVisibilityQuery(scope);
  const { save, remove } = useStockVisibilityMutations(scope);
  const dealerPool = useDealerPoolWarehouses();
  const searchWarehouses = useStockVisibilityWarehouseSearch();

  const [draft, setDraft] = useState<Draft>({ mode: 'detailed', warehouseIds: [] });
  const [warehouseCache, setWarehouseCache] = useState<
    Record<string, StockVisibilityWarehouse>
  >({});
  const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false);
  /** Last server value the draft was seeded from - see the effect below. */
  const syncedRef = useRef<string | null>(null);

  const cacheWarehouses = useCallback((rows: StockVisibilityWarehouse[]) => {
    if (rows.length === 0) return;
    setWarehouseCache((prev) => {
      const next = { ...prev };
      for (const row of rows) next[row.id] = row;
      return next;
    });
  }, []);

  // The card always opens on the policy in force, whichever tier it came from. Server
  // data is the only writer of the draft, so a save or a remove re-seeds it.
  //
  // Keyed on the CONTENT rather than the response object: react-query hands back a new
  // object on every background refetch, and re-seeding on that would throw away a
  // half-made edit the moment the window regained focus.
  useEffect(() => {
    if (!data) return;
    const effective = data.effective;
    const warehouseIds = (effective.warehouses ?? []).map((w) => w.id);
    const signature = JSON.stringify([effective.mode, [...warehouseIds].sort()]);
    if (syncedRef.current === signature) return;
    syncedRef.current = signature;
    cacheWarehouses(effective.warehouses ?? []);
    setDraft({ mode: effective.mode, warehouseIds });
  }, [data, cacheWarehouses]);

  const fetchOptions = useCallback(
    async (query: string) => {
      const rows = await searchWarehouses(query);
      cacheWarehouses(rows);
      return rows.map(toOption);
    },
    [searchWarehouses, cacheWarehouses],
  );

  const selectedOptions = useMemo(
    () =>
      draft.warehouseIds.map((id) => {
        const warehouse = warehouseCache[id];
        return warehouse ? toOption(warehouse) : { value: id, label: 'Unknown location' };
      }),
    [draft.warehouseIds, warehouseCache],
  );

  const baseline = data?.effective;
  const isDirty =
    !!baseline &&
    (baseline.mode !== draft.mode ||
      !sameIds((baseline.warehouses ?? []).map((w) => w.id), draft.warehouseIds));

  const hasOwnRow = !!data?.override;
  const canRemove = hasOwnRow && scope.kind !== 'default';
  const isBusy = save.isPending || remove.isPending || dealerPool.isPending;
  // An inheriting tier has nothing of its own yet, so Save is the act of creating the
  // row - offered even when the values still match what is inherited.
  const canSave = !!data && !isBusy && (isDirty || !hasOwnRow);

  if (isLoading) {
    return (
      <div className={className}>
        <Skeleton className="h-5 w-40" />
        <Skeleton className="mt-3 h-9 w-full" />
        <Skeleton className="mt-3 h-9 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={className}>
        <p className="text-sm text-destructive">
          {error?.message || 'Stock visibility could not be loaded. Reload the page to try again.'}
        </p>
      </div>
    );
  }

  function applyDealerPool() {
    dealerPool.mutate(undefined, {
      onSuccess: (rows) => {
        cacheWarehouses(rows);
        setDraft((prev) => ({ ...prev, warehouseIds: rows.map((row) => row.id) }));
      },
    });
  }

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {heading ? <p className="text-sm text-muted-foreground">{heading}</p> : <span />}
        <Badge
          variant={data.effective.source === 'default' ? 'secondary' : 'primary'}
          className="font-normal"
        >
          {sourceBadgeText(data.effective)}
        </Badge>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="stock-visibility-mode">Mode</Label>
          <SearchableSelect
            id="stock-visibility-mode"
            value={draft.mode}
            onChange={(value) =>
              setDraft((prev) => ({ ...prev, mode: value as StockVisibilityMode }))
            }
            options={MODE_OPTIONS}
            placeholder="Select mode"
            disabled={isBusy}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="stock-visibility-warehouses">Locations</Label>
          <SearchableMultiSelect
            id="stock-visibility-warehouses"
            value={draft.warehouseIds}
            onChange={(value) => setDraft((prev) => ({ ...prev, warehouseIds: value }))}
            fetchOptions={fetchOptions}
            selectedOptions={selectedOptions}
            placeholder="All locations"
            emptyMessage="No locations found"
            disabled={isBusy}
          />
          <div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={applyDealerPool}
              disabled={isBusy}
            >
              Dealer pool
            </Button>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() =>
            save.mutate({
              mode: draft.mode,
              // Empty means every active warehouse, which the API stores as NULL.
              warehouse_ids: draft.warehouseIds.length > 0 ? draft.warehouseIds : null,
            })
          }
          disabled={!canSave}
        >
          Save
        </Button>
        {canRemove ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => setConfirmRemoveOpen(true)}
            disabled={isBusy}
          >
            {scope.kind === 'contact' ? 'Remove override' : 'Remove policy'}
          </Button>
        ) : null}
      </div>

      <ConfirmDeleteDialog
        open={confirmRemoveOpen}
        onOpenChange={setConfirmRemoveOpen}
        title={scope.kind === 'contact' ? 'Remove override' : 'Remove policy'}
        description={
          scope.kind === 'contact'
            ? 'This contact will fall back to the policy from its access type, or the default.'
            : 'Contacts with this access type will fall back to the default policy.'
        }
        successMessage="Stock visibility removed"
        onDelete={async () => {
          await remove.mutateAsync();
        }}
        queryKeysToInvalidate={[stockVisibilityScopeKey(scope)]}
      />
    </div>
  );
}

export default StockVisibilitySection;
