'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Layers,
  Sparkles,
} from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useApplyProductSetProposals,
  useProductSetProposals,
  useRunProductSetProposals,
} from '../hooks/useProductSetProposals';
import type { ProductSetProposal } from '../types/productSetProposal.types';

/** RM, or an explicit absence. A price of zero and a missing price are different facts. */
function price(value: number | null, absent = 'No basis') {
  if (value === null) {
    return (
      <span className="text-muted-foreground" title="No member sets the price yet">
        {absent}
      </span>
    );
  }
  // Cents always. `1180.00` rendered as `RM 1,180` and `1180.50` as `RM 1,180.5`
  // reads as a different price from the one on the product row it came off.
  return (
    <span className="tabular-nums">
      RM{' '}
      {value.toLocaleString('en-MY', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}
    </span>
  );
}

function ProposalCard({
  proposal,
  checked,
  onToggle,
}: {
  proposal: ProductSetProposal;
  checked: boolean;
  onToggle: () => void;
}) {
  const [open, setOpen] = useState(false);
  // Surfaced on the COLLAPSED card as well as inside it: 41 of the 136 live
  // candidates carry one, and a reviewer ticking hundreds will not expand every
  // card to find out which.
  const discontinued = proposal.members.filter((m) => m.is_discontinued);

  return (
    <div className="rounded-lg border">
      <div className="flex flex-wrap items-center gap-3 p-3">
        <Checkbox
          checked={checked}
          onCheckedChange={onToggle}
          aria-label={`Create ${proposal.set_code}`}
        />
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 text-start"
          aria-expanded={open}
        >
          {open ? (
            <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
          )}
          <span className="min-w-0">
            <span className="block truncate font-medium" title={proposal.set_code}>
              {proposal.set_code}
            </span>
            <span className="block truncate text-xs text-muted-foreground" title={proposal.name}>
              {proposal.name}
            </span>
          </span>
        </button>
        <Badge variant="secondary" size="sm">
          {proposal.members.length} member{proposal.members.length === 1 ? '' : 's'}
        </Badge>
        {discontinued.length > 0 ? (
          <Badge
            variant="destructive"
            size="sm"
            title={`Discontinued: ${discontinued.map((m) => m.product_code).join(', ')}`}
          >
            <AlertTriangle className="size-3" /> {discontinued.length} discontinued
          </Badge>
        ) : null}
        <span className="text-sm">{price(proposal.computed_price)}</span>
      </div>

      {open ? (
        <div className="overflow-x-auto border-t">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="text-xs text-muted-foreground">
                <th className="px-3 py-2 text-start font-medium">Product</th>
                <th className="px-3 py-2 text-start font-medium">Description</th>
                <th className="px-3 py-2 text-end font-medium">List price</th>
                <th className="px-3 py-2 text-end font-medium">Qty</th>
                <th className="px-3 py-2 text-start font-medium">Price basis</th>
              </tr>
            </thead>
            <tbody>
              {proposal.members.map((m) => (
                <tr key={m.product_code} className="border-t">
                  <td className="max-w-[200px] px-3 py-2">
                    <span className="flex items-center gap-1.5">
                      <span className="min-w-0 truncate" title={m.product_code}>
                        {m.product_code}
                      </span>
                      {m.is_discontinued ? (
                        <Badge
                          variant="destructive"
                          size="sm"
                          title="Discontinued. The set survives; it cannot complete."
                        >
                          <AlertTriangle className="size-3" /> Discontinued
                        </Badge>
                      ) : null}
                    </span>
                  </td>
                  <td
                    className="max-w-[280px] truncate px-3 py-2 text-muted-foreground"
                    title={m.description ?? ''}
                  >
                    {m.description ?? '-'}
                  </td>
                  <td className="px-3 py-2 text-end">{price(m.list_price, '-')}</td>
                  <td className="px-3 py-2 text-end tabular-nums">{m.quantity}</td>
                  <td className="px-3 py-2">
                    {m.contributes_to_price ? (
                      <Badge variant="primary" size="sm">
                        Sets the price
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

export default function ProductSetProposals() {
  const { data: batch, isLoading, isError, error } = useProductSetProposals();
  const run = useRunProductSetProposals();
  const apply = useApplyProductSetProposals();

  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
  } = useDebouncedSearch();
  const [confirmingScan, setConfirmingScan] = useState(false);

  const proposals = batch?.proposals ?? [];
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return proposals;
    return proposals.filter(
      (p) =>
        p.set_code.toLowerCase().includes(needle) ||
        p.name.toLowerCase().includes(needle) ||
        p.members.some((m) => m.product_code.toLowerCase().includes(needle)),
    );
  }, [proposals, search]);

  /** Grouped by family, because two candidates in one family are the same
   *  assembly in different trap variants and are judged against each other. */
  const families = useMemo(() => {
    const groups = new Map<string, ProductSetProposal[]>();
    for (const p of visible) {
      const list = groups.get(p.family_key);
      if (list) list.push(p);
      else groups.set(p.family_key, [p]);
    }
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [visible]);

  function toggle(id: string) {
    setTicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleFamily(ids: string[]) {
    setTicked((prev) => {
      const next = new Set(prev);
      const allOn = ids.every((id) => next.has(id));
      for (const id of ids) {
        if (allOn) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  /** A scan REPLACES the open batch, so every ticked id dies with it.
   *
   *  Left standing, the sticky bar still claimed "40 ticked" over a screen where
   *  nothing was checked, and Create then sent 40 ids that no longer existed and
   *  came back as 40 error toasts.
   */
  function scan() {
    run.mutate(undefined, { onSuccess: () => setTicked(new Set()) });
  }

  async function onApply() {
    const ids = [...ticked];
    if (!ids.length) return;
    await apply.mutateAsync(ids);
    setTicked(new Set());
  }

  if (isLoading) {
    return (
      <Card className="space-y-3 p-4">
        <Skeleton className="h-6 w-52" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </Card>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load proposals.'}
      </div>
    );
  }

  // No batch and a batch that found nothing are different facts, and the second
  // one is the good news: every family the catalogue names already has a set.
  if (!batch || proposals.length === 0) {
    return (
      <Card>
        <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
          <div className="rounded-full bg-muted p-3">
            <Layers className="size-6 text-muted-foreground" />
          </div>
          <p className="max-w-md text-sm text-muted-foreground">
            {batch
              ? 'Nothing left to propose. Every assembly the catalogue names already has a set.'
              : 'The catalogue names assemblies it has no code for. Scan it and the pass will fill in the code, the members and the price basis for you to check.'}
          </p>
          <div className="flex flex-wrap justify-center gap-2 pt-1">
            {/* The first run from the empty state destroys nothing, so it does
                not confirm. */}
            <Button onClick={scan} disabled={run.isPending}>
              <Sparkles className="size-4" />
              {run.isPending ? 'Scanning...' : 'Propose from catalogue'}
            </Button>
            <Button variant="outline" asChild>
              <Link href="/master-data-management/product-sets">Back to sets</Link>
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <Card className="flex flex-wrap items-center justify-between gap-3 p-3">
        <div className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{batch.proposal_count}</span> proposed
          across <span className="font-medium text-foreground">{batch.family_count}</span>{' '}
          families
          {batch.company_name ? ` for ${batch.company_name}` : ''}.
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ListSearchInput
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Search code or member"
            className="w-56"
          />
          <Button
            variant="outline"
            onClick={() => setConfirmingScan(true)}
            disabled={run.isPending}
          >
            <Sparkles className="size-4" />
            {run.isPending ? 'Scanning...' : 'Scan again'}
          </Button>
        </div>
      </Card>

      {families.length === 0 ? (
        <Card className="px-6 py-10 text-center text-sm text-muted-foreground">
          No proposals match that search.
        </Card>
      ) : null}

      {families.map(([family, items]) => {
        const ids = items.map((p) => p.id);
        const allOn = ids.every((id) => ticked.has(id));
        return (
          <Card key={family} className="space-y-2 p-3">
            <div className="flex items-center gap-3">
              <Checkbox
                checked={allOn}
                onCheckedChange={() => toggleFamily(ids)}
                aria-label={`Create every candidate in ${family}`}
              />
              <span className="truncate font-medium" title={family}>
                {family}
              </span>
              <Badge variant="secondary" size="sm">
                {items.length} candidate{items.length === 1 ? '' : 's'}
              </Badge>
            </div>
            <div className="space-y-2">
              {items.map((p) => (
                <ProposalCard
                  key={p.id}
                  proposal={p}
                  checked={ticked.has(p.id)}
                  onToggle={() => toggle(p.id)}
                />
              ))}
            </div>
          </Card>
        );
      })}

      {ticked.size > 0 ? (
        <div className="sticky bottom-4 z-10">
          <Card className="flex flex-wrap items-center justify-between gap-3 p-3 shadow-lg">
            <span className="text-sm">
              <span className="font-medium">{ticked.size}</span> ticked
            </span>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setTicked(new Set())}>
                Clear
              </Button>
              <Button onClick={onApply} disabled={apply.isPending}>
                {apply.isPending
                  ? 'Creating...'
                  : `Create ${ticked.size} set${ticked.size === 1 ? '' : 's'}`}
              </Button>
            </div>
          </Card>
        </div>
      ) : null}

      {/* Replacing the batch is destructive, so it confirms like a delete. */}
      <AlertDialog open={confirmingScan} onOpenChange={setConfirmingScan}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Scan the catalogue again?</AlertDialogTitle>
            <AlertDialogDescription>
              The {batch.proposal_count} candidate
              {batch.proposal_count === 1 ? '' : 's'} on screen are replaced by a fresh
              scan
              {ticked.size > 0
                ? `, and your ${ticked.size} ticked candidate${ticked.size === 1 ? '' : 's'} are cleared`
                : ''}
              . Sets you have already created are not touched.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={run.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={scan} disabled={run.isPending}>
              Scan again
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
