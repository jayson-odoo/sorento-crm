'use client';

import * as React from 'react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { useIsMobile } from '@/hooks/use-mobile';
import {
  useApplyCostPriceChangeSet,
  useCostPriceChangeLines,
  useDecideAllCostPriceLines,
  useDecideCostPriceLine,
  usePatchCostPriceChangeLine,
  useReturnCostPriceChangeSet,
  useSubmitCostPriceChangeSet,
} from '../../hooks/useCostPriceChangeSets';
import { searchCostPriceProductOptions, type PatchLineInput } from '../../services/costPriceService';
import type { CostPriceChangeLine, CostPriceChangeSetDetail } from '../../types/costPrice.types';

type FilterKey = 'changed' | 'unchanged' | 'new_link' | 'unmatched' | 'duplicate_code' | 'needs_attention';

const FILTERS: { key: FilterKey; label: string; predicate: (l: CostPriceChangeLine) => boolean }[] = [
  { key: 'changed', label: 'Price changed', predicate: (l) => !l.skipped && l.line_state === 'changed' },
  { key: 'unchanged', label: 'Unchanged', predicate: (l) => !l.skipped && l.line_state === 'unchanged' },
  { key: 'new_link', label: 'New for this supplier', predicate: (l) => !l.skipped && l.line_state === 'new_link' },
  { key: 'unmatched', label: 'Not found', predicate: (l) => !l.skipped && l.match_outcome === 'unmatched' },
  { key: 'duplicate_code', label: 'Duplicate code', predicate: (l) => !l.skipped && l.flags.includes('duplicate_code') },
  { key: 'needs_attention', label: 'Needs attention', predicate: (l) => !l.skipped && l.line_state === 'needs_attention' },
];

function searchTokens(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

function matchesSearch(line: CostPriceChangeLine, tokens: string[]): boolean {
  if (!tokens.length) return true;
  const haystack = [line.supplier_code, line.configuration, line.product?.product_code, line.product?.description, line.sheet]
    .filter(Boolean)
    .map((s) => (s as string).toLowerCase());
  return tokens.every((t) => haystack.some((h) => h.includes(t)));
}

function ChangeBadge({ line }: { line: CostPriceChangeLine }) {
  if (line.line_state === 'new_link') return <Badge variant="info">New link</Badge>;
  if (line.change_pct == null) return <span className="text-muted-foreground">-</span>;
  if (line.change_pct === 0) return <Badge variant="secondary">0%</Badge>;
  const rise = line.change_pct > 0;
  return (
    <Badge variant={rise ? 'destructive' : 'success'}>
      {rise ? '+' : ''}
      {line.change_pct.toFixed(1)}%
    </Badge>
  );
}

function money(value: number | null, currency: string | null): string {
  if (value == null) return 'none';
  return `${value.toFixed(2)} ${currency ?? ''}`.trim();
}

/**
 * One line, as a card (mockup `cost-price-review.html`, "At 375 wide"): the DataGrid's
 * horizontal-scroll table does not fit a phone, so mobile gets its own layout rather than
 * a narrower cut of the same columns - same fields (code, sheet/row, configuration, our
 * product, price now to new, decision), stacked.
 */
function LineCard({
  line,
  showDecisionColumn,
  isPendingForVerifier,
  onPatch,
  onDecide,
}: {
  line: CostPriceChangeLine;
  showDecisionColumn: boolean;
  isPendingForVerifier: boolean;
  onPatch: (patch: PatchLineInput) => void;
  onDecide: (decision: 'accepted' | 'rejected') => void;
}) {
  const showDecision = isPendingForVerifier && !line.skipped && (line.line_state === 'changed' || line.line_state === 'new_link');
  const showReadOnlyDecision = showDecisionColumn && !isPendingForVerifier && line.decision != null;
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="font-medium">{line.supplier_code}</span>
          {line.code_note ? <div className="text-xs text-muted-foreground">note: {line.code_note}</div> : null}
        </div>
        <ChangeBadge line={line} />
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {line.sheet} row {line.row_no}
        </span>
        <span className="truncate">{line.configuration ?? ''}</span>
      </div>

      {line.match_outcome === 'unmatched' ? (
        <div className="mt-2 flex flex-col gap-1.5">
          <SearchableSelect
            id={`map-mobile-${line.id}`}
            value=""
            onChange={() => {}}
            onOptionChange={(opt) => onPatch({ product_id: opt?.value ?? null })}
            fetchOptions={searchCostPriceProductOptions}
            clearable
            size="sm"
            placeholder="Pick a product"
            triggerClassName="w-full"
          />
          <Button type="button" size="sm" variant="ghost" className="self-start text-muted-foreground" onClick={() => onPatch({ skipped: true, skip_reason: 'Not found' })}>
            Skip
          </Button>
        </div>
      ) : (
        <>
          <div className="mt-2 flex items-center justify-between text-sm">
            <span className="text-xs text-muted-foreground">Our product</span>
            <span className="font-medium">{line.product?.product_code ?? '-'}</span>
          </div>
          <div className="mt-1 flex items-center justify-between text-sm">
            <span className="text-xs text-muted-foreground">Price now to new</span>
            <span className="tabular-nums">
              {line.current_unit_cost != null ? <span className="text-muted-foreground line-through">{line.current_unit_cost.toFixed(2)}</span> : null}{' '}
              {money(line.new_unit_cost, line.current_currency)}
            </span>
          </div>
          {line.flags.includes('duplicate_code') ? (
            <Button type="button" size="sm" variant="ghost" className="mt-1 text-muted-foreground" onClick={() => onPatch({ skipped: true, skip_reason: 'Duplicate code' })}>
              Skip this one
            </Button>
          ) : null}
          {line.line_state === 'new_link' && line.new_link_lead_time_days == null ? (
            <div className="mt-1 flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Lead time (days)</span>
              <Input
                type="number"
                min={0}
                className="h-7 w-20"
                onBlur={(e) => {
                  const v = e.target.value ? Number(e.target.value) : undefined;
                  if (v !== undefined) onPatch({ new_link_lead_time_days: v });
                }}
              />
            </div>
          ) : null}
        </>
      )}

      {showDecision ? (
        <div className="mt-2 flex items-center gap-1.5">
          <Button type="button" size="sm" variant={line.decision === 'accepted' ? 'primary' : 'outline'} onClick={() => onDecide('accepted')}>
            Accept
          </Button>
          <Button type="button" size="sm" variant={line.decision === 'rejected' ? 'destructive' : 'outline'} onClick={() => onDecide('rejected')}>
            Reject
          </Button>
        </div>
      ) : null}
      {showReadOnlyDecision ? (
        <div className="mt-2">
          {line.decision === 'accepted' ? (
            <Badge variant="success">Accepted</Badge>
          ) : (
            <>
              <Badge variant="destructive" title={line.decision_reason ?? undefined}>
                Rejected
              </Badge>
              {line.decision_reason ? (
                <div className="mt-0.5 truncate text-xs text-muted-foreground" title={line.decision_reason}>
                  {line.decision_reason}
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

/** Return to submitter needs a reason (AC-S2-09), so it is the one action here with a dialog. */
function ReturnDialog({ setId, onDone }: { setId: string; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const returnSet = useReturnCostPriceChangeSet(setId);

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        Return to submitter
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Return to submitter</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value.slice(0, 500))}
              placeholder="Why is this set going back?"
              rows={4}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!reason.trim() || returnSet.isPending}
              onClick={async () => {
                await returnSet.mutateAsync(reason.trim());
                setOpen(false);
                setReason('');
                onDone();
              }}
            >
              Return
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function CostPriceLinesTab({ changeSet }: { changeSet: CostPriceChangeSetDetail }) {
  const { data } = useCostPriceChangeLines(changeSet.id);
  const lines = React.useMemo(() => data?.data ?? [], [data]);
  // Cards at 375 (mockup "At 375 wide"), the DataGrid at sm+ - a JS switch, not a CSS
  // one: `sm:hidden`/`hidden sm:block` render BOTH into the DOM regardless of viewport
  // (jsdom applies no CSS), which doubled every button `getByRole` sees in the existing
  // vitest suite. `useIsMobile` defaults to false until its effect runs, which in jsdom
  // (innerWidth 1024) settles on the desktop view - the same one these tests render today.
  const isMobile = useIsMobile();

  const [activeFilter, setActiveFilter] = React.useState<FilterKey>('changed');
  const [search, setSearch] = React.useState('');
  const [activeSheet, setActiveSheet] = React.useState('all');

  const patchLine = usePatchCostPriceChangeLine(changeSet.id);
  const decideLine = useDecideCostPriceLine(changeSet.id);
  const decideAll = useDecideAllCostPriceLines(changeSet.id);
  const submit = useSubmitCostPriceChangeSet(changeSet.id);
  const apply = useApplyCostPriceChangeSet(changeSet.id);

  const tokens = React.useMemo(() => searchTokens(search), [search]);
  const searchedLines = React.useMemo(() => lines.filter((l) => matchesSearch(l, tokens)), [lines, tokens]);

  const sheets = React.useMemo(() => Array.from(new Set(lines.map((l) => l.sheet))), [lines]);

  const filteredLines = React.useMemo(() => {
    const predicate = FILTERS.find((f) => f.key === activeFilter)!.predicate;
    return searchedLines.filter((l) => predicate(l) && (activeSheet === 'all' || l.sheet === activeSheet));
  }, [searchedLines, activeFilter, activeSheet]);

  const isVerifier = changeSet.actions.can_decide || changeSet.actions.can_return;
  const isPendingForVerifier = isVerifier && changeSet.status === 'pending_verification';
  // J14/AC-AU-04 (tester finding 1): once a set leaves Pending, a line's decision must
  // stay visible - read-only - not vanish the moment `showDecisionColumn`'s original
  // "verifier on a Pending set" condition goes false. A read-only column earns its
  // place ONLY when there is something to show; an untouched draft/applied-with-no-
  // decisions set gets no Decision column at all.
  const anyLineHasDecision = lines.some((l) => l.decision != null);
  const showDecisionColumn = isPendingForVerifier || anyLineHasDecision;
  // With the setting on, a staff draft always goes through Submit, never straight to
  // Apply (AC-S2-04) - driven by the set's own workflow, not by whether Submit
  // happens to be enabled right now, so a blocked draft still shows Submit (disabled)
  // rather than silently falling back to the Apply button verification-off sets use.
  const isSubmitWorkflow =
    changeSet.verification_enabled && changeSet.status === 'draft' && changeSet.channel === 'staff_upload';

  const columns = React.useMemo<ColumnDef<CostPriceChangeLine>[]>(() => {
    const base: ColumnDef<CostPriceChangeLine>[] = [
      {
        // Sheet and Row merged into one column (column-width budget, 1280 breakpoint):
        // the grid must reach the Decision column at ~950px of content width without
        // horizontal scroll, and neither value is worth its own 60-110px slot.
        id: 'sheet_row',
        header: 'Sheet / row',
        size: 90,
        cell: ({ row }) => (
          <div className="min-w-0 text-xs">
            <span className="block truncate font-medium" title={row.original.sheet}>
              {row.original.sheet}
            </span>
            <span className="text-muted-foreground">Row {row.original.row_no}</span>
          </div>
        ),
      },
      {
        id: 'supplier_code',
        header: 'Supplier code',
        size: 140,
        cell: ({ row }) => (
          <div className="min-w-0">
            <span className="block truncate font-medium" title={row.original.supplier_code}>
              {row.original.supplier_code}
            </span>
            {row.original.code_note ? (
              <span className="block truncate text-xs text-muted-foreground" title={row.original.code_note}>
                note: {row.original.code_note}
              </span>
            ) : null}
          </div>
        ),
      },
      {
        id: 'configuration',
        header: 'Configuration',
        size: 90,
        cell: ({ row }) => (
          <div className="min-w-0">
            <span className="block truncate" title={row.original.configuration ?? ''}>
              {row.original.configuration ?? '-'}
            </span>
            {row.original.flags.includes('configuration_from_merge') ? (
              <span className="block text-xs text-muted-foreground">merged</span>
            ) : null}
          </div>
        ),
      },
      {
        id: 'product',
        header: 'Our product',
        size: 170,
        cell: ({ row }) => {
          const line = row.original;
          if (line.match_outcome === 'unmatched') {
            return (
              <div className="flex min-w-0 flex-col gap-1.5">
                <SearchableSelect
                  id={`map-${line.id}`}
                  value=""
                  onChange={() => {}}
                  onOptionChange={(opt) =>
                    void patchLine.mutateAsync({ lineId: line.id, patch: { product_id: opt?.value ?? null } })
                  }
                  fetchOptions={searchCostPriceProductOptions}
                  clearable
                  size="sm"
                  placeholder="Pick a product"
                  triggerClassName="w-full"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="self-start text-muted-foreground"
                  onClick={() => void patchLine.mutateAsync({ lineId: line.id, patch: { skipped: true, skip_reason: 'Not found' } })}
                >
                  Skip
                </Button>
              </div>
            );
          }
          return (
            <div className="min-w-0">
              <span className="block truncate font-medium" title={line.product?.product_code ?? ''}>
                {line.product?.product_code ?? '-'}
              </span>
              {line.match_rung || line.match_outcome !== 'exact' ? (
                <span className="block truncate text-xs text-muted-foreground">
                  {line.match_outcome === 'manual' ? 'mapped by hand' : line.match_rung ? `supplier code rule: ${line.match_rung}` : line.match_outcome}
                  {line.line_state === 'new_link' ? ', new for this supplier' : ''}
                </span>
              ) : null}
              {line.flags.includes('duplicate_code') ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="mt-1 text-muted-foreground"
                  onClick={() => void patchLine.mutateAsync({ lineId: line.id, patch: { skipped: true, skip_reason: 'Duplicate code' } })}
                >
                  Skip this one
                </Button>
              ) : null}
              {line.line_state === 'needs_attention' && !line.flags.includes('duplicate_code') ? (
                <div className="mt-1 flex items-center gap-1.5">
                  <span className="text-xs text-destructive">
                    {line.new_unit_cost == null ? 'No readable price' : 'Needs attention'}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="text-muted-foreground"
                    onClick={() => void patchLine.mutateAsync({ lineId: line.id, patch: { skipped: true, skip_reason: 'No readable price' } })}
                  >
                    Skip
                  </Button>
                </div>
              ) : null}
              {line.line_state === 'new_link' && line.new_link_lead_time_days == null ? (
                <div className="mt-1 flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Lead time (days)</span>
                  <Input
                    type="number"
                    min={0}
                    className="h-7 w-20"
                    defaultValue=""
                    onBlur={(e) => {
                      const v = e.target.value ? Number(e.target.value) : undefined;
                      if (v !== undefined) void patchLine.mutateAsync({ lineId: line.id, patch: { new_link_lead_time_days: v } });
                    }}
                  />
                </div>
              ) : null}
            </div>
          );
        },
      },
      {
        id: 'current',
        header: 'Price now',
        // 110, not 90: "498.00 CNY" truncated to "498.0..." at 90px (Phase 1 evidence,
        // review-verification-off-1280.png) - wide enough for a 3-digit amount plus
        // its currency code with room to spare.
        size: 110,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => <span className="tabular-nums">{money(row.original.current_unit_cost, row.original.current_currency)}</span>,
      },
      {
        id: 'new',
        header: 'New price',
        size: 110,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => <span className="tabular-nums">{money(row.original.new_unit_cost, changeSet.currency)}</span>,
      },
      {
        id: 'change',
        header: 'Change',
        size: 90,
        cell: ({ row }) => <ChangeBadge line={row.original} />,
      },
    ];

    if (showDecisionColumn) {
      base.push({
        id: 'decision',
        header: 'Decision',
        size: isPendingForVerifier ? 150 : 130,
        cell: ({ row }) => {
          const line = row.original;
          if (isPendingForVerifier) {
            if (line.skipped || (line.line_state !== 'changed' && line.line_state !== 'new_link')) {
              return <span className="text-muted-foreground">-</span>;
            }
            return (
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  size="sm"
                  variant={line.decision === 'accepted' ? 'primary' : 'outline'}
                  onClick={() => void decideLine.mutateAsync({ lineId: line.id, decision: 'accepted' })}
                >
                  Accept
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={line.decision === 'rejected' ? 'destructive' : 'outline'}
                  onClick={() => void decideLine.mutateAsync({ lineId: line.id, decision: 'rejected', reason: 'Not agreed' })}
                >
                  Reject
                </Button>
              </div>
            );
          }
          // J14/AC-AU-04: the set has left Pending (or the caller isn't the verifier who
          // decided it) - a line's decision is now a FACT of the record, not something
          // to re-decide, so it renders read-only. The reject reason travels with it
          // (visible text AND `title`, so either a sighted skim or a hover/hit-test
          // finds it) - a reviewer must not have to cross-reference the History tab to
          // learn why a line was rejected.
          if (!line.decision) return <span className="text-muted-foreground">-</span>;
          if (line.decision === 'accepted') return <Badge variant="success">Accepted</Badge>;
          return (
            <div className="min-w-0">
              <Badge variant="destructive" title={line.decision_reason ?? undefined}>
                Rejected
              </Badge>
              {line.decision_reason ? (
                <span className="mt-0.5 block truncate text-xs text-muted-foreground" title={line.decision_reason}>
                  {line.decision_reason}
                </span>
              ) : null}
            </div>
          );
        },
      });
    }
    return base;
  }, [changeSet.currency, decideLine, isPendingForVerifier, patchLine, showDecisionColumn]);

  const table = useReactTable({
    columns,
    data: filteredLines,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const emptyMessages: Record<FilterKey, string> = {
    changed: 'Nothing changed against current prices',
    unchanged: 'No unchanged rows',
    new_link: 'No new products from this supplier',
    unmatched: 'No codes need mapping',
    duplicate_code: 'No duplicate codes',
    needs_attention: 'Nothing needs attention',
  };

  const actions = changeSet.actions;

  return (
    <div className="space-y-4">
      {/* Stat cards as filters (search-scoped counts, AC-SR-02). */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {FILTERS.map((f) => {
          const count = searchedLines.filter(f.predicate).length;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setActiveFilter(f.key)}
              className={`rounded-lg border p-2.5 text-left transition-colors ${
                activeFilter === f.key ? 'border-primary bg-primary/5' : 'border-border bg-card'
              }`}
            >
              <div className="text-lg font-bold tabular-nums">{count}</div>
              <div className="text-xs text-muted-foreground">{f.label}</div>
            </button>
          );
        })}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <ListSearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search code, configuration or product"
          className="w-full sm:w-72"
        />
        {sheets.length > 1 ? (
          <Tabs value={activeSheet} onValueChange={setActiveSheet} className="min-w-0 flex-1">
            <TabsList variant="line" className="w-full justify-start overflow-x-auto">
              <TabsTrigger value="all">All sheets</TabsTrigger>
              {sheets.map((sheet) => (
                <TabsTrigger key={sheet} value={sheet}>
                  {sheet}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        ) : null}
      </div>

      {filteredLines.length === 0 ? (
        <Card>
          <div className="flex flex-col items-center gap-3 p-10 text-center">
            <p className="text-sm font-medium">{emptyMessages[activeFilter]}</p>
            {activeFilter === 'changed' && searchedLines.length === lines.length && lines.every((l) => l.line_state === 'unchanged' || l.skipped) && actions.can_discard ? (
              <p className="text-xs text-muted-foreground">Discard this set from the header above.</p>
            ) : null}
          </div>
        </Card>
      ) : isMobile ? (
        <div className="space-y-2">
          {filteredLines.map((line) => (
            <LineCard
              key={line.id}
              line={line}
              showDecisionColumn={showDecisionColumn}
              isPendingForVerifier={isPendingForVerifier}
              onPatch={(patch) => void patchLine.mutateAsync({ lineId: line.id, patch })}
              onDecide={(decision) => void decideLine.mutateAsync({ lineId: line.id, decision })}
            />
          ))}
        </div>
      ) : (
        <DataGrid table={table} recordCount={filteredLines.length} listingKey="" tableLayout={{ width: 'fixed', columnsResizable: true }}>
          <Card>
            <CardTable>
              <DataGridTable />
            </CardTable>
          </Card>
        </DataGrid>
      )}

      {/* Sticky apply bar, driven only by `actions` from the detail (contract 1.4) - the FE
          never re-derives the four-eyes rule. Nothing left to do on an applied set. */}
      {changeSet.status !== 'applied' ? (
        <div className="sticky bottom-0 z-10 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-background p-3 shadow-sm">
          <span className="text-sm font-medium">
            {actions.apply_count} {actions.apply_count === 1 ? 'change' : 'changes'} ready
          </span>
          {changeSet.largest_rise ? (
            <span className="text-sm text-muted-foreground">
              Largest rise: {changeSet.largest_rise.supplier_code} +{changeSet.largest_rise.change_pct.toFixed(1)}%
            </span>
          ) : null}
          {actions.apply_blocked_reason ? (
            <span className="text-sm text-muted-foreground">{actions.apply_blocked_reason}</span>
          ) : null}
          <div className="ms-auto flex flex-wrap items-center gap-2">
            {actions.can_decide ? (
              <Button type="button" variant="outline" size="sm" onClick={() => void decideAll.mutateAsync('accepted')}>
                Accept all
              </Button>
            ) : null}
            {actions.can_return ? <ReturnDialog setId={changeSet.id} onDone={() => {}} /> : null}
            {isSubmitWorkflow ? (
              <Button
                onClick={() => void submit.mutateAsync()}
                disabled={!actions.can_submit || submit.isPending}
                title={actions.apply_blocked_reason ?? undefined}
              >
                Submit for verification
              </Button>
            ) : (
              <Button
                onClick={() => void apply.mutateAsync()}
                disabled={!actions.can_apply || apply.isPending}
                title={actions.apply_blocked_reason ?? undefined}
              >
                Apply {actions.apply_count} {actions.apply_count === 1 ? 'change' : 'changes'}
              </Button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default CostPriceLinesTab;
