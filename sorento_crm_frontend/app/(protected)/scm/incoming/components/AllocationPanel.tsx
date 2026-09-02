'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, LoaderCircle } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { EM_DASH, fmtInt } from '../../lib/format';
import {
  approveAllocations,
  getAllocationSuggestion,
  type AllocationLine,
  type AllocationOption,
} from '../../services/fulfilmentService';

/**
 * One decision per line: accept what the system worked out, or point it somewhere else.
 *
 * The screen arrives with an answer rather than a form. What makes accepting a DECISION rather
 * than a shrug is the two things beside it: the reason the winner won, and the orders it beat,
 * both of which come from the same Fulfilment Priority policy the Loading Plan ranks by.
 *
 * The running total is on screen the whole time because approving refuses a split that does not
 * sum to what shipped. Discovering that in an error message after pressing Approve would be the
 * screen keeping a rule to itself.
 */

const REASON_LABEL: Record<AllocationLine['reason'], string> = {
  only_open_order: 'The only open order for this item',
  highest_priority: 'Highest priority of the open orders',
  no_open_order: 'No open order for this item',
};

export function AllocationPanel({ shipmentId }: { shipmentId: string }) {
  const qc = useQueryClient();
  const suggestion = useQuery({
    queryKey: ['scm', 'fulfilment', 'allocation', shipmentId],
    queryFn: () => getAllocationSuggestion(shipmentId),
    refetchOnWindowFocus: false,
  });

  /** Which option each line is pointed at, keyed by shipment line. */
  const [choice, setChoice] = useState<Record<string, string>>({});

  useEffect(() => {
    // Start on what the system proposed. Re-seeded whenever a different container is opened,
    // so a choice made on one never carries onto another.
    const next: Record<string, string> = {};
    for (const ln of suggestion.data?.lines ?? []) {
      if (ln.suggestion) next[ln.shipment_line_id] = ln.suggestion.po_line_id;
    }
    setChoice(next);
  }, [suggestion.data]);

  const approve = useMutation({
    mutationFn: () => {
      const decisions = (suggestion.data?.lines ?? [])
        .filter((ln) => ln.quantity_to_allocate > 0)
        .map((ln) => {
          const picked = optionsFor(ln).find(
            (o) => o.po_line_id === choice[ln.shipment_line_id],
          );
          return {
            shipment_line_id: ln.shipment_line_id,
            splits: [
              {
                po_line_id: picked?.po_line_id ?? null,
                warehouse_id: picked?.warehouse_id ?? '',
                qty: ln.quantity_to_allocate,
              },
            ],
          };
        });
      return approveAllocations(shipmentId, decisions);
    },
    onSuccess: (out) => {
      qc.invalidateQueries({ queryKey: ['scm', 'fulfilment', 'allocation', shipmentId] });
      toast.success(
        `${out.allocations_written} allocated. ${out.purchase_order_lines_advanced} purchase-order line${
          out.purchase_order_lines_advanced === 1 ? '' : 's'
        } moved from ordered to incoming.`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const lines = useMemo(() => suggestion.data?.lines ?? [], [suggestion.data]);
  const outstanding = useMemo(
    () => lines.filter((ln) => ln.quantity_to_allocate > 0),
    [lines],
  );
  const blocked = outstanding.filter((ln) => {
    const picked = optionsFor(ln).find((o) => o.po_line_id === choice[ln.shipment_line_id]);
    return !picked?.warehouse_id;
  });

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">
            {suggestion.data?.container_no || suggestion.data?.shipment_number || 'Container'}
          </h3>
          <p className="text-2xs text-muted-foreground">
            {outstanding.length
              ? `${outstanding.length} line${outstanding.length === 1 ? '' : 's'} to allocate`
              : 'Everything on this container is allocated.'}
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => approve.mutate()}
          disabled={!outstanding.length || !!blocked.length || approve.isPending}
        >
          {approve.isPending ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <Check className="size-4" />
          )}
          Approve
        </Button>
      </CardHeader>

      <div className="px-4 pb-4">
        {suggestion.isLoading ? (
          <Skeleton className="h-24 w-full rounded-lg" />
        ) : !lines.length ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            This container has no line we hold a product for.
          </p>
        ) : (
          <div className="space-y-2">
            {blocked.length ? (
              <Alert variant="destructive">
                <AlertDescription>
                  {blocked.length} line{blocked.length === 1 ? '' : 's'} have nowhere to land.
                  Pick a location before approving.
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="divide-y divide-border rounded-lg border">
              {lines.map((ln) => {
                const options = optionsFor(ln);
                const picked = options.find((o) => o.po_line_id === choice[ln.shipment_line_id]);
                const done = ln.quantity_to_allocate <= 0;
                return (
                  <div key={ln.shipment_line_id} className="p-3">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="text-xs font-medium">
                          {fmtInt(ln.quantity_shipped)} shipped
                          {ln.quantity_allocated > 0 ? (
                            <span className="ms-2 text-muted-foreground">
                              {fmtInt(ln.quantity_allocated)} already allocated
                            </span>
                          ) : null}
                        </div>
                        <p className="text-2xs text-muted-foreground">
                          {REASON_LABEL[ln.reason]}
                          {picked?.po_number ? ` · ${picked.po_number}` : ''}
                          {picked?.warehouse_code ? ` · ${picked.warehouse_code}` : ''}
                        </p>
                      </div>
                      <div className="shrink-0 text-2xs text-muted-foreground">
                        {done ? 'Allocated' : `${fmtInt(ln.quantity_to_allocate)} to allocate`}
                      </div>
                    </div>

                    {done ? null : options.length ? (
                      <SearchableSelect
                        className="mt-2 w-full sm:w-96"
                        value={choice[ln.shipment_line_id] ?? ''}
                        onChange={(v: string) =>
                          setChoice((c) => ({ ...c, [ln.shipment_line_id]: v }))
                        }
                        options={options.map((o) => ({
                          value: o.po_line_id,
                          label: `${o.po_number ?? EM_DASH} · ${o.warehouse_code ?? 'no location'} · ${fmtInt(
                            o.outstanding,
                          )} outstanding`,
                        }))}
                        placeholder="Where this draws down"
                      />
                    ) : (
                      <p className="mt-2 text-2xs text-muted-foreground">
                        Nothing to draw down. It will be received against no purchase order,
                        which leaves the ordered figure unchanged.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

/** The winner and its alternatives as one list, so the select shows what was compared. */
function optionsFor(line: AllocationLine): AllocationOption[] {
  return line.suggestion ? [line.suggestion, ...line.alternatives] : line.alternatives;
}
