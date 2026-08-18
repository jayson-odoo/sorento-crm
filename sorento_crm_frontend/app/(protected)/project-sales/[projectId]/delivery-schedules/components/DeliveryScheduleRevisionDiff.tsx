'use client';

import * as React from 'react';
import { ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { DeliveryScheduleVersion } from '../../../_shared/types/deliverySchedule.types';
import {
  diffScheduleQuantities,
  groupPhasesByArea,
  schedulePhaseDateMoves,
} from '../lib/scheduleTotals';
import type { PhaseDateMove, ScheduleQtyChange } from '../lib/scheduleTotals';
import { formatQty } from '../../components/SalesOrderMoney';

/**
 * Was -> now, against the version this one revises (section 9.1).
 *
 * Dates come straight off this version's own payload (`promoted_delivery_date` is what the
 * project held before it): no extra fetch. Quantities carry no such field, so they need the
 * FULL prior version, which is why this card can render its date moves before `priorVersion`
 * has loaded and its quantity moves only after.
 */
export function DeliveryScheduleRevisionDiff({
  version,
  priorVersion,
  priorLoading,
}: {
  version: DeliveryScheduleVersion;
  priorVersion: DeliveryScheduleVersion | null | undefined;
  priorLoading: boolean;
}) {
  const dateMoves = React.useMemo(
    () => schedulePhaseDateMoves(version.phases),
    [version.phases],
  );

  const qty = React.useMemo(() => {
    if (!priorVersion) return null;
    return diffScheduleQuantities(version, priorVersion);
  }, [version, priorVersion]);

  const rows = React.useMemo(
    () => buildDiffRows(version, dateMoves, qty?.changes ?? []),
    [version, dateMoves, qty],
  );

  const summary = priorLoading
    ? 'Comparing quantities with the previous version…'
    : qty
      ? `${dateMoves.length} phase${dateMoves.length === 1 ? '' : 's'} moved · ` +
        `${qty.changes.length} quantit${qty.changes.length === 1 ? 'y' : 'ies'} changed · ` +
        `${qty.unchangedCount} unchanged`
      : `${dateMoves.length} phase${dateMoves.length === 1 ? '' : 's'} moved. Quantities could ` +
        'not be compared with the previous version.';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Changes since the previous version</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p data-testid="revision-diff-summary" className="text-sm font-medium">
          {summary}
        </p>

        {priorLoading && rows.length === 0 ? (
          <div className="space-y-2" aria-hidden>
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing moved between this version and the one before it.
          </p>
        ) : (
          <ul className="space-y-2">
            {rows.map((row) => (
              <li
                key={row.phaseId}
                className="rounded-lg border border-border px-3 py-2 text-sm"
                data-testid="revision-diff-row"
              >
                <p className="break-words font-medium">
                  {row.area ? `${row.area} · ${row.label}` : row.label}
                </p>
                {row.dateMove && (
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5">
                    <span className="text-muted-foreground">Delivery:</span>
                    <span className="text-muted-foreground line-through">
                      {formatDateInMalaysia(row.dateMove.from)}
                    </span>
                    <ArrowRight className="size-3.5 shrink-0" aria-hidden />
                    <span className="font-medium">{formatDateInMalaysia(row.dateMove.to)}</span>
                    <span
                      className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] font-medium tabular-nums"
                      title={
                        row.dateMove.deltaDays === null
                          ? 'The delta could not be worked out'
                          : `${row.dateMove.deltaDays >= 0 ? 'Delayed' : 'Advanced'} by ` +
                            `${Math.abs(row.dateMove.deltaDays)} day${Math.abs(row.dateMove.deltaDays) === 1 ? '' : 's'}`
                      }
                    >
                      {row.dateMove.deltaDays === null
                        ? '—'
                        : `${row.dateMove.deltaDays >= 0 ? '+' : ''}${row.dateMove.deltaDays} d`}
                    </span>
                  </p>
                )}
                {row.qtyChanges.map((change, index) => (
                  <p
                    key={`${change.productLabel}-${index}`}
                    className="mt-0.5 flex flex-wrap items-center gap-1.5"
                  >
                    <span className="text-muted-foreground">{`${change.productLabel} qty:`}</span>
                    <span className="text-muted-foreground line-through">
                      {change.from ? formatQty(change.from) : 'None'}
                    </span>
                    <ArrowRight className="size-3.5 shrink-0" aria-hidden />
                    <span className="font-medium">
                      {change.to ? formatQty(change.to) : 'None'}
                    </span>
                  </p>
                ))}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

interface DiffRow {
  phaseId: string;
  label: string;
  area: string | null;
  dateMove: PhaseDateMove | null;
  qtyChanges: ScheduleQtyChange[];
}

/** One row per phase that moved a date or a quantity, in the sheet's own document order. */
function buildDiffRows(
  version: DeliveryScheduleVersion,
  dateMoves: PhaseDateMove[],
  qtyChanges: ScheduleQtyChange[],
): DiffRow[] {
  const dateByPhase = new Map(dateMoves.map((move) => [move.phaseId, move]));
  const qtyByPhase = new Map<string, ScheduleQtyChange[]>();
  for (const change of qtyChanges) {
    const existing = qtyByPhase.get(change.phaseId);
    if (existing) existing.push(change);
    else qtyByPhase.set(change.phaseId, [change]);
  }

  const rows: DiffRow[] = [];
  for (const group of groupPhasesByArea(version.phases)) {
    for (const phase of group.phases) {
      const dateMove = dateByPhase.get(phase.id) ?? null;
      const changes = qtyByPhase.get(phase.id) ?? [];
      if (!dateMove && changes.length === 0) continue;
      rows.push({
        phaseId: phase.id,
        label: phase.label?.trim() || `Phase ${phase.sequence}`,
        area: group.area,
        dateMove,
        qtyChanges: changes,
      });
    }
  }
  return rows;
}
