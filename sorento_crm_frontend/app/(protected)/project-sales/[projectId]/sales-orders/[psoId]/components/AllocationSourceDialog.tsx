'use client';

import * as React from 'react';
import { LoaderCircleIcon, PackageSearch, Send } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useAllocationCandidates } from '../../../../_shared/hooks/useProjectAllocations';
import type {
  AllocationCandidate,
  AllocationLineRow,
  AllocationSourceInput,
} from '../../../../_shared/types/projectAllocation.types';
import { ALLOCATION_SOURCE_LABEL } from '../../../../_shared/types/projectAllocation.types';
import { InfoHint } from '../../../components/InfoHint';
import { formatQty } from '../../../components/SalesOrderMoney';

function toNumber(value: string | null | undefined): number {
  const parsed = Number.parseFloat(value ?? '0');
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * The ranked sources for one line, and the decision taken on them (AC-H1 to AC-H4).
 *
 * Two different actions, because they are two different things. Stock nobody has spoken
 * for is USED: type a quantity against it and confirm. Stock held for another project is
 * ASKED for: it carries a Request button that raises a claim to that project's CS, and it
 * can never be typed into the basket, because until they accept, nothing moves.
 *
 * The figures are fetched every time this opens and are never cached: they belong to other
 * people's stock and go stale the moment those people ship.
 */
export function AllocationSourceDialog({
  line,
  canEdit,
  submitting,
  onDone,
  onConfirm,
  onClaim,
}: {
  line: AllocationLineRow;
  canEdit: boolean;
  submitting: boolean;
  onDone: () => void;
  onConfirm: (sources: AllocationSourceInput[]) => Promise<unknown>;
  onClaim: (body: { warehouse_id: string; to_project_id: string; qty: string }) => Promise<unknown>;
}) {
  const candidates = useAllocationCandidates(line.line_id);
  const [draft, setDraft] = React.useState<Record<string, string>>({});
  const [orderQty, setOrderQty] = React.useState('');
  const [seeded, setSeeded] = React.useState(false);

  const data = candidates.data;

  // The proposal is pre-filled once, so opening the picker shows what the system would do
  // and the person edits it rather than starting from an empty form.
  React.useEffect(() => {
    if (!data || seeded) return;
    const next: Record<string, string> = {};
    data.plan.forEach((leg) => {
      next[leg.warehouse_id] = leg.qty;
    });
    setDraft(next);
    setOrderQty(toNumber(data.shortfall) > 0 ? data.shortfall : '');
    setSeeded(true);
  }, [data, seeded]);

  const needed = toNumber(line.qty);
  const chosen =
    Object.values(draft).reduce((total, value) => total + toNumber(value), 0) +
    toNumber(orderQty);
  const outstanding = Math.max(needed - chosen, 0);
  const overCommitted = chosen > needed;

  /**
   * Locations typed past what they actually hold.
   *
   * The line total was checked but the per-location figure was not, so 500 could be typed
   * against a shelf holding 30 and the form submitted happily. The server refuses it, but
   * finding out after pressing Confirm is a worse way to learn. `order` is exempt: it has
   * no shelf to exceed.
   */
  const overDrawn = (data?.candidates ?? []).filter((candidate) => {
    if (!candidate.warehouse_id || candidate.source_type === 'other_project') return false;
    const typed = toNumber(draft[candidate.warehouse_id]);
    return typed > 0 && typed > toNumber(candidate.allocatable);
  });
  const blocked = overCommitted || overDrawn.length > 0;

  const buildSources = (): AllocationSourceInput[] => {
    const rows: AllocationSourceInput[] = [];
    (data?.candidates ?? []).forEach((candidate) => {
      if (!candidate.warehouse_id || candidate.source_type === 'other_project') return;
      const qty = draft[candidate.warehouse_id];
      if (!qty || toNumber(qty) <= 0) return;
      rows.push({
        source_type: candidate.source_type,
        warehouse_id: candidate.warehouse_id,
        qty,
      });
    });
    if (toNumber(orderQty) > 0) rows.push({ source_type: 'order', qty: orderQty });
    return rows;
  };

  const sources = buildSources();

  const submit = async () => {
    if (sources.length === 0 || blocked) return;
    await onConfirm(sources);
    onDone();
  };

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            <span className="break-words">
              {`Line ${line.line_no}: ${line.product_code || 'Unresolved product'}`}
            </span>
            <Badge variant="secondary" appearance="light">
              {`${formatQty(line.qty)} ${line.uom || ''}`.trim()}
            </Badge>
            <InfoHint label="About ranked sources">
              Locations are ranked master location first, then this project&apos;s own stock,
              then anything free elsewhere, then stock held for another project, and finally
              ordering it. The figures are read live each time this opens.
            </InfoHint>
          </DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-4">
          {candidates.isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}

          {candidates.isError && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-6 text-center">
              <p className="text-sm font-semibold text-destructive">
                The ranked sources could not be loaded
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {candidates.error instanceof Error
                  ? candidates.error.message
                  : 'Try again in a moment.'}
              </p>
            </div>
          )}

          {data && data.candidates.length === 0 && (
            <div className="rounded-lg border border-dashed px-4 py-10 text-center">
              <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
              <p className="mt-2 text-sm font-semibold">No location holds this product</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
                It has to be ordered. Put the full quantity against Order it below.
              </p>
            </div>
          )}

          {data?.candidates.map((candidate) => (
            <CandidateCard
              key={candidate.warehouse_id ?? 'order'}
              candidate={candidate}
              canEdit={canEdit}
              value={
                candidate.source_type === 'order'
                  ? orderQty
                  : draft[candidate.warehouse_id ?? ''] ?? ''
              }
              onChange={(value) => {
                if (candidate.source_type === 'order') {
                  setOrderQty(value);
                  return;
                }
                if (!candidate.warehouse_id) return;
                setDraft((current) => ({ ...current, [candidate.warehouse_id as string]: value }));
              }}
              outstanding={outstanding}
              onClaim={async (holderProjectId, qty) => {
                if (!candidate.warehouse_id) return;
                await onClaim({
                  warehouse_id: candidate.warehouse_id,
                  to_project_id: holderProjectId,
                  qty,
                });
                onDone();
              }}
              submitting={submitting}
            />
          ))}
        </DialogBody>

        <DialogFooter className="flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p
            className={`text-sm ${blocked ? 'text-destructive' : 'text-muted-foreground'}`}
          >
            {overDrawn.length > 0
              ? `${overDrawn[0].warehouse_code ?? 'That location'} only has ${formatQty(overDrawn[0].allocatable)} free.`
              : overCommitted
              ? `That is ${formatQty(String(chosen - needed))} more than the line needs.`
              : outstanding > 0
                ? `${formatQty(String(chosen))} of ${formatQty(line.qty)} sourced, ${formatQty(String(outstanding))} still open.`
                : `All ${formatQty(line.qty)} sourced.`}
          </p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={submit}
              disabled={!canEdit || submitting || sources.length === 0 || blocked}
            >
              {submitting ? (
                <LoaderCircleIcon className="size-4 animate-spin" aria-hidden />
              ) : (
                <Send className="size-4" aria-hidden />
              )}
              Confirm source
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CandidateCard({
  candidate,
  canEdit,
  value,
  outstanding,
  onChange,
  onClaim,
  submitting,
}: {
  candidate: AllocationCandidate;
  canEdit: boolean;
  value: string;
  /** What the line still needs once the other sources on it are counted. */
  outstanding: number;
  onChange: (value: string) => void;
  onClaim: (holderProjectId: string, qty: string) => Promise<void>;
  submitting: boolean;
}) {
  const held = candidate.source_type === 'other_project';
  const isOrder = candidate.source_type === 'order';
  const inputId = `alloc-qty-${candidate.warehouse_id ?? 'order'}`;

  /**
   * Ask for what this line needs, not for everything the other project is holding.
   *
   * This used to send `candidate.claimable`, so a line needing 10 against a pile of 40
   * put a request for all 40 into the other CS's inbox, and with two holders on one
   * candidate both buttons asked for the same 40. Bounded by what that holder actually
   * has, so we never ask one project for stock a different project is holding.
   */
  const claimQtyFor = (holder: { qty: string }) => {
    const held_qty = Number(holder.qty);
    const want = Number.isFinite(outstanding) && outstanding > 0 ? outstanding : held_qty;
    const asked = Math.min(want, held_qty);
    return String(asked > 0 ? asked : held_qty);
  };

  return (
    <div className="rounded-lg border px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" appearance="light" size="sm">
              {candidate.rank}
            </Badge>
            <span className="truncate text-sm font-medium" title={candidate.warehouse_code ?? ''}>
              {candidate.warehouse_code || 'No location'}
            </span>
            <Badge
              variant={held ? 'warning' : isOrder ? 'secondary' : 'success'}
              appearance="light"
              size="sm"
            >
              {ALLOCATION_SOURCE_LABEL[candidate.source_type]}
            </Badge>
            {candidate.is_project_location && (
              <Badge variant="info" appearance="light" size="sm">
                This project
              </Badge>
            )}
          </div>

          {isOrder ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Nothing on the shelf covers this. Purchasing buys it.
            </p>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">
              {`On hand ${formatQty(candidate.on_hand)} · committed ${formatQty(
                candidate.committed,
              )} · free ${formatQty(candidate.available)}`}
            </p>
          )}

          {candidate.holders.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {candidate.holders.map((holder) => (
                <li key={holder.project_id} className="text-xs text-muted-foreground">
                  {`${formatQty(holder.qty)} held for ${holder.project_code}, ask ${
                    holder.cs_name || 'their CS'
                  }`}
                </li>
              ))}
            </ul>
          )}

          {candidate.open_claim_state === 'requested' && (
            <p className="mt-1 text-xs font-medium text-amber-600">
              Already asked for. Waiting on an answer.
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-end gap-2">
          {held ? (
            candidate.holders.map((holder) => (
              <Button
                key={holder.project_id}
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  !canEdit || submitting || candidate.open_claim_state === 'requested'
                }
                onClick={() => onClaim(holder.project_id, claimQtyFor(holder))}
              >
                {`Request from ${holder.project_code}`}
              </Button>
            ))
          ) : (
            <div className="w-32">
              <Label htmlFor={inputId} className="text-xs text-muted-foreground">
                Take
              </Label>
              <Input
                id={inputId}
                inputMode="decimal"
                value={value}
                disabled={!canEdit || submitting}
                placeholder="0"
                onChange={(event) => onChange(event.target.value)}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
