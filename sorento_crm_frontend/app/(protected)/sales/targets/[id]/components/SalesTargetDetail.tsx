'use client';

import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Check, LoaderCircleIcon, Plus, SquarePen, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia, todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import {
  useCreateTargetChild,
  usePatchSalesTarget,
  usePatchSalesTargetPeriod,
  useSalesTarget,
  useSalesTargetOptions,
  useTargetProductSearch,
} from '../../hooks/useSalesTargets';
import {
  METRIC_LABEL,
  SCOPE_LABEL,
  formatFigure,
  formatPct,
  scopeSummary,
  shortDate,
  splitSummary,
  unitOf,
} from '../../lib/format';
import type {
  SalesTargetDetail as Detail,
  SalesTargetUpdatePayload,
  TargetBasis,
  TargetMetric,
  TargetProductScope,
  TargetSplitUnit,
} from '../../types/salesTarget.types';

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

interface Draft {
  name: string;
  metric: TargetMetric;
  basis: TargetBasis;
  scope: TargetProductScope;
  categoryIds: string[];
  productIds: string[];
  start: string;
  end: string;
  split: boolean;
  every: string;
  unit: TargetSplitUnit | '';
}

function draftOf(target: Detail): Draft {
  return {
    name: target.name,
    metric: target.metric,
    basis: target.basis,
    scope: target.product_scope,
    categoryIds:
      target.product_scope === 'categories'
        ? target.scope.map((s) => s.id)
        : [],
    productIds:
      target.product_scope === 'products' ? target.scope.map((s) => s.id) : [],
    start: target.start_date,
    end: target.end_date,
    split: !!target.split_every,
    every: String(target.split_every ?? 1),
    unit: target.split_unit ?? 'month',
  };
}

/** Only what changed, so a rename of a child never touches what it follows. */
function changes(target: Detail, draft: Draft): SalesTargetUpdatePayload {
  const out: SalesTargetUpdatePayload = {};
  if (draft.name.trim() !== target.name) out.name = draft.name.trim();
  if (target.parent) return out;
  if (draft.metric !== target.metric) out.metric = draft.metric;
  if (draft.basis !== target.basis) out.basis = draft.basis;
  const before = draftOf(target);
  const scopeChanged =
    draft.scope !== target.product_scope ||
    draft.categoryIds.join() !== before.categoryIds.join() ||
    draft.productIds.join() !== before.productIds.join();
  if (scopeChanged) {
    out.product_scope = draft.scope;
    out.category_ids = draft.scope === 'categories' ? draft.categoryIds : [];
    out.product_ids = draft.scope === 'products' ? draft.productIds : [];
  }
  if (draft.start !== target.start_date) out.start_date = draft.start;
  if (draft.end !== target.end_date) out.end_date = draft.end;
  const every = draft.split && draft.unit ? Number(draft.every) : null;
  const unit = draft.split && draft.unit ? draft.unit : null;
  if (every !== target.split_every || unit !== target.split_unit) {
    out.split_every = every;
    out.split_unit = unit;
  }
  return out;
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      {htmlFor ? (
        <Label htmlFor={htmlFor} className="text-xs text-muted-foreground">
          {label}
        </Label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <div className="min-w-0 text-sm">{children}</div>
    </div>
  );
}

function SectionCard({
  label,
  action,
  children,
}: {
  label: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <section aria-label={label} className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{label}</h3>
          {action}
        </div>
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
      <Button
        variant="ghost"
        size="sm"
        mode="icon"
        aria-label="Save figure"
        disabled={saving}
        onClick={() => void commit()}
      >
        {saving ? (
          <LoaderCircleIcon className="size-3.5 animate-spin" />
        ) : (
          <Check className="size-3.5" />
        )}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        mode="icon"
        aria-label="Cancel"
        onClick={() => setEditing(false)}
      >
        <X className="size-3.5" />
      </Button>
    </span>
  );
}

/**
 * A target's own page, `/sales/targets/{id}` (UAC S1-23, S1-27, S1-28; J14; plan 3.9).
 *
 * VIEW AND EDIT ARE THE SAME LAYOUT. Sections in order, always rendered: Target, What counts,
 * Dates, Periods, Agents (a team target only), Commission. Edit swaps each value for its input
 * in place; nothing moves. The target number, the subject link, the parent, the agent count,
 * Created and Updated sit in the header's meta strip, never in a section.
 *
 * A child of a team target follows its parent (T3): only its name and its figures are its
 * own, so What counts and Dates stay read-only with "Set on <parent>". A team target's
 * periods are the sum of its agents' figures, so they are read-only here; each agent's figure
 * edits in the Agents section.
 *
 * The page wrapper decides what the reader may do: `readOnly`, the `secondary` header button
 * (Duplicate), the row menu `actions` (the deferred Delete), its countdown and the `pager`.
 */
export function SalesTargetDetail({
  id,
  readOnly = false,
  canOpenAgent = false,
  actions,
  pendingAction,
  secondary,
  pager,
}: {
  id: string;
  readOnly?: boolean;
  canOpenAgent?: boolean;
  actions?: RecordAction[];
  pendingAction?: ReactNode;
  /** A header button beside Edit (Duplicate, S1-23). */
  secondary?: ReactNode;
  pager?: ReactNode;
}) {
  const { data: target, isLoading, isError } = useSalesTarget(id);
  const patchPeriod = usePatchSalesTargetPeriod();
  const addChild = useCreateTargetChild();
  const patchHeader = usePatchSalesTarget();
  const [draft, setDraft] = useState<Draft | null>(null);
  const today = todayMalaysiaYyyyMmDd();

  const pending = useMemo(
    () => (target && draft ? changes(target, draft) : {}),
    [target, draft],
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }
  if (isError || !target) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <div className="text-sm font-semibold">Target not found</div>
      </Card>
    );
  }

  const isEditing = draft !== null;
  const isChild = !!target.parent;
  const isTeam = target.subject_kind === 'team';
  const unit = unitOf(target.metric);
  const canSave =
    isEditing &&
    draft.name.trim().length > 0 &&
    draft.end >= draft.start &&
    !patchHeader.isPending;

  const save = async () => {
    if (!canSave) return;
    if (Object.keys(pending).length === 0) {
      setDraft(null);
      return;
    }
    try {
      await patchHeader.mutateAsync({ targetId: target.id, ...pending });
      setDraft(null);
    } catch {
      // The hook toasted the reason; the edit stays open so nothing typed is lost.
    }
  };
  const set = (patch: Partial<Draft>) =>
    setDraft((d) => (d ? { ...d, ...patch } : d));

  const subjectHref = isTeam
    ? `/sales/teams/${target.sales_team_id}`
    : canOpenAgent
      ? `/master-data-management/sales-agents/${target.sales_agent_id}`
      : null;
  const agentCount = `${target.child_count} agent target${target.child_count === 1 ? '' : 's'}`;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 flex-col gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">
                {target.target_no}
              </span>
              <h2
                className="truncate text-lg font-semibold"
                title={target.name}
              >
                {target.name}
              </h2>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span className="min-w-0 truncate">
                  {'For '}
                  {subjectHref ? (
                    <Link
                      href={subjectHref}
                      className="text-primary hover:underline"
                    >
                      {target.subject_label}
                    </Link>
                  ) : (
                    target.subject_label
                  )}
                </span>
                {target.parent ? (
                  <span className="min-w-0 truncate">
                    {'Part of '}
                    <Link
                      href={`/sales/targets/${target.parent.id}`}
                      className="text-primary hover:underline"
                    >
                      {target.parent.name}
                    </Link>
                  </span>
                ) : null}
                {isTeam ? <span>{agentCount}</span> : null}
                {target.created_at ? (
                  <span>Created {formatDateInMalaysia(target.created_at)}</span>
                ) : null}
                {target.updated_at ? (
                  <span>Updated {formatDateInMalaysia(target.updated_at)}</span>
                ) : null}
              </div>
            </div>
            {isEditing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDraft(null)}
                  disabled={patchHeader.isPending}
                >
                  Cancel
                </Button>
                <Button size="sm" onClick={save} disabled={!canSave}>
                  {patchHeader.isPending ? (
                    <LoaderCircleIcon className="size-4 animate-spin" />
                  ) : null}
                  Save
                </Button>
              </div>
            ) : (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                {secondary}
                <DetailActions
                  pagerNode={pager}
                  actions={actions}
                  pendingAction={pendingAction}
                  primary={
                    readOnly ? undefined : (
                      <Button
                        variant="primary"
                        size="sm"
                        className="gap-1.5"
                        onClick={() => setDraft(draftOf(target))}
                      >
                        <SquarePen className="size-4" />
                        Edit
                      </Button>
                    )
                  }
                />
              </div>
            )}
          </div>
        </CardHeader>
      </Card>

      <SectionCard label="Target">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Target for">{isTeam ? 'Team' : 'Agent'}</Field>
          <Field label="Who">
            <span className="block truncate" title={target.subject_label}>
              {target.subject_label}
            </span>
          </Field>
          <Field
            label="Name"
            htmlFor={isEditing ? 'target-edit-name' : undefined}
          >
            {isEditing ? (
              <Input
                id="target-edit-name"
                value={draft.name}
                maxLength={120}
                onChange={(e) => set({ name: e.target.value })}
                className="h-8"
              />
            ) : (
              <span className="block truncate" title={target.name}>
                {target.name}
              </span>
            )}
          </Field>
        </div>
      </SectionCard>

      <SectionCard label="What counts">
        {isEditing && !isChild ? (
          <WhatCountsEditor draft={draft} set={set} />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Metric">{`${METRIC_LABEL[target.metric]} (${unit})`}</Field>
            <Field label="Counts">{target.counts_label}</Field>
            <Field label="Applies to">
              {target.product_scope === 'all'
                ? SCOPE_LABEL.all
                : scopeSummary(target.product_scope, target.scope.length)}
            </Field>
            {target.scope.length ? (
              <ul className="flex flex-col gap-1 sm:col-span-3">
                {target.scope.map((item) => (
                  <li
                    key={item.id}
                    className="truncate text-sm"
                    title={item.label}
                  >
                    {item.label}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </SectionCard>

      <SectionCard label="Dates">
        {isEditing && !isChild ? (
          <DatesEditor draft={draft} set={set} />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <Field label="Start and end date">
                {`${shortDate(target.start_date)} to ${shortDate(target.end_date)}`}
              </Field>
            </div>
            <Field label="Split">
              {splitSummary(target.split_every, target.split_unit)}
            </Field>
            {target.parent ? (
              <Link
                href={`/sales/targets/${target.parent.id}`}
                className="truncate text-sm text-primary hover:underline sm:col-span-3"
              >
                {`Set on ${target.parent.name}`}
              </Link>
            ) : null}
          </div>
        )}
      </SectionCard>

      <SectionCard label="Periods">
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
            <tbody className="divide-y">
              {target.periods.map((p) => {
                const future = p.period_start > today;
                return (
                  <tr
                    key={p.id}
                    className={p.is_current ? 'bg-primary/5' : undefined}
                  >
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
                        editable={!readOnly && !isTeam && !isEditing}
                        saving={patchPeriod.isPending}
                        onSave={async (next) => {
                          await patchPeriod.mutateAsync({
                            targetId: target.id,
                            periodId: p.id,
                            target_value: next,
                          });
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
            </tbody>
          </table>
        </div>
      </SectionCard>

      {isTeam ? (
        <SectionCard label="Agents">
          {target.children.length === 0 &&
          target.members_without_figure.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-8 text-center">
              <span className="text-sm font-medium">
                No agents in this team during these dates
              </span>
              <Link
                href={`/sales/teams/${target.sales_team_id}`}
                className="text-sm text-primary hover:underline"
              >
                Open the team
              </Link>
            </div>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border">
              {target.children.map((child) => {
                const period =
                  child.periods.find((cp) =>
                    target.periods.some(
                      (tp) =>
                        tp.is_current && tp.period_start === cp.period_start,
                    ),
                  ) ?? child.periods[0];
                return (
                  <li
                    key={child.target_id}
                    className="flex min-w-0 items-center justify-between gap-3 px-3 py-2"
                  >
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
                        editable={!readOnly && !isEditing && !!period.id}
                        saving={patchPeriod.isPending}
                        onSave={async (next) => {
                          await patchPeriod.mutateAsync({
                            targetId: child.target_id,
                            periodId: period.id as string,
                            target_value: next,
                          });
                        }}
                      />
                    ) : null}
                  </li>
                );
              })}
              {target.members_without_figure.map((m) => (
                <li
                  key={m.sales_agent_id}
                  className="flex min-w-0 items-center justify-between gap-3 px-3 py-2"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm" title={m.label}>
                      {m.label}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      No figure yet
                    </span>
                  </span>
                  {!readOnly ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={addChild.isPending || isEditing}
                      onClick={() =>
                        void addChild
                          .mutateAsync({
                            targetId: target.id,
                            sales_agent_id: m.sales_agent_id,
                            target_value: 0,
                          })
                          .catch(() => undefined)
                      }
                    >
                      <Plus className="size-4" />
                      Add figure
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      ) : null}

      <SectionCard label="Commission">
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-8 text-center">
          <span className="text-sm font-medium">No commission</span>
          <Button variant="outline" size="sm" disabled>
            <Plus className="size-4" />
            Add tier
          </Button>
        </div>
      </SectionCard>
    </div>
  );
}

/** What counts, in edit. Mounted only while editing, so the pickers' options load then. */
function WhatCountsEditor({
  draft,
  set,
}: {
  draft: Draft;
  set: (patch: Partial<Draft>) => void;
}) {
  const { data: options } = useSalesTargetOptions();
  const searchProducts = useTargetProductSearch();
  const categoryOptions = useMemo(
    () =>
      (options?.categories ?? []).map((c) => ({ value: c.id, label: c.label })),
    [options],
  );
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Field label="Metric" htmlFor="target-edit-metric">
        <SearchableSelect
          id="target-edit-metric"
          value={draft.metric}
          onChange={(v) => v && set({ metric: v as TargetMetric })}
          options={METRIC_OPTIONS}
        />
      </Field>
      <Field label="Counts" htmlFor="target-edit-counts">
        <SearchableSelect
          id="target-edit-counts"
          value={draft.basis}
          onChange={(v) => v && set({ basis: v as TargetBasis })}
          options={COUNTS_OPTIONS}
        />
      </Field>
      <Field label="Applies to" htmlFor="target-edit-applies">
        <SearchableSelect
          id="target-edit-applies"
          value={draft.scope}
          onChange={(v) => v && set({ scope: v as TargetProductScope })}
          options={APPLIES_OPTIONS}
        />
      </Field>
      {draft.scope === 'categories' ? (
        <div className="sm:col-span-3">
          <Field label="Categories" htmlFor="target-edit-categories">
            <SearchableMultiSelect
              id="target-edit-categories"
              value={draft.categoryIds}
              onChange={(ids) => set({ categoryIds: ids })}
              options={categoryOptions}
              placeholder="Pick categories"
              wrapOptions
            />
          </Field>
        </div>
      ) : null}
      {draft.scope === 'products' ? (
        <div className="sm:col-span-3">
          <Field label="Products" htmlFor="target-edit-products">
            <SearchableMultiSelect
              id="target-edit-products"
              value={draft.productIds}
              onChange={(ids) => set({ productIds: ids })}
              fetchOptions={searchProducts}
              placeholder="Search products"
              wrapOptions
            />
          </Field>
        </div>
      ) : null}
    </div>
  );
}

/** Dates, in edit: the range and the optional split. */
function DatesEditor({
  draft,
  set,
}: {
  draft: Draft;
  set: (patch: Partial<Draft>) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className="sm:col-span-2">
        <Field label="Start and end date" htmlFor="target-edit-dates">
          <DateRangePicker
            id="target-edit-dates"
            aria-label="Start and end date"
            from={draft.start || null}
            to={draft.end || null}
            onChange={({ from, to }) =>
              set({ start: from ?? '', end: to ?? '' })
            }
            className="sm:w-72"
          />
        </Field>
      </div>
      <Field label="Split">
        <div className="flex flex-wrap items-center gap-2">
          <Switch
            aria-label="Split"
            checked={draft.split}
            onCheckedChange={(on) => set({ split: on })}
          />
          {draft.split ? (
            <>
              <Label htmlFor="target-edit-every" className="text-xs">
                Every
              </Label>
              <Input
                id="target-edit-every"
                type="number"
                min={1}
                max={99}
                value={draft.every}
                onChange={(e) => set({ every: e.target.value })}
                className="h-8 w-16"
              />
              <SearchableSelect
                id="target-edit-unit"
                value={draft.unit}
                onChange={(v) =>
                  v
                    ? set({ unit: v as TargetSplitUnit })
                    : set({ split: false, unit: 'month' })
                }
                options={UNIT_OPTIONS}
                clearable
                className="w-28"
              />
            </>
          ) : null}
        </div>
      </Field>
    </div>
  );
}
