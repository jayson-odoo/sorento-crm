'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Filter,
  Layers,
  RotateCcw,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { formatDateTime, getInitials, timeAgo } from '@/lib/helpers';
import { useActivityFeed } from '../hooks/useActivityFeed';
import type {
  ActivityAction,
  ActivityEntityType,
  ActivityItem,
  ActivityMockState,
} from '../types/activity.types';
import {
  ACTION_OPTIONS,
  ENTITY_TYPE_OPTIONS,
  actionMeta,
  entityBadgeVariant,
  entityTypeLabel,
  groupByDay,
} from './activityPresenters';

const ANY = '__any__';

export default function ActivityTimeline() {
  // PHASE-1 demo knob — lets reviewers exercise every UI state without a backend.
  const [mockState, setMockState] = useState<ActivityMockState>('success');

  const [entityTypes, setEntityTypes] = useState<ActivityEntityType[]>([]);
  const [action, setAction] = useState<string>(ANY);
  const [userId, setUserId] = useState<string>(ANY);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [q, setQ] = useState('');

  const { data, isLoading, isError, error, refetch, isFetching } =
    useActivityFeed({
      mockState,
      entity_types: entityTypes,
      action: action !== ANY ? (action as ActivityAction) : undefined,
      user_id: userId !== ANY ? userId : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      q: q.trim() || undefined,
    });

  const actors = data?.actors ?? [];
  const groups = useMemo(() => groupByDay(data?.items ?? []), [data?.items]);

  const activeFilterCount =
    entityTypes.length +
    (action !== ANY ? 1 : 0) +
    (userId !== ANY ? 1 : 0) +
    (dateFrom ? 1 : 0) +
    (dateTo ? 1 : 0);
  const hasAnyFilter = activeFilterCount > 0 || q.trim().length > 0;

  const resetFilters = () => {
    setEntityTypes([]);
    setAction(ANY);
    setUserId(ANY);
    setDateFrom('');
    setDateTo('');
    setQ('');
  };

  const toggleEntityType = (type: ActivityEntityType) => {
    setEntityTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  };

  return (
    <div className="space-y-4">
      <FilterBar
        q={q}
        onQChange={setQ}
        entityTypes={entityTypes}
        onToggleEntityType={toggleEntityType}
        action={action}
        onActionChange={setAction}
        userId={userId}
        onUserChange={setUserId}
        actors={actors}
        dateFrom={dateFrom}
        onDateFromChange={setDateFrom}
        dateTo={dateTo}
        onDateToChange={setDateTo}
        activeFilterCount={activeFilterCount}
        onReset={resetFilters}
        onRefresh={() => void refetch()}
        isRefreshing={isFetching && !isLoading}
        mockState={mockState}
        onMockStateChange={setMockState}
      />

      {isLoading ? (
        <TimelineSkeleton />
      ) : isError ? (
        <ErrorCard
          message={error instanceof Error ? error.message : 'Please try again.'}
          onRetry={() => void refetch()}
        />
      ) : groups.length === 0 ? (
        <EmptyState hasFilters={hasAnyFilter} onReset={resetFilters} />
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <section key={group.date_key} className="space-y-3">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold">{group.label}</h2>
                <span className="text-xs text-muted-foreground">
                  {group.items.length}{' '}
                  {group.items.length === 1 ? 'event' : 'events'}
                </span>
                <div className="h-px flex-1 bg-border" />
              </div>
              <ol className="relative space-y-4 ps-4 before:absolute before:inset-y-1 before:start-[5px] before:w-px before:bg-border">
                {group.items.map((item, idx) => (
                  <TimelineRow
                    key={item.id}
                    item={item}
                    traceGroupSize={countTrace(group.items, item.trace_id)}
                    isTraceContinuation={
                      idx > 0 &&
                      !!item.trace_id &&
                      group.items[idx - 1].trace_id === item.trace_id
                    }
                  />
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function countTrace(items: ActivityItem[], traceId?: string | null): number {
  if (!traceId) return 0;
  return items.filter((i) => i.trace_id === traceId).length;
}

/* -------------------------------------------------------------------------- */
/* Filter bar                                                                 */
/* -------------------------------------------------------------------------- */

interface FilterBarProps {
  q: string;
  onQChange: (v: string) => void;
  entityTypes: ActivityEntityType[];
  onToggleEntityType: (t: ActivityEntityType) => void;
  action: string;
  onActionChange: (v: string) => void;
  userId: string;
  onUserChange: (v: string) => void;
  actors: { id: string; name: string }[];
  dateFrom: string;
  onDateFromChange: (v: string) => void;
  dateTo: string;
  onDateToChange: (v: string) => void;
  activeFilterCount: number;
  onReset: () => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  mockState: ActivityMockState;
  onMockStateChange: (v: ActivityMockState) => void;
}

function FilterBar(props: FilterBarProps) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center">
        {/* Search */}
        <div className="relative w-full lg:max-w-xs">
          <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search activity..."
            value={props.q}
            onChange={(e) => props.onQChange(e.target.value)}
            className="ps-9"
          />
          {props.q && (
            <Button
              mode="icon"
              variant="dim"
              className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
              onClick={() => props.onQChange('')}
            >
              <X />
            </Button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Entity types multi-select */}
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm">
                <Layers className="size-4" />
                Entity types
                {props.entityTypes.length > 0 && (
                  <Badge variant="primary" appearance="light" size="sm">
                    {props.entityTypes.length}
                  </Badge>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-56 p-2">
              <div className="max-h-72 space-y-0.5 overflow-auto">
                {ENTITY_TYPE_OPTIONS.map((opt) => {
                  const checked = props.entityTypes.includes(opt.value);
                  return (
                    <label
                      key={opt.value}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={() =>
                          props.onToggleEntityType(opt.value)
                        }
                      />
                      {opt.label}
                    </label>
                  );
                })}
              </div>
            </PopoverContent>
          </Popover>

          {/* Action */}
          <Select value={props.action} onValueChange={props.onActionChange}>
            <SelectTrigger size="sm" className="w-[130px]">
              <Filter className="size-4 text-muted-foreground" />
              <SelectValue placeholder="Action" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>All actions</SelectItem>
              {ACTION_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* User */}
          <Select value={props.userId} onValueChange={props.onUserChange}>
            <SelectTrigger size="sm" className="w-[150px]">
              <SelectValue placeholder="User" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>All users</SelectItem>
              {props.actors.map((actor) => (
                <SelectItem key={actor.id} value={actor.id}>
                  {actor.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Date range */}
          <div className="flex items-center gap-1.5">
            <Input
              type="date"
              aria-label="From date"
              value={props.dateFrom}
              onChange={(e) => props.onDateFromChange(e.target.value)}
              className="h-8 w-[140px]"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <Input
              type="date"
              aria-label="To date"
              value={props.dateTo}
              onChange={(e) => props.onDateToChange(e.target.value)}
              className="h-8 w-[140px]"
            />
          </div>

          {props.activeFilterCount > 0 && (
            <Button variant="ghost" size="sm" onClick={props.onReset}>
              <RotateCcw className="size-4" />
              Reset
            </Button>
          )}
        </div>

        <div className="flex items-center gap-2 lg:ms-auto">
          {/* PHASE-1 demo state switcher — remove when the real endpoint lands. */}
          <Select
            value={props.mockState}
            onValueChange={(v) => props.onMockStateChange(v as ActivityMockState)}
          >
            <SelectTrigger size="sm" className="w-[140px]">
              <SlidersHorizontal className="size-4 text-muted-foreground" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="success">Demo: data</SelectItem>
              <SelectItem value="loading">Demo: loading</SelectItem>
              <SelectItem value="empty">Demo: empty</SelectItem>
              <SelectItem value="error">Demo: error</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={props.onRefresh}
            disabled={props.isRefreshing}
          >
            <RotateCcw
              className={props.isRefreshing ? 'size-4 animate-spin' : 'size-4'}
            />
            Refresh
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Timeline row                                                               */
/* -------------------------------------------------------------------------- */

function TimelineRow({
  item,
  traceGroupSize,
  isTraceContinuation,
}: {
  item: ActivityItem;
  traceGroupSize: number;
  isTraceContinuation: boolean;
}) {
  const action = actionMeta(item.action);
  return (
    <li className="relative ps-6">
      {/* Timeline dot */}
      <span
        className={`absolute start-0 top-1.5 size-2.5 rounded-full ring-4 ring-background ${action.dotClass}`}
        aria-hidden
      />
      <Card className="shadow-none">
        <CardContent className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant={entityBadgeVariant(item.entity_type)}
                appearance="light"
                size="sm"
              >
                {entityTypeLabel(item.entity_type)}
              </Badge>
              {item.entity_href ? (
                <Link
                  href={item.entity_href}
                  className="truncate font-medium hover:underline"
                  title={item.entity_label}
                >
                  {item.entity_label}
                </Link>
              ) : (
                <span
                  className="truncate font-medium"
                  title={item.entity_label}
                >
                  {item.entity_label}
                </span>
              )}
              <span className={`text-sm font-medium ${action.textClass}`}>
                {action.label}
              </span>
              {!isTraceContinuation && traceGroupSize > 1 && (
                <Badge variant="secondary" appearance="light" size="sm">
                  <Layers className="size-3" />
                  {traceGroupSize} in one action
                </Badge>
              )}
            </div>

            {item.summary && (
              <p
                className="truncate text-sm text-muted-foreground"
                title={item.summary}
              >
                {item.summary}
              </p>
            )}

            {item.changes && item.changes.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {item.changes.map((c, i) => (
                  <span
                    key={`${c.field}-${i}`}
                    className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs"
                  >
                    <span className="font-medium">{c.field}:</span>
                    <span className="text-muted-foreground line-through">
                      {c.from ?? '—'}
                    </span>
                    <span aria-hidden>→</span>
                    <span>{c.to ?? '—'}</span>
                  </span>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2 pt-1">
              <Avatar className="size-5">
                <AvatarFallback className="text-[10px]">
                  {getInitials(item.actor_name || 'System', 2) || 'S'}
                </AvatarFallback>
              </Avatar>
              <span className="text-xs text-muted-foreground">
                {item.actor_name || 'System'}
              </span>
            </div>
          </div>

          <div className="shrink-0 text-start sm:text-end">
            <div className="text-xs font-medium">
              {timeAgo(item.changed_at)}
            </div>
            <div
              className="text-xs text-muted-foreground"
              title={formatDateTime(new Date(item.changed_at))}
            >
              {formatDateTime(new Date(item.changed_at))}
            </div>
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

/* -------------------------------------------------------------------------- */
/* States                                                                     */
/* -------------------------------------------------------------------------- */

function TimelineSkeleton() {
  return (
    <div className="space-y-6">
      {[0, 1].map((section) => (
        <div key={section} className="space-y-3">
          <Skeleton className="h-4 w-28" />
          <div className="space-y-4 ps-4">
            {[0, 1, 2].map((row) => (
              <Card key={row} className="shadow-none">
                <CardContent className="flex items-start justify-between gap-3 p-3">
                  <div className="w-full space-y-2">
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-5 w-20" />
                      <Skeleton className="h-4 w-40" />
                    </div>
                    <Skeleton className="h-4 w-64" />
                    <Skeleton className="h-4 w-24" />
                  </div>
                  <Skeleton className="h-4 w-24 shrink-0" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({
  hasFilters,
  onReset,
}: {
  hasFilters: boolean;
  onReset: () => void;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center gap-3 p-12 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-muted">
          <Layers className="size-6 text-muted-foreground" />
        </div>
        <div>
          <p className="font-medium">
            {hasFilters
              ? 'No activity for these filters'
              : 'No activity recorded yet'}
          </p>
          <p className="text-sm text-muted-foreground">
            {hasFilters
              ? 'Try widening the date range or clearing filters.'
              : 'System activity will appear here as records change.'}
          </p>
        </div>
        {hasFilters && (
          <Button variant="outline" size="sm" onClick={onReset}>
            <RotateCcw className="size-4" />
            Reset filters
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function ErrorCard({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center gap-3 p-12 text-center">
        <p className="font-medium text-destructive">
          Failed to load activity timeline.
        </p>
        <p className="text-sm text-muted-foreground">{message}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCcw className="size-4" />
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}
