'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { toast } from '@/lib/toast';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { useDeferredAction } from '@/hooks/useDeferredAction';
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
 * Locations has THREE readings, and they are not interchangeable: a list of locations,
 * `null` = every active warehouse, and `[]` = no stock at all. The picker itself can
 * only ever hand back a list, so removing the last chip means `[]` and the "All
 * locations" button is the way back to `null`. The placeholder names which of the two
 * empty readings is in force, because a card that draws them the same way shows the
 * strictest policy as the loosest one - and Save writes what it drew.
 *
 * "Hide zero-quantity locations" sits with Locations because that is what it edits:
 * the locations holding none of the product drop out of the answer. It is part of
 * the same wholesale Save, so it is drafted, dirty-tracked and re-seeded with the
 * other two fields rather than written on toggle.
 */

export interface StockVisibilitySectionProps {
  scope: StockVisibilityScope;
  /** Heading above the fields. Pass null where the surrounding card already titles it. */
  heading?: string | null;
  className?: string;
}

type Draft = {
  mode: StockVisibilityMode;
  warehouseIds: string[] | null;
  hideZeroLocations: boolean;
};

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

/** null (every location) is a different value from [] (none), never just "empty". */
function sameIds(a: string[] | null, b: string[] | null): boolean {
  if (a === null || b === null) return a === b;
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
  const { save } = useStockVisibilityMutations(scope);
  const dealerPool = useDealerPoolWarehouses();
  const searchWarehouses = useStockVisibilityWarehouseSearch();

  const [draft, setDraft] = useState<Draft>({
    mode: 'detailed',
    warehouseIds: null,
    hideZeroLocations: false,
  });
  const [warehouseCache, setWarehouseCache] = useState<
    Record<string, StockVisibilityWarehouse>
  >({});
  // Remove asks nothing (D7): the countdown takes the button's place and Cancel
  // is the way back. The scope IS the record here, so it is parked against the
  // contact id or the access-type code, and the kind travels in the payload
  // because the two are different columns rather than different ids.
  const removal = useDeferredAction({
    actionKey: 'stock_visibility_policy.remove',
    entityType: 'stock_visibility_policy',
    entityId:
      scope.kind === 'contact'
        ? scope.contactId
        : scope.kind === 'access_type'
          ? scope.accessTypeCode
          : undefined,
    verb: 'Removing',
    subject: scope.kind === 'contact' ? 'this override' : 'this policy',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Stock visibility removed',
    payload: { scope_kind: scope.kind },
    invalidateKeys: [stockVisibilityScopeKey(scope)],
  });
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
    const warehouseIds = effective.warehouses ? effective.warehouses.map((w) => w.id) : null;
    const signature = JSON.stringify([
      effective.mode,
      warehouseIds === null ? null : [...warehouseIds].sort(),
      effective.hide_zero_locations,
    ]);
    if (syncedRef.current === signature) return;
    syncedRef.current = signature;
    cacheWarehouses(effective.warehouses ?? []);
    setDraft({
      mode: effective.mode,
      warehouseIds,
      hideZeroLocations: !!effective.hide_zero_locations,
    });
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
      (draft.warehouseIds ?? []).map((id) => {
        const warehouse = warehouseCache[id];
        return warehouse ? toOption(warehouse) : { value: id, label: 'Unknown location' };
      }),
    [draft.warehouseIds, warehouseCache],
  );

  const baseline = data?.effective;
  const isDirty =
    !!baseline &&
    (baseline.mode !== draft.mode ||
      !!baseline.hide_zero_locations !== draft.hideZeroLocations ||
      !sameIds(
        baseline.warehouses ? baseline.warehouses.map((w) => w.id) : null,
        draft.warehouseIds,
      ));

  const hasOwnRow = !!data?.override;
  const canRemove = hasOwnRow && scope.kind !== 'default';
  const isBusy = save.isPending || removal.isPending || dealerPool.isPending;
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
        // An empty pool is not a policy. Writing it would store `[]` - "no stock
        // at all" - from a button the admin pressed expecting three locations.
        if (rows.length === 0) {
          toast.error('No dealer pool locations are configured');
          return;
        }
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

      {/* `items-start`, or the two columns stretch to the taller one: Locations
          carries a picker plus two buttons, and the select trigger is `min-h`,
          so Mode was drawn two to three times a control's height. */}
      <div className="mt-3 grid grid-cols-1 items-start gap-4 md:grid-cols-2">
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
            value={draft.warehouseIds ?? []}
            onChange={(value) => setDraft((prev) => ({ ...prev, warehouseIds: value }))}
            fetchOptions={fetchOptions}
            selectedOptions={selectedOptions}
            placeholder={draft.warehouseIds === null ? 'All locations' : 'No locations'}
            emptyMessage="No locations found"
            disabled={isBusy}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={applyDealerPool}
              disabled={isBusy}
            >
              Dealer pool
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setDraft((prev) => ({ ...prev, warehouseIds: null }))}
              disabled={isBusy || draft.warehouseIds === null}
            >
              All locations
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="stock-visibility-hide-zero"
              checked={draft.hideZeroLocations}
              onCheckedChange={(checked) =>
                setDraft((prev) => ({ ...prev, hideZeroLocations: checked }))
              }
              disabled={isBusy}
            />
            <Label htmlFor="stock-visibility-hide-zero" className="font-normal">
              Hide zero-quantity locations
            </Label>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() =>
            save.mutate({
              // Sent as drafted: null stays null (every active warehouse), [] stays
              // [] (none at all). Collapsing one into the other here is what made
              // the two policies unreachable from this card.
              mode: draft.mode,
              warehouse_ids: draft.warehouseIds,
              hide_zero_locations: draft.hideZeroLocations,
            })
          }
          disabled={!canSave}
        >
          Save stock visibility
        </Button>
        {canRemove
          ? removal.countdown ?? (
              <Button
                type="button"
                variant="outline"
                onClick={() => removal.start()}
                disabled={isBusy}
              >
                {scope.kind === 'contact' ? 'Remove override' : 'Remove policy'}
              </Button>
            )
          : null}
      </div>

    </div>
  );
}

export default StockVisibilitySection;
