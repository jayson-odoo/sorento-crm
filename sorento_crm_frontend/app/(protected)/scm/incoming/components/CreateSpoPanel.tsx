'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Download, FileText, LoaderCircle } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { EM_DASH, fmtInt } from '../../lib/format';
import {
  createSpo,
  downloadSpoWorksheet,
  getSpoSuggestion,
  type SpoConfirmLine,
  type SpoSuggestionLine,
} from '../../services/fulfilmentService';

/**
 * "Create SPO" - the shipment page's own confirm screen for the second half of
 * `PLAN-scm-proforma-to-spo.md`. Every line pre-checked at its suggested quantity, per the
 * plan's journey: the buyer unticks or trims before converting. A line already covered by an
 * open PO or by stock reads as covered - visible, unticked, one line saying why; a line with
 * no supplier on it cannot convert at all.
 *
 * Runs for a DRAFT shipment too (the captain will often act before the real packing list
 * arrives) - the base quantity is then the draft's own PACKED figure, same as any other
 * shipment, and the copy below says so explicitly.
 *
 * **UNREFERENCED as of the captain's second amendment (21 Aug 00:40).** The surface and shape
 * both moved: `SpoPlannerTable` on `/procurement-management/packing-lists/{id}` (a planner
 * TABLE, not this checkbox list) is where "Create SPO" lives now. This file and its own test
 * (`CreateSpoPanel.test.tsx`) are kept, deliberately unmounted from `IncomingContainersView`,
 * rather than deleted - see the plan doc for why the surface moved.
 */

export function CreateSpoPanel({ shipmentId }: { shipmentId: string }) {
  const qc = useQueryClient();
  const suggestion = useQuery({
    queryKey: ['scm', 'fulfilment', 'spo-suggestion', shipmentId],
    queryFn: () => getSpoSuggestion(shipmentId),
  });

  /** Per shipment line: whether it is ticked, and the confirmed quantity. */
  const [confirm, setConfirm] = useState<Record<string, { include: boolean; qty: number }>>({});

  useEffect(() => {
    // Seeded from the suggestion every time a different container is opened (or this one's
    // suggestion refetches) - pre-checked at the suggested qty, covered/unmatched lines start
    // unticked, exactly the plan's "pre-checked" screen.
    const next: Record<string, { include: boolean; qty: number }> = {};
    for (const ln of suggestion.data?.lines ?? []) {
      next[ln.shipment_line_id] = {
        include: !ln.cannot_convert && ln.suggested_qty > 0,
        qty: ln.suggested_qty,
      };
    }
    setConfirm(next);
  }, [suggestion.data]);

  const create = useMutation({
    mutationFn: () => {
      const lines: SpoConfirmLine[] = (suggestion.data?.lines ?? []).map((ln) => ({
        shipment_line_id: ln.shipment_line_id,
        qty: confirm[ln.shipment_line_id]?.qty ?? 0,
        include: confirm[ln.shipment_line_id]?.include ?? false,
      }));
      return createSpo(shipmentId, lines);
    },
    onSuccess: (out) => {
      qc.invalidateQueries({ queryKey: ['scm', 'fulfilment', 'spo-suggestion', shipmentId] });
      const names = out.created_spos.map((s) => s.po_number).filter(Boolean).join(', ');
      toast.success(
        out.created_spos.length
          ? `Created ${out.created_spos.length === 1 ? 'SPO' : `${out.created_spos.length} SPOs`}: ${names}.`
          : 'Nothing was created - every line was already covered.',
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const worksheet = useMutation({
    mutationFn: () =>
      downloadSpoWorksheet(
        shipmentId,
        suggestion.data?.shipment_number ?? 'container',
      ),
    onError: (e: Error) => toast.error(e.message),
  });

  const lines = useMemo(() => suggestion.data?.lines ?? [], [suggestion.data]);
  const selected = lines.filter((ln) => confirm[ln.shipment_line_id]?.include);
  const alreadyConverted = suggestion.data?.already_converted ?? false;

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Create SPO</h3>
          <p className="text-2xs text-muted-foreground">
            {alreadyConverted
              ? 'Already created from this shipment.'
              : suggestion.data?.shipment_status === 'draft'
                ? "Draft shipment - based on this draft's own packed quantities, not a real packing list yet."
                : 'One SPO per supplier, from what is packed and not already covered.'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {alreadyConverted ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => worksheet.mutate()}
              disabled={worksheet.isPending}
            >
              {worksheet.isPending ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
              ) : (
                <Download className="size-4" aria-hidden />
              )}
              Download worksheet
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => create.mutate()}
              disabled={!selected.length || create.isPending}
            >
              {create.isPending ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
              ) : (
                <Check className="size-4" aria-hidden />
              )}
              Create SPO
            </Button>
          )}
        </div>
      </CardHeader>

      <div className="px-4 pb-4">
        {suggestion.isLoading ? (
          <Skeleton className="h-24 w-full rounded-lg" />
        ) : suggestion.isError ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            {suggestion.error instanceof Error
              ? suggestion.error.message
              : 'Failed to load the SPO suggestion.'}
          </p>
        ) : alreadyConverted ? (
          <div className="flex flex-wrap items-center gap-2">
            <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            {(suggestion.data?.existing_spos ?? []).map((spo) => (
              <Badge key={spo.purchase_order_id} variant="secondary" size="sm">
                {spo.po_number ?? EM_DASH}
                {spo.supplier_name ? ` · ${spo.supplier_name}` : ''}
              </Badge>
            ))}
          </div>
        ) : !lines.length ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            This container has no line we hold a product for.
          </p>
        ) : (
          <div className="divide-y divide-border rounded-lg border">
            {lines.map((ln) => (
              <SpoLineRow
                key={ln.shipment_line_id}
                line={ln}
                state={confirm[ln.shipment_line_id] ?? { include: false, qty: 0 }}
                onChange={(next) =>
                  setConfirm((c) => ({ ...c, [ln.shipment_line_id]: next }))
                }
              />
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function SpoLineRow({
  line,
  state,
  onChange,
}: {
  line: SpoSuggestionLine;
  state: { include: boolean; qty: number };
  onChange: (next: { include: boolean; qty: number }) => void;
}) {
  const disabled = line.cannot_convert;
  return (
    <div className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-2">
        <Checkbox
          className="mt-0.5"
          checked={state.include}
          disabled={disabled}
          onCheckedChange={(v) => onChange({ ...state, include: v === true })}
        />
        <div className="min-w-0">
          <div className="truncate text-xs font-medium" title={line.item_code ?? undefined}>
            {line.item_code ?? 'Unmatched product'}
            {line.product_name ? (
              <span className="ms-1 font-normal text-muted-foreground">{line.product_name}</span>
            ) : null}
          </div>
          <p className="text-2xs text-muted-foreground">
            {fmtInt(line.packed_qty)} packed
            {line.supplier_name ? ` · ${line.supplier_name}` : ''}
            {line.po_covered_qty > 0
              ? ` · ${fmtInt(line.po_covered_qty)} already on ${line.matched_po_number ?? 'an open PO'}`
              : ''}
            {line.on_hand > 0 ? ` · ${fmtInt(line.on_hand)} on hand` : ''}
            {line.incoming_spo > 0 ? ` · ${fmtInt(line.incoming_spo)} incoming` : ''}
          </p>
          {line.reason ? (
            <p className="text-2xs text-muted-foreground">{line.reason}</p>
          ) : null}
        </div>
      </div>
      <div className="shrink-0">
        <Input
          type="number"
          min={0}
          step={1}
          className="w-28"
          value={state.qty}
          disabled={disabled || !state.include}
          onChange={(e) => onChange({ ...state, qty: Math.max(Number(e.target.value) || 0, 0) })}
        />
      </div>
    </div>
  );
}

export default CreateSpoPanel;
