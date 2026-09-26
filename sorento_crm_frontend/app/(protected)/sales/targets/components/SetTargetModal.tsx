'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DateRangePicker } from '@/components/ui/date-range-picker';
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
import { Switch } from '@/components/ui/switch';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import {
  useCreateSalesTarget,
  useSalesTargetOptions,
  useTargetProductSearch,
} from '../hooks/useSalesTargets';
import { endOfMonth, formatFigure, shortDate, unitOf } from '../lib/format';
import { generatePeriods } from '../lib/periods';
import type {
  SalesTargetCreatePayload,
  SalesTargetOptions,
  TargetBasis,
  TargetMetric,
  TargetProductScope,
  TargetSplitUnit,
} from '../types/salesTarget.types';

type Kind = 'agent' | 'team';

const KIND_OPTIONS = [
  { value: 'agent', label: 'Agent' },
  { value: 'team', label: 'Team' },
];
const METRIC_OPTIONS = [
  { value: 'amount', label: 'Amount (RM)' },
  { value: 'quantity', label: 'Quantity (units)' },
];
const COUNTS_OPTIONS = [
  { value: 'ordered', label: 'Ordered' },
  { value: 'delivered', label: 'Delivered' },
];
const APPLIES_OPTIONS = [
  { value: 'all', label: 'All products' },
  { value: 'categories', label: 'Categories' },
  { value: 'products', label: 'Products' },
];
const UNIT_OPTIONS = [
  { value: 'day', label: 'Days' },
  { value: 'week', label: 'Weeks' },
  { value: 'month', label: 'Months' },
];

/** Members of the team on any day of the range, one line per agent (S1-27). */
function membersInRange(
  team: SalesTargetOptions['teams'][number] | undefined,
  start: string,
  end: string,
): { sales_agent_id: string; label: string }[] {
  if (!team) return [];
  const seen = new Map<string, string>();
  for (const m of team.members) {
    const inRange =
      (!m.valid_from || m.valid_from <= end) &&
      (!m.valid_to || m.valid_to >= start);
    if (inRange && !seen.has(m.sales_agent_id))
      seen.set(m.sales_agent_id, m.label);
  }
  return Array.from(seen, ([sales_agent_id, label]) => ({
    sales_agent_id,
    label,
  })).sort((a, b) => a.label.localeCompare(b.label));
}

function toNumber(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/**
 * Set target (UAC S1-18, S1-24, S1-25, S1-27; plan 3.9): the create form for the target page's
 * fields in the same order. Sections Target, What counts, Dates, then the figure.
 *
 * Every picker is the standard `SearchableSelect` (N8); only Split unit is clearable, and
 * clearing it turns the split off. The range is a start and an end date (N6), split optionally
 * every N days, weeks or months (N7), picked with the shared `DateRangePicker` (S1-25). An
 * agent target takes one figure, for the whole range
 * or per period. A team target takes one figure per agent in the team during the range and
 * shows their sum read-only: the team figure IS that sum (owner ruling 26 Sep 06:09, T3).
 *
 * Opened from the header, "Target for" is preset to the open tab's kind and Who is empty;
 * opened from a "No target" row or a team page, Who is filled in and read-only.
 */
export default function SetTargetModal({
  open,
  onOpenChange,
  presetKind,
  presetSubjectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  presetKind?: 'agent' | 'team' | 'dealer';
  presetSubjectId?: string;
}) {
  const { data: options } = useSalesTargetOptions(open);
  const save = useCreateSalesTarget();

  const initialKind: Kind | '' =
    presetKind === 'agent' || presetKind === 'team' ? presetKind : '';
  const today = todayMalaysiaYyyyMmDd();
  const [kind, setKind] = useState<Kind | ''>(initialKind);
  const [subjectId, setSubjectId] = useState(presetSubjectId ?? '');
  const [name, setName] = useState('');
  const [metric, setMetric] = useState<TargetMetric>('amount');
  const [basis, setBasis] = useState<TargetBasis>('ordered');
  const [scope, setScope] = useState<TargetProductScope>('all');
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [productIds, setProductIds] = useState<string[]>([]);
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(endOfMonth(today));
  const [split, setSplit] = useState(false);
  const [splitEvery, setSplitEvery] = useState('1');
  const [splitUnit, setSplitUnit] = useState<TargetSplitUnit | ''>('month');
  const [figure, setFigure] = useState('');
  const [agentFigures, setAgentFigures] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    const now = todayMalaysiaYyyyMmDd();
    setKind(presetKind === 'agent' || presetKind === 'team' ? presetKind : '');
    setSubjectId(presetSubjectId ?? '');
    setName('');
    setMetric('amount');
    setBasis('ordered');
    setScope('all');
    setCategoryIds([]);
    setProductIds([]);
    setStartDate(now);
    setEndDate(endOfMonth(now));
    setSplit(false);
    setSplitEvery('1');
    setSplitUnit('month');
    setFigure('');
    setAgentFigures({});
  }, [open, presetKind, presetSubjectId]);

  const subjectOptions = useMemo(() => {
    if (kind === 'agent')
      return (options?.agents ?? []).map((a) => ({
        value: a.id,
        label: a.label,
      }));
    if (kind === 'team')
      return (options?.teams ?? []).map((t) => ({
        value: t.id,
        label: t.name,
      }));
    return [];
  }, [kind, options]);
  const categoryOptions = useMemo(
    () =>
      (options?.categories ?? []).map((c) => ({ value: c.id, label: c.label })),
    [options],
  );

  const team =
    kind === 'team'
      ? options?.teams.find((t) => t.id === subjectId)
      : undefined;
  const members = useMemo(
    () => membersInRange(team, startDate, endDate),
    [team, startDate, endDate],
  );
  const teamSum = members.reduce(
    (sum, m) => sum + toNumber(agentFigures[m.sales_agent_id] ?? ''),
    0,
  );

  const every = Number(splitEvery);
  const splitOn =
    split &&
    !!splitUnit &&
    Number.isInteger(every) &&
    every >= 1 &&
    every <= 99;
  let periodHint = '';
  let periodError = '';
  if (startDate && endDate) {
    try {
      const periods = generatePeriods(
        startDate,
        endDate,
        splitOn ? every : null,
        splitOn ? (splitUnit as TargetSplitUnit) : null,
      );
      const last = periods[periods.length - 1];
      periodHint =
        periods.length === 1
          ? `1 period, ${shortDate(last.start)} to ${shortDate(last.end)}`
          : `${periods.length} periods, the last ${shortDate(last.start)} to ${shortDate(last.end)}`;
    } catch (error) {
      periodError =
        error instanceof Error
          ? error.message
          : 'These dates do not make periods.';
    }
  }

  const scopeReady =
    scope === 'all' ||
    (scope === 'categories' ? categoryIds.length > 0 : productIds.length > 0);
  const canSave =
    !!kind &&
    !!subjectId &&
    name.trim().length > 0 &&
    !!startDate &&
    !!endDate &&
    !periodError &&
    scopeReady &&
    (kind === 'team' ? members.length > 0 : figure.trim() !== '') &&
    !save.isPending;

  const changeKind = (value: string) => {
    setKind((value as Kind) || '');
    setSubjectId('');
    setAgentFigures({});
  };
  const changeSplitUnit = (value: string) => {
    // Clearing the unit turns the split off (S1-24).
    if (!value) {
      setSplit(false);
      setSplitUnit('month');
      return;
    }
    setSplitUnit(value as TargetSplitUnit);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave || !kind) return;
    const common = {
      name: name.trim(),
      metric,
      basis,
      product_scope: scope,
      ...(scope === 'categories' ? { category_ids: categoryIds } : {}),
      ...(scope === 'products' ? { product_ids: productIds } : {}),
      start_date: startDate,
      end_date: endDate,
      ...(splitOn
        ? { split_every: every, split_unit: splitUnit as TargetSplitUnit }
        : {}),
    };
    const payload: SalesTargetCreatePayload =
      kind === 'agent'
        ? {
            subject_kind: 'agent',
            sales_agent_id: subjectId,
            target_value: toNumber(figure),
            ...common,
          }
        : {
            subject_kind: 'team',
            sales_team_id: subjectId,
            agent_figures: members.map((m) => ({
              sales_agent_id: m.sales_agent_id,
              target_value: toNumber(agentFigures[m.sales_agent_id] ?? ''),
            })),
            ...common,
          };
    try {
      await save.mutateAsync(payload);
      onOpenChange(false);
    } catch {
      // The hook toasted the reason; the modal stays open with what was typed.
    }
  };

  const unit = unitOf(metric);
  const perWhat = splitOn ? 'per period' : 'for the whole range';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Set target</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col gap-4">
          <DialogBody className="flex max-h-[65dvh] flex-col gap-5 overflow-y-auto pe-1">
            <section aria-label="Target" className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Target</h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="target-for">Target for</Label>
                  <SearchableSelect
                    id="target-for"
                    value={kind}
                    onChange={changeKind}
                    options={KIND_OPTIONS}
                    placeholder="Pick one"
                    disabled={!!presetSubjectId}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="who">Who</Label>
                  <SearchableSelect
                    id="who"
                    value={subjectId}
                    onChange={setSubjectId}
                    options={subjectOptions}
                    placeholder={
                      kind === 'team' ? 'Pick a team' : 'Pick an agent'
                    }
                    emptyMessage={
                      kind
                        ? 'Nothing active to pick.'
                        : 'Pick Target for first.'
                    }
                    disabled={!kind || !!presetSubjectId}
                    wrapOptions
                  />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="target-name">Name</Label>
                <Input
                  id="target-name"
                  value={name}
                  maxLength={120}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
            </section>

            <section aria-label="What counts" className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">What counts</h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="metric">Metric</Label>
                  <SearchableSelect
                    id="metric"
                    value={metric}
                    onChange={(v) => v && setMetric(v as TargetMetric)}
                    options={METRIC_OPTIONS}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="counts">Counts</Label>
                  <SearchableSelect
                    id="counts"
                    value={basis}
                    onChange={(v) => v && setBasis(v as TargetBasis)}
                    options={COUNTS_OPTIONS}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="applies-to">Applies to</Label>
                  <SearchableSelect
                    id="applies-to"
                    value={scope}
                    onChange={(v) => v && setScope(v as TargetProductScope)}
                    options={APPLIES_OPTIONS}
                  />
                </div>
              </div>
              {scope === 'categories' ? (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="target-categories">Categories</Label>
                  <SearchableMultiSelect
                    id="target-categories"
                    value={categoryIds}
                    onChange={setCategoryIds}
                    options={categoryOptions}
                    placeholder="Pick categories"
                    emptyMessage="No categories."
                    wrapOptions
                  />
                </div>
              ) : null}
              {scope === 'products' ? (
                <ProductScopePicker
                  value={productIds}
                  onChange={setProductIds}
                />
              ) : null}
            </section>

            <section aria-label="Dates" className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Dates</h3>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="target-dates">Start and end date</Label>
                <DateRangePicker
                  id="target-dates"
                  aria-label="Start and end date"
                  from={startDate || null}
                  to={endDate || null}
                  onChange={({ from, to }) => {
                    setStartDate(from ?? '');
                    setEndDate(to ?? '');
                  }}
                  className="sm:w-72"
                />
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <Switch
                    id="target-split"
                    aria-label="Split"
                    checked={split}
                    onCheckedChange={setSplit}
                  />
                  <Label htmlFor="target-split">Split</Label>
                </div>
                {split ? (
                  <div className="flex items-center gap-2">
                    <Label htmlFor="target-split-every">Every</Label>
                    <Input
                      id="target-split-every"
                      type="number"
                      min={1}
                      max={99}
                      value={splitEvery}
                      onChange={(e) => setSplitEvery(e.target.value)}
                      className="w-20"
                    />
                    <Label htmlFor="split-unit" className="sr-only">
                      Split unit
                    </Label>
                    <SearchableSelect
                      id="split-unit"
                      value={splitUnit}
                      onChange={changeSplitUnit}
                      options={UNIT_OPTIONS}
                      clearable
                      className="w-32"
                    />
                  </div>
                ) : null}
              </div>
              {periodError ? (
                <p className="text-sm text-destructive">{periodError}</p>
              ) : periodHint ? (
                <p className="text-xs text-muted-foreground">{periodHint}</p>
              ) : null}
            </section>

            {kind === 'team' ? (
              <section
                aria-label="Agent figures"
                className="flex flex-col gap-3"
              >
                <h3 className="text-sm font-semibold">{`Agent figures, ${unit} ${perWhat}`}</h3>
                {subjectId && members.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No agents in this team during these dates.
                  </p>
                ) : null}
                {members.length ? (
                  <div className="overflow-x-auto rounded-lg border">
                    <table aria-label="Agents" className="w-full text-sm">
                      <thead className="bg-muted/40 text-xs text-muted-foreground">
                        <tr>
                          <th className="px-3 py-2 text-start font-medium">
                            Agent
                          </th>
                          <th className="w-40 px-3 py-2 text-end font-medium">{`Figure (${unit})`}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {members.map((m) => (
                          <tr key={m.sales_agent_id}>
                            <td
                              className="max-w-0 truncate px-3 py-1.5"
                              title={m.label}
                            >
                              {m.label}
                            </td>
                            <td className="px-3 py-1.5">
                              <Input
                                type="number"
                                min={0}
                                step="any"
                                aria-label={`${m.label} figure`}
                                value={agentFigures[m.sales_agent_id] ?? ''}
                                onChange={(e) =>
                                  setAgentFigures((prev) => ({
                                    ...prev,
                                    [m.sales_agent_id]: e.target.value,
                                  }))
                                }
                                className="h-8 text-end"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                <div className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2 text-sm">
                  <span className="font-medium">Team target</span>
                  <span className="tabular-nums">{formatFigure(teamSum)}</span>
                </div>
              </section>
            ) : (
              <section aria-label="Figure" className="flex flex-col gap-1.5">
                <Label htmlFor="target-figure">{`Target figure (${unit}) ${perWhat}`}</Label>
                <Input
                  id="target-figure"
                  type="number"
                  min={0}
                  step="any"
                  value={figure}
                  onChange={(e) => setFigure(e.target.value)}
                  className="sm:w-60"
                />
              </section>
            )}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={save.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              {save.isPending ? (
                <LoaderCircleIcon className="size-4 animate-spin" />
              ) : null}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Products, searched on the server (about 22,000 of them). Mounted only for Applies to: Products. */
function ProductScopePicker({
  value,
  onChange,
}: {
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const search = useTargetProductSearch();
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="target-products">Products</Label>
      <SearchableMultiSelect
        id="target-products"
        value={value}
        onChange={onChange}
        fetchOptions={search}
        placeholder="Search products"
        emptyMessage="No products match."
        wrapOptions
      />
    </div>
  );
}
