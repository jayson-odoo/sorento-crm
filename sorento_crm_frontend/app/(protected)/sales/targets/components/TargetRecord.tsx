'use client';

import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  CalendarRange,
  Check,
  CircleDollarSign,
  Info,
  LoaderCircleIcon,
  Plus,
  SquarePen,
  UsersRound,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import DetailActions from '@/components/common/DetailActions';
import RecordNavigation from '@/components/common/RecordNavigation';
import type { RecordAction } from '@/components/common/recordActions';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateInMalaysia, todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import {
  useCreateSalesTarget,
  useCreateTargetChild,
  usePatchSalesTarget,
  usePatchSalesTargetPeriod,
  useSalesTarget,
  useSalesTargetOptions,
  useSalesTargets,
  useTargetProductSearch,
} from '../hooks/useSalesTargets';
import { useSalesTargetActions } from '../actions';
import {
  METRIC_LABEL,
  SCOPE_LABEL,
  endOfMonth,
  formatFigure,
  formatPct,
  scopeSummary,
  shortDate,
  splitSummary,
  unitOf,
} from '../lib/format';
import { generatePeriods } from '../lib/periods';
import type {
  SalesTargetCreatePayload,
  SalesTargetDetail,
  SalesTargetOptions,
  SalesTargetUpdatePayload,
  TargetBasis,
  TargetMetric,
  TargetProductScope,
  TargetSplitUnit,
  TargetSubjectKind,
} from '../types/salesTarget.types';

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
const APPLIES_OPTIONS: { value: TargetProductScope; label: string }[] = [
  { value: 'all', label: SCOPE_LABEL.all },
  { value: 'categories', label: SCOPE_LABEL.categories },
  { value: 'products', label: SCOPE_LABEL.products },
  { value: 'brands', label: SCOPE_LABEL.brands },
];
const UNIT_OPTIONS = [
  { value: 'day', label: 'Days' },
  { value: 'week', label: 'Weeks' },
  { value: 'month', label: 'Months' },
];

/** The owner's question on the hand test ("what does split mean ya"), answered on the form. */
export const SPLIT_HELP =
  'Split breaks the dates into periods of N days, weeks or months, each with its own figure. Off: one figure for the whole range.';
/** Both dates are required (owner ruling N6); a half-empty range never reaches Save. */
export const DATES_REQUIRED = 'Pick both a start date and an end date.';

type RecordTab = 'details' | 'periods' | 'agents' | 'commission';

interface Draft {
  kind: TargetSubjectKind | '';
  subjectId: string;
  name: string;
  metric: TargetMetric;
  basis: TargetBasis;
  scope: TargetProductScope;
  categoryIds: string[];
  productIds: string[];
  brandIds: string[];
  start: string;
  end: string;
  split: boolean;
  every: string;
  unit: TargetSplitUnit | '';
  /** An agent target's figure, create only. */
  figure: string;
  /** A team target's figure per agent, create only. */
  agentFigures: Record<string, string>;
}

function emptyDraft(preset: TargetRecordPreset | undefined): Draft {
  const today = todayMalaysiaYyyyMmDd();
  return {
    kind: preset?.kind ?? '',
    subjectId: preset?.subjectId ?? '',
    name: '',
    metric: 'amount',
    basis: 'ordered',
    scope: 'all',
    categoryIds: [],
    productIds: [],
    brandIds: [],
    start: today,
    end: endOfMonth(today),
    split: false,
    every: '1',
    unit: 'month',
    figure: '',
    agentFigures: {},
  };
}

function idsOf(target: SalesTargetDetail, kind: 'category' | 'product' | 'brand'): string[] {
  return target.scope.filter((s) => s.kind === kind).map((s) => s.id);
}

function draftOf(target: SalesTargetDetail): Draft {
  return {
    kind: target.subject_kind,
    subjectId: (target.subject_kind === 'team' ? target.sales_team_id : target.sales_agent_id) ?? '',
    name: target.name,
    metric: target.metric,
    basis: target.basis,
    scope: target.product_scope,
    categoryIds: idsOf(target, 'category'),
    productIds: idsOf(target, 'product'),
    brandIds: idsOf(target, 'brand'),
    start: target.start_date,
    end: target.end_date,
    split: !!target.split_every,
    every: String(target.split_every ?? 1),
    unit: target.split_unit ?? 'month',
    figure: '',
    agentFigures: {},
  };
}

function splitOf(draft: Draft): { every: number; unit: TargetSplitUnit } | null {
  const every = Number(draft.every);
  if (!draft.split || !draft.unit || !Number.isInteger(every) || every < 1 || every > 99) return null;
  return { every, unit: draft.unit };
}

function scopeLists(draft: Draft) {
  return {
    category_ids: draft.scope === 'categories' ? draft.categoryIds : [],
    product_ids: draft.scope === 'products' ? draft.productIds : [],
    brand_ids: draft.scope === 'brands' ? draft.brandIds : [],
  };
}

/** Only what changed, so a rename of a child never touches what it follows. */
function changes(target: SalesTargetDetail, draft: Draft): SalesTargetUpdatePayload {
  const out: SalesTargetUpdatePayload = {};
  if (draft.name.trim() !== target.name) out.name = draft.name.trim();
  if (target.parent) return out;
  if (draft.metric !== target.metric) out.metric = draft.metric;
  if (draft.basis !== target.basis) out.basis = draft.basis;
  const before = scopeLists(draftOf(target));
  const after = scopeLists(draft);
  const scopeChanged =
    draft.scope !== target.product_scope ||
    (Object.keys(after) as (keyof typeof after)[]).some((k) => after[k].join() !== before[k].join());
  if (scopeChanged) Object.assign(out, { product_scope: draft.scope, ...after });
  if (draft.start !== target.start_date) out.start_date = draft.start;
  if (draft.end !== target.end_date) out.end_date = draft.end;
  const split = splitOf(draft);
  if ((split?.every ?? null) !== target.split_every || (split?.unit ?? null) !== target.split_unit) {
    out.split_every = split?.every ?? null;
    out.split_unit = split?.unit ?? null;
  }
  return out;
}

/** Members of the team on any day of the range, one line per agent (S1-27). */
function membersInRange(
  team: SalesTargetOptions['teams'][number] | undefined,
  start: string,
  end: string,
): { sales_agent_id: string; label: string }[] {
  if (!team || !start || !end) return [];
  const seen = new Map<string, string>();
  for (const m of team.members) {
    const inRange = (!m.valid_from || m.valid_from <= end) && (!m.valid_to || m.valid_to >= start);
    if (inRange && !seen.has(m.sales_agent_id)) seen.set(m.sales_agent_id, m.label);
  }
  return Array.from(seen, ([sales_agent_id, label]) => ({ sales_agent_id, label })).sort((a, b) =>
    a.label.localeCompare(b.label),
  );
}

function toNumber(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function Field({ label, htmlFor, children }: { label: string; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      {htmlFor ? (
        <Label htmlFor={htmlFor} id={`${htmlFor}-label`} className="text-xs text-muted-foreground">
          {label}
        </Label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <div className="min-w-0 text-sm">{children}</div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Card>
      <section aria-label={label} className="flex flex-col gap-3 p-5">
        <h3 className="text-sm font-semibold">{label}</h3>
        {children}
      </section>
    </Card>
  );
}

/** A figure that edits in place: the value, a pencil, then an input with save and cancel. */
function InlineFigure({
  value,
  label,
  editable,
  saving,
  onSave,
}: {
  value: number;
  label: string;
  editable: boolean;
  saving: boolean;
  onSave: (next: number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  if (!editing) {
    return (
      <span className="inline-flex items-center justify-end gap-1">
        <span className="tabular-nums">{formatFigure(value)}</span>
        {editable ? (
          <Button
            variant="ghost"
            size="sm"
            mode="icon"
            aria-label={label}
            onClick={() => {
              setText(String(value));
              setEditing(true);
            }}
          >
            <SquarePen className="size-3.5" />
          </Button>
        ) : null}
      </span>
    );
  }
  const commit = async () => {
    const next = Number(text);
    if (!Number.isFinite(next) || next < 0) return;
    try {
      await onSave(next);
      setEditing(false);
    } catch {
      // The hook toasted the reason; the input stays open with what was typed.
    }
  };
  return (
    <span className="inline-flex items-center justify-end gap-1">
      <Input
        type="number"
        min={0}
        step="any"
        aria-label={`${label}, new value`}
        value={text}
        autoFocus
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void commit();
          if (e.key === 'Escape') setEditing(false);
        }}
        className="h-8 w-28 text-end"
      />
      <Button variant="ghost" size="sm" mode="icon" aria-label="Save figure" disabled={saving} onClick={() => void commit()}>
        {saving ? <LoaderCircleIcon className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
      </Button>
      <Button variant="ghost" size="sm" mode="icon" aria-label="Cancel" onClick={() => setEditing(false)}>
        <X className="size-3.5" />
      </Button>
    </span>
  );
}

export interface TargetRecordPreset {
  kind?: TargetSubjectKind;
  subjectId?: string;
}

/**
 * The target record (UAC S1-18, S1-23 to S1-28; J14; the S1 hand test of 27 Sep, F4): ONE
 * view for a new target (`/sales/targets/new`, no `id`) and an existing one
 * (`/sales/targets/{id}`), in place of the retired Set target modal.
 *
 * The standard record: a header card (the TGT number, the name, and in the meta strip who it
 * is for, its team target, the agent count, Created and Updated; prev/next and the gear on the
 * right), then line tabs in the order **Details** (Target, What counts, Dates, Figure),
 * **Periods**, **Agents** (a team target only) and **Commission**. Edit is an item in the gear
 * with Duplicate and Delete; the edit view is the same tabs with each value swapped for its
 * input in place, and Cancel and Save in the header card. A new target opens in that edit view,
 * empty, with the defaults Amount, Ordered, All products, today to month end, split off.
 *
 * Every single pick is `SearchableSelect`, every multi pick `SearchableMultiSelect`, and a
 * picked category, product or brand always shows its "CODE - Name" (F5): the record's own scope
 * labels seed the pickers, and every product the search returns is remembered by name.
 *
 * A child of a team target follows its parent (T3): only its name and its figures are its own,
 * so What counts and Dates stay read-only with "Set on <parent>". A team target's periods are
 * the sum of its agents' figures, so each agent's figure edits on the Agents tab.
 */
export default function TargetRecord({ id, preset }: { id?: string; preset?: TargetRecordPreset }) {
  const router = useRouter();
  const isCreate = !id;
  const canEdit = useHasPermission('sales.targets.edit');
  const canOpenAgent = useHasPermission('master_data.sales_agents.view');
  const today = todayMalaysiaYyyyMmDd();

  const loaded = useSalesTarget(id ?? null);
  const { isLoading, isError } = loaded;
  const target = isCreate ? undefined : loaded.data;
  const [draft, setDraft] = useState<Draft | null>(() => (isCreate ? emptyDraft(preset) : null));
  const editing = draft !== null;
  const { data: options } = useSalesTargetOptions(editing);
  const create = useCreateSalesTarget();
  const patchHeader = usePatchSalesTarget();
  const patchPeriod = usePatchSalesTargetPeriod();
  const addChild = useCreateTargetChild();
  const { actions: targetActions, pending } = useSalesTargetActions(target, {
    onDeleted: () => router.push('/sales/targets'),
  });
  const { data: siblings } = useSalesTargets(
    { all: true, subject: target?.subject_kind ?? 'agent' },
    !!target,
  );
  const [tab, setTab] = useState<RecordTab>('details');

  // Every name a picked category, product or brand is known by (F5).
  const labels = useRef(new Map<string, string>());
  for (const item of target?.scope ?? []) labels.current.set(item.id, item.label);
  for (const c of options?.categories ?? []) labels.current.set(c.id, c.label);
  for (const b of options?.brands ?? []) labels.current.set(b.id, b.label);
  const searchProducts = useTargetProductSearch();
  const fetchProducts = useCallback(
    async (query: string) => {
      const rows = await searchProducts(query);
      for (const row of rows) labels.current.set(row.value, row.label);
      return rows;
    },
    [searchProducts],
  );

  const ids = useMemo(() => {
    const seen: string[] = [];
    for (const row of siblings?.rows ?? []) {
      if (row.target_id && !seen.includes(row.target_id)) seen.push(row.target_id);
    }
    return seen;
  }, [siblings]);

  if (!isCreate && isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }
  if (!isCreate && (isError || !target)) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <div className="text-sm font-semibold">Target not found</div>
      </Card>
    );
  }

  const set = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const kind: TargetSubjectKind | '' = isCreate ? (draft?.kind ?? '') : (target as SalesTargetDetail).subject_kind;
  const isTeam = kind === 'team';
  const isChild = !!target?.parent;
  const metric = draft?.metric ?? target?.metric ?? 'amount';
  const unit = unitOf(metric);

  // Periods the dates make, for the hint and the new target's Periods tab.
  const split = draft ? splitOf(draft) : null;
  const datesMissing = !!draft && (!draft.start || !draft.end);
  let periods: { start: string; end: string }[] = [];
  let periodError = '';
  if (draft && !datesMissing) {
    try {
      periods = generatePeriods(draft.start, draft.end, split?.every ?? null, split?.unit ?? null);
    } catch (error) {
      periodError = error instanceof Error ? error.message : 'These dates do not make periods.';
    }
  }

  const team = isTeam ? options?.teams.find((t) => t.id === draft?.subjectId) : undefined;
  const members = draft && isCreate && isTeam ? membersInRange(team, draft.start, draft.end) : [];
  const teamSum = members.reduce((sum, m) => sum + toNumber(draft?.agentFigures[m.sales_agent_id] ?? ''), 0);

  const scopeReady =
    !draft ||
    draft.scope === 'all' ||
    (draft.scope === 'categories' && draft.categoryIds.length > 0) ||
    (draft.scope === 'products' && draft.productIds.length > 0) ||
    (draft.scope === 'brands' && draft.brandIds.length > 0);
  const saving = create.isPending || patchHeader.isPending;
  const canSave =
    !!draft &&
    draft.name.trim().length > 0 &&
    !datesMissing &&
    !periodError &&
    scopeReady &&
    (!isCreate ||
      (!!draft.kind && !!draft.subjectId && (isTeam ? members.length > 0 : draft.figure.trim() !== ''))) &&
    !saving;

  const save = async () => {
    if (!draft || !canSave) return;
    if (!isCreate && target) {
      const pendingChanges = changes(target, draft);
      if (Object.keys(pendingChanges).length === 0) {
        setDraft(null);
        return;
      }
      try {
        await patchHeader.mutateAsync({ targetId: target.id, ...pendingChanges });
        setDraft(null);
      } catch {
        // The hook toasted the reason; the edit stays open so nothing typed is lost.
      }
      return;
    }
    const lists = scopeLists(draft);
    const common = {
      name: draft.name.trim(),
      metric: draft.metric,
      basis: draft.basis,
      product_scope: draft.scope,
      ...(draft.scope === 'categories' ? { category_ids: lists.category_ids } : {}),
      ...(draft.scope === 'products' ? { product_ids: lists.product_ids } : {}),
      ...(draft.scope === 'brands' ? { brand_ids: lists.brand_ids } : {}),
      start_date: draft.start,
      end_date: draft.end,
      ...(split ? { split_every: split.every, split_unit: split.unit } : {}),
    };
    const payload: SalesTargetCreatePayload =
      draft.kind === 'agent'
        ? { subject_kind: 'agent', sales_agent_id: draft.subjectId, target_value: toNumber(draft.figure), ...common }
        : {
            subject_kind: 'team',
            sales_team_id: draft.subjectId,
            agent_figures: members.map((m) => ({
              sales_agent_id: m.sales_agent_id,
              target_value: toNumber(draft.agentFigures[m.sales_agent_id] ?? ''),
            })),
            ...common,
          };
    try {
      const created = await create.mutateAsync(payload);
      router.push(`/sales/targets/${created.id}`);
    } catch {
      // The hook toasted the reason; the record stays open with what was typed.
    }
  };
  const cancel = () => (isCreate ? router.push('/sales/targets') : setDraft(null));

  const tabs: { value: RecordTab; label: string; icon: typeof Info }[] = [
    { value: 'details', label: 'Details', icon: Info },
    { value: 'periods', label: 'Periods', icon: CalendarRange },
    ...(isTeam ? [{ value: 'agents' as const, label: 'Agents', icon: UsersRound }] : []),
    { value: 'commission', label: 'Commission', icon: CircleDollarSign },
  ];

  const actions: RecordAction[] =
    target && canEdit
      ? [{ key: 'sales_target.edit', label: 'Edit', icon: SquarePen, run: () => setDraft(draftOf(target)) }, ...targetActions]
      : targetActions;
  const index = target ? ids.indexOf(target.id) : -1;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="block py-4" data-testid="record-header">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <RecordIdentity target={target} canOpenAgent={canOpenAgent} />
            {editing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={cancel} disabled={saving}>
                  Cancel
                </Button>
                <Button size="sm" onClick={save} disabled={!canSave}>
                  {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                  Save
                </Button>
              </div>
            ) : (
              <DetailActions
                pagerNode={
                  <RecordNavigation
                    index={index >= 0 ? index + 1 : null}
                    total={ids.length}
                    hasPrevious={index > 0}
                    hasNext={index >= 0 && index < ids.length - 1}
                    onPrevious={() => router.push(`/sales/targets/${ids[index - 1]}`)}
                    onNext={() => router.push(`/sales/targets/${ids[index + 1]}`)}
                    ariaLabel="target"
                  />
                }
                actions={actions}
                pendingAction={pending}
                gearLabel="Target options"
              />
            )}
          </div>
        </CardHeader>
      </Card>

      <Tabs value={tab} onValueChange={(v) => setTab(v as RecordTab)}>
        <TabsList variant="line" className="mb-5">
          {tabs.map((t) => (
            <TabsTrigger key={t.value} value={t.value} onClick={() => setTab(t.value)}>
              <t.icon className="size-4" />
              <span>{t.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="details" className="space-y-5">
          <Section label="Target">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Field label="Target for" htmlFor={isCreate ? 'target-for' : undefined}>
                {isCreate && draft ? (
                  <SearchableSelect
                    id="target-for"
                    value={draft.kind}
                    onChange={(v) => set({ kind: (v as TargetSubjectKind) || '', subjectId: '', agentFigures: {} })}
                    options={KIND_OPTIONS}
                    placeholder="Pick one"
                    disabled={!!preset?.subjectId}
                  />
                ) : isTeam ? (
                  'Team'
                ) : (
                  'Agent'
                )}
              </Field>
              <Field label="Who" htmlFor={isCreate ? 'target-who' : undefined}>
                {isCreate && draft ? (
                  <SearchableSelect
                    id="target-who"
                    value={draft.subjectId}
                    onChange={(v) => set({ subjectId: v, agentFigures: {} })}
                    options={
                      draft.kind === 'team'
                        ? (options?.teams ?? []).map((t) => ({ value: t.id, label: t.name }))
                        : draft.kind === 'agent'
                          ? (options?.agents ?? []).map((a) => ({ value: a.id, label: a.label }))
                          : []
                    }
                    placeholder={draft.kind === 'team' ? 'Pick a team' : 'Pick an agent'}
                    emptyMessage={draft.kind ? 'Nothing active to pick.' : 'Pick Target for first.'}
                    disabled={!draft.kind || !!preset?.subjectId}
                    wrapOptions
                  />
                ) : (
                  <span className="block truncate" title={target?.subject_label}>
                    {target?.subject_label}
                  </span>
                )}
              </Field>
              <Field label="Name" htmlFor={editing ? 'target-name' : undefined}>
                {editing ? (
                  <Input
                    id="target-name"
                    value={draft.name}
                    maxLength={120}
                    onChange={(e) => set({ name: e.target.value })}
                    className="h-8"
                  />
                ) : (
                  <span className="block truncate" title={target?.name}>
                    {target?.name}
                  </span>
                )}
              </Field>
            </div>
          </Section>

          <Section label="What counts">
            {editing && !isChild ? (
              <WhatCountsEditor draft={draft} set={set} options={options} labels={labels.current} fetchProducts={fetchProducts} />
            ) : target ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <Field label="Measure">{`${METRIC_LABEL[target.metric]} (${unitOf(target.metric)})`}</Field>
                <Field label="Counts">{target.counts_label}</Field>
                <Field label="Applies to">
                  {target.product_scope === 'all'
                    ? SCOPE_LABEL.all
                    : `${SCOPE_LABEL[target.product_scope]}: ${scopeSummary(target.product_scope, target.scope.length)}`}
                </Field>
                {target.scope.length ? (
                  <ul className="flex flex-col gap-1 sm:col-span-3">
                    {target.scope.map((item) => (
                      <li key={item.id} className="truncate text-sm" title={item.label}>
                        {item.label}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {target.parent ? <SetOnParent parent={target.parent} /> : null}
              </div>
            ) : null}
          </Section>

          <Section label="Dates">
            {editing && !isChild ? (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div className="sm:col-span-2">
                    <Field label="Start and end date" htmlFor="target-dates">
                      <DateRangePicker
                        id="target-dates"
                        aria-label="Start and end date"
                        from={draft.start || null}
                        to={draft.end || null}
                        onChange={({ from, to }) => set({ start: from ?? '', end: to ?? '' })}
                        className="sm:w-72"
                      />
                    </Field>
                  </div>
                  <Field label="Split">
                    <div className="flex flex-wrap items-center gap-2">
                      <Switch aria-label="Split" checked={draft.split} onCheckedChange={(on) => set({ split: on })} />
                      {draft.split ? (
                        <>
                          <Label htmlFor="target-split-every" className="text-xs">
                            Every
                          </Label>
                          <Input
                            id="target-split-every"
                            type="number"
                            min={1}
                            max={99}
                            value={draft.every}
                            onChange={(e) => set({ every: e.target.value })}
                            className="h-8 w-16"
                          />
                          <Label htmlFor="target-split-unit" className="sr-only">
                            Split unit
                          </Label>
                          <SearchableSelect
                            id="target-split-unit"
                            value={draft.unit}
                            // Clearing the unit turns the split off (S1-24).
                            onChange={(v) => (v ? set({ unit: v as TargetSplitUnit }) : set({ split: false, unit: 'month' }))}
                            options={UNIT_OPTIONS}
                            clearable
                            className="w-28"
                          />
                        </>
                      ) : null}
                    </div>
                  </Field>
                </div>
                <p className="text-xs text-muted-foreground">{SPLIT_HELP}</p>
                {datesMissing ? (
                  <p className="text-sm text-destructive">{DATES_REQUIRED}</p>
                ) : periodError ? (
                  <p className="text-sm text-destructive">{periodError}</p>
                ) : periods.length ? (
                  <p className="text-xs text-muted-foreground">
                    {periods.length === 1
                      ? `1 period, ${shortDate(periods[0].start)} to ${shortDate(periods[0].end)}`
                      : `${periods.length} periods, the last ${shortDate(periods[periods.length - 1].start)} to ${shortDate(periods[periods.length - 1].end)}`}
                  </p>
                ) : null}
              </div>
            ) : target ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="sm:col-span-2">
                  <Field label="Start and end date">{`${shortDate(target.start_date)} to ${shortDate(target.end_date)}`}</Field>
                </div>
                <Field label="Split">{splitSummary(target.split_every, target.split_unit)}</Field>
              </div>
            ) : null}
          </Section>

          <Section label="Figure">
            {isCreate && draft && !isTeam ? (
              <Field label={`Target figure (${unit}) ${split ? 'per period' : 'for the whole range'}`} htmlFor="target-figure">
                <Input
                  id="target-figure"
                  type="number"
                  min={0}
                  step="any"
                  value={draft.figure}
                  onChange={(e) => set({ figure: e.target.value })}
                  className="h-8 sm:w-60"
                />
              </Field>
            ) : isCreate ? (
              <Field label={`Team target (${unit})`}>
                <span className="tabular-nums">{formatFigure(teamSum)}</span>
              </Field>
            ) : target ? (
              <Field label={`${isTeam ? 'Team target' : 'Target figure'} (${unit})`}>
                <span className="tabular-nums">{figureSummary(target)}</span>
              </Field>
            ) : null}
          </Section>
        </TabsContent>

        <TabsContent value="periods">
          <Card>
            <section aria-label="Periods" className="flex flex-col gap-3 p-5">
              {isCreate ? (
                periods.length ? (
                  <PeriodsTable unit={unit}>
                    {periods.map((p) => (
                      <tr key={p.start}>
                        <td className="whitespace-nowrap px-3 py-2">{`${shortDate(p.start)} to ${shortDate(p.end)}`}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-end tabular-nums">
                          {formatFigure(isTeam ? teamSum : toNumber(draft?.figure ?? ''))}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-end tabular-nums">-</td>
                        <td className="whitespace-nowrap px-3 py-2 text-end tabular-nums">-</td>
                      </tr>
                    ))}
                  </PeriodsTable>
                ) : (
                  <div className="rounded-lg border border-dashed py-8 text-center text-sm font-medium">No periods yet</div>
                )
              ) : target ? (
                <PeriodsTable unit={unit}>
                  {target.periods.map((p) => {
                    const future = p.period_start > today;
                    return (
                      <tr key={p.id} className={p.is_current ? 'bg-primary/5' : undefined}>
                        <td className="whitespace-nowrap px-3 py-2">
                          <span className="inline-flex items-center gap-2">
                            {`${shortDate(p.period_start)} to ${shortDate(p.period_end)}`}
                            {p.is_current ? (
                              <Badge variant="primary" appearance="light" size="sm">
                                Current
                              </Badge>
                            ) : null}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-end">
                          <InlineFigure
                            value={p.target_value}
                            label={`Edit period figure, ${shortDate(p.period_start)}`}
                            editable={canEdit && !isTeam && !editing}
                            saving={patchPeriod.isPending}
                            onSave={async (next) => {
                              await patchPeriod.mutateAsync({ targetId: target.id, periodId: p.id, target_value: next });
                            }}
                          />
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-end tabular-nums">
                          {future ? '-' : formatFigure(p.achieved_value)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-end tabular-nums">
                          {future ? '-' : formatPct(p.achieved_pct)}
                        </td>
                      </tr>
                    );
                  })}
                </PeriodsTable>
              ) : null}
            </section>
          </Card>
        </TabsContent>

        {isTeam ? (
          <TabsContent value="agents">
            <Card>
              <section aria-label="Agents" className="flex flex-col gap-3 p-5">
                {isCreate && draft ? (
                  <NewTeamFigures
                    members={members}
                    hasTeam={!!draft.subjectId}
                    figures={draft.agentFigures}
                    unit={unit}
                    perWhat={split ? 'per period' : 'for the whole range'}
                    sum={teamSum}
                    onChange={(agentId, value) => set({ agentFigures: { ...draft.agentFigures, [agentId]: value } })}
                  />
                ) : target ? (
                  <TeamChildren
                    target={target}
                    editable={canEdit && !editing}
                    savingFigure={patchPeriod.isPending}
                    adding={addChild.isPending}
                    onFigure={(childId, periodId, value) =>
                      patchPeriod.mutateAsync({ targetId: childId, periodId, target_value: value }).then(() => undefined)
                    }
                    onAdd={(agentId) =>
                      void addChild
                        .mutateAsync({ targetId: target.id, sales_agent_id: agentId, target_value: 0 })
                        .catch(() => undefined)
                    }
                  />
                ) : null}
              </section>
            </Card>
          </TabsContent>
        ) : null}

        <TabsContent value="commission">
          <Card>
            <section aria-label="Commission" className="flex flex-col items-center gap-3 p-5">
              <div className="flex w-full flex-col items-center gap-3 rounded-lg border border-dashed py-8 text-center">
                <span className="text-sm font-medium">No commission</span>
                <Button variant="outline" size="sm" disabled>
                  <Plus className="size-4" />
                  Add tier
                </Button>
              </div>
            </section>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** The header card's left side: the number, the name, and the read-only meta strip. */
function RecordIdentity({
  target,
  canOpenAgent,
}: {
  target: SalesTargetDetail | undefined;
  canOpenAgent: boolean;
}) {
  if (!target) {
    return (
      <div className="flex min-w-0 flex-col gap-1.5">
        <h2 className="truncate text-lg font-semibold">New target</h2>
      </div>
    );
  }
  const isTeam = target.subject_kind === 'team';
  const subjectHref = isTeam
    ? `/sales/teams/${target.sales_team_id}`
    : canOpenAgent
      ? `/master-data-management/sales-agents/${target.sales_agent_id}`
      : null;
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{target.target_no}</span>
      <h2 className="truncate text-lg font-semibold" title={target.name}>
        {target.name}
      </h2>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="min-w-0 truncate">
          {'For '}
          {subjectHref ? (
            <Link href={subjectHref} className="text-primary hover:underline">
              {target.subject_label}
            </Link>
          ) : (
            target.subject_label
          )}
        </span>
        {target.parent ? (
          <span className="min-w-0 truncate">
            {'Part of '}
            <Link href={`/sales/targets/${target.parent.id}`} className="text-primary hover:underline">
              {target.parent.name}
            </Link>
          </span>
        ) : null}
        {isTeam ? (
          <span>{`${target.child_count} agent target${target.child_count === 1 ? '' : 's'}`}</span>
        ) : null}
        {target.created_at ? <span>Created {formatDateInMalaysia(target.created_at)}</span> : null}
        {target.updated_at ? <span>Updated {formatDateInMalaysia(target.updated_at)}</span> : null}
      </div>
    </div>
  );
}

function SetOnParent({ parent }: { parent: NonNullable<SalesTargetDetail['parent']> }) {
  return (
    <Link href={`/sales/targets/${parent.id}`} className="truncate text-sm text-primary hover:underline sm:col-span-3">
      {`Set on ${parent.name}`}
    </Link>
  );
}

/** One figure for every period, or "Varies by period". */
function figureSummary(target: SalesTargetDetail): string {
  const values = new Set(target.periods.map((p) => p.target_value));
  if (values.size !== 1) return 'Varies by period';
  const [only] = Array.from(values);
  return `${formatFigure(only)} ${target.periods.length === 1 ? 'for the whole range' : 'per period'}`;
}

function PeriodsTable({ unit, children }: { unit: string; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[32rem] text-sm">
        <thead className="bg-muted/40 text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-start font-medium">Period</th>
            <th className="px-3 py-2 text-end font-medium">{`Target (${unit})`}</th>
            <th className="px-3 py-2 text-end font-medium">Achieved</th>
            <th className="px-3 py-2 text-end font-medium">%</th>
          </tr>
        </thead>
        <tbody className="divide-y">{children}</tbody>
      </table>
    </div>
  );
}

/** What counts, in edit: Measure, Counts, Applies to, and the picker Applies to asks for. */
function WhatCountsEditor({
  draft,
  set,
  options,
  labels,
  fetchProducts,
}: {
  draft: Draft;
  set: (patch: Partial<Draft>) => void;
  options: SalesTargetOptions | undefined;
  labels: Map<string, string>;
  fetchProducts: (query: string) => Promise<SearchableMultiSelectOption[]>;
}) {
  // A picked value missing from the options (an inactive category, say) keeps its name.
  const withPicked = (base: { id: string; label: string }[], picked: string[]): SearchableMultiSelectOption[] => {
    const out = base.map((o) => ({ value: o.id, label: o.label }));
    for (const value of picked) {
      if (!out.some((o) => o.value === value) && labels.has(value)) out.push({ value, label: labels.get(value) as string });
    }
    return out;
  };
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Field label="Measure" htmlFor="target-measure">
        <SearchableSelect
          id="target-measure"
          value={draft.metric}
          onChange={(v) => v && set({ metric: v as TargetMetric })}
          options={METRIC_OPTIONS}
        />
      </Field>
      <Field label="Counts" htmlFor="target-counts">
        <SearchableSelect
          id="target-counts"
          value={draft.basis}
          onChange={(v) => v && set({ basis: v as TargetBasis })}
          options={COUNTS_OPTIONS}
        />
      </Field>
      <Field label="Applies to" htmlFor="target-applies">
        <SearchableSelect
          id="target-applies"
          value={draft.scope}
          onChange={(v) => v && set({ scope: v as TargetProductScope })}
          options={APPLIES_OPTIONS}
        />
      </Field>
      {draft.scope === 'categories' ? (
        <div className="sm:col-span-3">
          <Field label="Categories" htmlFor="target-categories">
            <SearchableMultiSelect
              id="target-categories"
              value={draft.categoryIds}
              onChange={(ids) => set({ categoryIds: ids })}
              options={withPicked(options?.categories ?? [], draft.categoryIds)}
              placeholder="Pick categories"
              emptyMessage="No categories."
              wrapOptions
            />
          </Field>
        </div>
      ) : null}
      {draft.scope === 'products' ? (
        <div className="sm:col-span-3">
          <Field label="Products" htmlFor="target-products">
            <SearchableMultiSelect
              id="target-products"
              value={draft.productIds}
              onChange={(ids) => set({ productIds: ids })}
              fetchOptions={fetchProducts}
              selectedOptions={draft.productIds.flatMap((value) =>
                labels.has(value) ? [{ value, label: labels.get(value) as string }] : [],
              )}
              placeholder="Search products"
              emptyMessage="No products match."
              wrapOptions
            />
          </Field>
        </div>
      ) : null}
      {draft.scope === 'brands' ? (
        <div className="sm:col-span-3">
          <Field label="Brands" htmlFor="target-brands">
            <SearchableMultiSelect
              id="target-brands"
              value={draft.brandIds}
              onChange={(ids) => set({ brandIds: ids })}
              options={withPicked(options?.brands ?? [], draft.brandIds)}
              placeholder="Pick brands"
              emptyMessage="No brands."
              wrapOptions
            />
          </Field>
        </div>
      ) : null}
    </div>
  );
}

/** A new team target: one figure per agent in the team during the dates, and their sum (T3). */
function NewTeamFigures({
  members,
  hasTeam,
  figures,
  unit,
  perWhat,
  sum,
  onChange,
}: {
  members: { sales_agent_id: string; label: string }[];
  hasTeam: boolean;
  figures: Record<string, string>;
  unit: string;
  perWhat: string;
  sum: number;
  onChange: (agentId: string, value: string) => void;
}) {
  if (!members.length) {
    return (
      <div className="rounded-lg border border-dashed py-8 text-center text-sm font-medium">
        {hasTeam ? 'No agents in this team during these dates' : 'Pick a team first'}
      </div>
    );
  }
  return (
    <>
      <div className="overflow-x-auto rounded-lg border">
        <table aria-label="Agent figures" className="w-full text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-start font-medium">Agent</th>
              <th className="w-44 px-3 py-2 text-end font-medium">{`Figure (${unit}) ${perWhat}`}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {members.map((m) => (
              <tr key={m.sales_agent_id}>
                <td className="max-w-0 truncate px-3 py-1.5" title={m.label}>
                  {m.label}
                </td>
                <td className="px-3 py-1.5">
                  <Input
                    type="number"
                    min={0}
                    step="any"
                    aria-label={`${m.label} figure`}
                    value={figures[m.sales_agent_id] ?? ''}
                    onChange={(e) => onChange(m.sales_agent_id, e.target.value)}
                    className="h-8 text-end"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2 text-sm">
        <span className="font-medium">Team target</span>
        <span className="tabular-nums">{formatFigure(sum)}</span>
      </div>
    </>
  );
}

/** A saved team target's agents: each child's figure in place, and Add figure for the rest. */
function TeamChildren({
  target,
  editable,
  savingFigure,
  adding,
  onFigure,
  onAdd,
}: {
  target: SalesTargetDetail;
  editable: boolean;
  savingFigure: boolean;
  adding: boolean;
  onFigure: (childId: string, periodId: string, value: number) => Promise<void>;
  onAdd: (agentId: string) => void;
}) {
  if (target.children.length === 0 && target.members_without_figure.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-8 text-center">
        <span className="text-sm font-medium">No agents in this team during these dates</span>
        <Link href={`/sales/teams/${target.sales_team_id}`} className="text-sm text-primary hover:underline">
          Open the team
        </Link>
      </div>
    );
  }
  return (
    <ul className="flex flex-col divide-y rounded-lg border">
      {target.children.map((child) => {
        const period =
          child.periods.find((cp) =>
            target.periods.some((tp) => tp.is_current && tp.period_start === cp.period_start),
          ) ?? child.periods[0];
        return (
          <li key={child.target_id} className="flex min-w-0 items-center justify-between gap-3 px-3 py-2">
            <Link
              href={`/sales/targets/${child.target_id}`}
              className="truncate text-sm text-primary hover:underline"
              title={child.label}
            >
              {child.label}
            </Link>
            {period ? (
              <InlineFigure
                value={period.target_value}
                label={`Edit figure for ${child.label}`}
                editable={editable && !!period.id}
                saving={savingFigure}
                onSave={(next) => onFigure(child.target_id, period.id as string, next)}
              />
            ) : null}
          </li>
        );
      })}
      {target.members_without_figure.map((m) => (
        <li key={m.sales_agent_id} className="flex min-w-0 items-center justify-between gap-3 px-3 py-2">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm" title={m.label}>
              {m.label}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">No figure yet</span>
          </span>
          {editable ? (
            <Button variant="outline" size="sm" disabled={adding} onClick={() => onAdd(m.sales_agent_id)}>
              <Plus className="size-4" />
              Add figure
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
