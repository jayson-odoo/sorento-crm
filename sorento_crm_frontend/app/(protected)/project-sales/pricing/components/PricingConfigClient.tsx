'use client';

import * as React from 'react';
import { Boxes, Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  usePriceFloorMutations,
  usePriceFloors,
  useProjectSeries,
  useSeriesMutations,
} from '../../_shared/hooks/useProjects';
import type { PriceFloorRule, ProjectSeries } from '../../_shared/types/project.types';
import { PriceFloorDialog } from './PriceFloorDialog';
import { SeriesDialog } from './SeriesDialog';

const LEVEL_LABELS: Record<string, string> = {
  product: 'Product',
  category: 'Category',
  system: 'Company default',
};

/**
 * The two policies that decide whether a quoted line raises an alert.
 *
 * They live on one screen because they answer the same question from two sides: the
 * SERIES says what we are supposed to be selling on this scope, and the FLOOR says how
 * cheap it is allowed to go. Splitting them would hide that a scope can be perfectly
 * on-series and still under-priced.
 *
 * Neither is retroactive. Both are copied onto a line when it is priced (AC-E7), so
 * editing a policy here never rewrites a quotation the customer already holds.
 */
export function PricingConfigClient() {
  const series = useProjectSeries(true);
  const floors = usePriceFloors();
  const seriesMutations = useSeriesMutations();
  const floorMutations = usePriceFloorMutations();

  const [seriesDialog, setSeriesDialog] = React.useState<{
    series: ProjectSeries | null;
  } | null>(null);
  const [floorDialog, setFloorDialog] = React.useState<{
    rule: PriceFloorRule | null;
  } | null>(null);
  const [deletingSeries, setDeletingSeries] = React.useState<ProjectSeries | null>(null);
  const [deletingFloor, setDeletingFloor] = React.useState<PriceFloorRule | null>(null);

  const seriesRows = React.useMemo(() => series.data ?? [], [series.data]);
  const floorRows = React.useMemo(() => floors.data ?? [], [floors.data]);

  return (
    <div className="space-y-5">
      <header className="min-w-0">
        <h1 className="text-xl font-semibold">Pricing policy</h1>
        <p className="text-sm text-muted-foreground">
          What each scope is supposed to be quoted from, and how low its price may go.
        </p>
      </header>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-sm">Series</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              A series is the set of categories a scope is meant to be quoted from.
              Nominating a parent category covers everything under it.
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setSeriesDialog({ series: null })}
          >
            <Plus className="size-4" aria-hidden />
            Add series
          </Button>
        </CardHeader>
        <CardContent>
          {series.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : seriesRows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-8 text-center">
              <h3 className="text-sm font-semibold">No series yet</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                Without one, a quotation cannot say what counts as standard, and no line
                is ever flagged as off-series.
              </p>
              <Button
                type="button"
                className="mt-3"
                onClick={() => setSeriesDialog({ series: null })}
              >
                <Plus className="size-4" aria-hidden />
                Add the first series
              </Button>
            </div>
          ) : (
            <ul className="space-y-1.5">
              {seriesRows.map((row) => (
                <li
                  key={row.id}
                  className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2 sm:flex-row sm:items-center"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="truncate text-sm font-medium" title={row.name}>
                        {row.name}
                      </span>
                      {row.brand_name && (
                        <Badge variant="secondary" className="text-[11px]">
                          {row.brand_name}
                        </Badge>
                      )}
                      {!row.is_active && (
                        <Badge variant="outline" className="text-[11px]">
                          Inactive
                        </Badge>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Boxes className="size-3" aria-hidden />
                        {`${row.category_ids.length} nominated, ${row.covered_category_count} covered`}
                      </span>
                      {row.quotation_count > 0 && (
                        <span>
                          {`Used by ${row.quotation_count} quotation${row.quotation_count === 1 ? '' : 's'}`}
                        </span>
                      )}
                      {row.category_names.length > 0 && (
                        <span
                          className="max-w-md truncate"
                          title={row.category_names.join(', ')}
                        >
                          {row.category_names.join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      onClick={() => setSeriesDialog({ series: row })}
                      aria-label={`Edit ${row.name}`}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeletingSeries(row)}
                      aria-label={`Delete ${row.name}`}
                    >
                      <Trash2 className="size-3.5 text-destructive" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-sm">Price floors</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Listed in the order they take effect: a product rule beats its category, a
              category beats its parent, and the company default is the last word.
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setFloorDialog({ rule: null })}
          >
            <Plus className="size-4" aria-hidden />
            Add floor
          </Button>
        </CardHeader>
        <CardContent>
          {floors.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : floorRows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-8 text-center">
              <h3 className="text-sm font-semibold">No floors set</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                Every price is accepted without an alert until at least one floor exists.
                A company default is the usual place to start.
              </p>
              <Button
                type="button"
                className="mt-3"
                onClick={() => setFloorDialog({ rule: null })}
              >
                <Plus className="size-4" aria-hidden />
                Set the first floor
              </Button>
            </div>
          ) : (
            <ul className="space-y-1.5">
              {floorRows.map((rule) => (
                <li
                  key={rule.id}
                  className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2 sm:flex-row sm:items-center"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="secondary" className="text-[11px]">
                        {LEVEL_LABELS[rule.level] ?? rule.level}
                      </Badge>
                      <span className="truncate text-sm font-medium">
                        {rule.product_code ??
                          rule.category_name ??
                          'Everything without a more specific rule'}
                      </span>
                      {!rule.is_active && (
                        <Badge variant="outline" className="text-[11px]">
                          Inactive
                        </Badge>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {describeFloorRule(rule)}
                      {rule.notes ? ` - ${rule.notes}` : ''}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      onClick={() => setFloorDialog({ rule })}
                      aria-label="Edit floor"
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeletingFloor(rule)}
                      aria-label="Delete floor"
                    >
                      <Trash2 className="size-3.5 text-destructive" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {seriesDialog && (
        <SeriesDialog
          series={seriesDialog.series}
          onDone={() => setSeriesDialog(null)}
        />
      )}

      {floorDialog && (
        <PriceFloorDialog rule={floorDialog.rule} onDone={() => setFloorDialog(null)} />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deletingSeries)}
        onOpenChange={(next) => !next && setDeletingSeries(null)}
        title="Confirm delete"
        description={
          deletingSeries
            ? `Delete the series "${deletingSeries.name}"? This action cannot be undone. A series still used by a quotation cannot be deleted, so deactivate it instead.`
            : ''
        }
        onDelete={async () => {
          if (!deletingSeries) return;
          await seriesMutations.remove.mutateAsync(deletingSeries.id);
        }}
        onSuccess={() => setDeletingSeries(null)}
        successMessage="Series deleted"
      />

      <ConfirmDeleteDialog
        open={Boolean(deletingFloor)}
        onOpenChange={(next) => !next && setDeletingFloor(null)}
        title="Confirm delete"
        description={
          deletingFloor
            ? `Delete the ${(LEVEL_LABELS[deletingFloor.level] ?? deletingFloor.level).toLowerCase()} floor for "${deletingFloor.product_code ?? deletingFloor.category_name ?? 'everything else'}"? This action cannot be undone. Lines already priced keep the floor that applied to them.`
            : ''
        }
        onDelete={async () => {
          if (!deletingFloor) return;
          await floorMutations.remove.mutateAsync(deletingFloor.id);
        }}
        onSuccess={() => setDeletingFloor(null)}
        successMessage="Price floor removed"
      />
    </div>
  );
}

function describeFloorRule(rule: PriceFloorRule): string {
  const amount = Number(rule.value);
  const value = Number.isNaN(amount) ? rule.value : String(amount);
  return rule.mode === 'percent'
    ? `At least ${value}% of the list price`
    : `At least RM ${value}, whatever the list price says`;
}
