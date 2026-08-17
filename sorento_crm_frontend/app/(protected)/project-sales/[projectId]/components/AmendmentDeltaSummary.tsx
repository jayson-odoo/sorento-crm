'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AMENDMENT_VERBS } from '../../_shared/types/projectSalesOrder.types';
import type { AmendmentDeltaRow } from '../../_shared/types/projectSalesOrder.types';

/** Fields that are a date move and nothing else. */
const DATE_FIELDS = new Set(['delivery_date', 'schedule_date']);

const FIELD_LABEL: Record<string, string> = {
  delivery_date: 'delivery date',
  schedule_date: 'schedule date',
  qty: 'quantity',
  quantity: 'quantity',
  unit_price: 'unit price',
  amount: 'amount',
  product_code: 'product',
  product_id: 'product',
  phase_label: 'phase',
  phase_id: 'phase',
  area_group: 'sales order',
  uom: 'unit of measure',
};

export function fieldLabel(field: string): string {
  return FIELD_LABEL[field] ?? field.replace(/_/g, ' ');
}

export interface DeltaShape {
  total: number;
  /** True when every changed field is a date. The reviewer's actual question. */
  dateOnly: boolean;
  dateRows: number;
  /** Non-date field label to the number of rows carrying it, in descending order. */
  otherFields: { label: string; count: number }[];
  headline: string;
}

/**
 * Answers "did anything other than the dates change?" without anyone reading 99 rows.
 *
 * A revision that moves dates must leave quantities alone, so the interesting fact is not
 * how many rows changed but whether any NON-date field is in the set. The sentence states
 * that first and quantifies second.
 */
export function describeDeltaShape(rows: AmendmentDeltaRow[]): DeltaShape {
  const counts = new Map<string, number>();
  let dateRows = 0;
  rows.forEach((row) => {
    if (DATE_FIELDS.has(row.field)) {
      dateRows += 1;
      return;
    }
    const label = fieldLabel(row.field);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  });

  const otherFields = [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));

  const dateOnly = rows.length > 0 && otherFields.length === 0;
  const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

  let headline: string;
  if (rows.length === 0) {
    headline = 'Nothing changed between these two versions.';
  } else if (dateOnly) {
    headline = `Dates only. ${plural(dateRows, 'line')} move; quantities, prices and products are unchanged.`;
  } else {
    const others = otherFields
      .map((entry) => `${plural(entry.count, `${entry.label} change`)}`)
      .join(', ');
    headline =
      dateRows > 0
        ? `Not only dates: ${others}, alongside ${plural(dateRows, 'date move')}.`
        : `No dates move. ${others.charAt(0).toUpperCase()}${others.slice(1)}.`;
  }

  return { total: rows.length, dateOnly, dateRows, otherFields, headline };
}

export function AmendmentDeltaSummary({
  rows,
  verbSummary,
  unmatchedCount,
  fromLabel,
  toLabel,
}: {
  rows: AmendmentDeltaRow[];
  verbSummary: Record<string, number>;
  unmatchedCount: number;
  fromLabel: string;
  toLabel: string;
}) {
  const shape = React.useMemo(() => describeDeltaShape(rows), [rows]);

  // The client's verbs in their own order, then anything the backend sent that is not one
  // of them, so an unexpected verb is visible rather than dropped.
  const orderedVerbs = [
    ...AMENDMENT_VERBS.filter((verb) => (verbSummary[verb] ?? 0) > 0).map((verb) => ({
      verb: verb as string,
      count: verbSummary[verb] ?? 0,
    })),
    ...Object.entries(verbSummary)
      .filter(([verb, count]) => count > 0 && !AMENDMENT_VERBS.includes(verb as never))
      .map(([verb, count]) => ({ verb, count })),
  ];

  return (
    <Card className={shape.dateOnly ? undefined : 'border-amber-300 dark:border-amber-800'}>
      <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words text-sm">What changed</CardTitle>
        <span className="truncate text-xs text-muted-foreground" title={`${fromLabel} to ${toLabel}`}>
          {`${fromLabel} to ${toLabel}`}
        </span>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="break-words text-sm font-medium" data-testid="delta-headline">
          {shape.headline}
        </p>

        <div className="flex flex-wrap gap-1.5">
          {orderedVerbs.length === 0 ? (
            <Badge variant="outline">No actions for purchasing</Badge>
          ) : (
            orderedVerbs.map((entry) => (
              <Badge key={entry.verb} variant="secondary" appearance="light">
                {`${entry.verb} ${entry.count}`}
              </Badge>
            ))
          )}
          {unmatchedCount > 0 && (
            <Badge variant="warning" appearance="light">
              {`${unmatchedCount} unmatched`}
            </Badge>
          )}
        </div>

        {shape.otherFields.length > 0 && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {shape.dateRows > 0 && <li>{`delivery date: ${shape.dateRows}`}</li>}
            {shape.otherFields.map((entry) => (
              <li key={entry.label}>{`${entry.label}: ${entry.count}`}</li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
