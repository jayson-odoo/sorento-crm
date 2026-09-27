'use client';

/**
 * My target, at the top of the portal's Sales Opportunity kind (fix lane round 2, F2; mockup
 * and layout choice on PR #1296, "Mockup: my target on the portal").
 *
 * One card per active target of the logging agent, trimmed per the owner's notes on the
 * mockup ("the wording too long already", "make it structured and simple"): four labelled
 * figures (target, achieved, open before the end date, short), a timeline from the start to
 * the end date with today marked and each open opportunity pinned at its close date, one bar
 * towards the target, and the opportunities themselves. No sentence, no legend: the figures'
 * own colour dots are the legend.
 */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { getMyTargets, type MyTarget, type MyTargets } from '../lib/my-target-service';
import { portalDetailPath } from '../lib/portal-paths';

function num(value: string | number | null | undefined): number {
  const n = typeof value === 'number' ? value : Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

const WHOLE = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const TWO_DP = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "RM 40,000" for an amount target (cents only when there are any), "120" for quantity. */
export function formatTargetValue(value: string | number, metric: string): string {
  const n = num(value);
  const text = Number.isInteger(n) ? WHOLE.format(n) : TWO_DP.format(n);
  return metric === 'amount' ? `RM ${text}` : text;
}

/** "31 Oct 2026", read as a calendar date (no timezone shift). */
export function formatTargetDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

function dayNumber(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
}

/** Where a date sits between the start and the end date, 0 to 100. */
function position(iso: string, start: string, end: string): number {
  const span = dayNumber(end) - dayNumber(start);
  if (span <= 0) return 100;
  return Math.min(100, Math.max(0, ((dayNumber(iso) - dayNumber(start)) / span) * 100));
}

function countsLine(target: MyTarget): string {
  const metric = target.metric === 'amount' ? 'Amount' : 'Quantity';
  const scope =
    target.product_scope === 'all' || target.scope_labels.length === 0
      ? 'all products'
      : target.scope_labels.join(', ');
  return `${metric}, ${target.counts_label.toLowerCase()}, ${scope}`;
}

function Stat({ id, label, value, dot }: { id: string; label: string; value: string; dot?: string }) {
  return (
    <div data-testid={`target-stat-${id}`} className="min-w-0">
      <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {dot ? <i aria-hidden className={`inline-block size-2 rounded-full ${dot}`} /> : null}
        {label}
      </dt>
      <dd className="truncate text-sm font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function TargetCard({ target, today, slug }: { target: MyTarget; today: string; slug?: string }) {
  const total = num(target.target_value);
  const achievedPct = total > 0 ? Math.min(100, (num(target.achieved_value) / total) * 100) : 100;
  const pipelinePct =
    total > 0 ? Math.min(100 - achievedPct, (num(target.pipeline_value) / total) * 100) : 0;
  const todayPct = position(today, target.start_date, target.end_date);
  const v = (x: string | number) => formatTargetValue(x, target.metric);
  const count = target.opportunities.length;

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold" title={target.name}>
              {target.name}
            </h3>
            <p className="truncate text-xs text-muted-foreground">{countsLine(target)}</p>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">
            By {formatTargetDate(target.end_date)}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat id="target" label="Target" value={v(target.target_value)} />
          <Stat id="achieved" label="Achieved" value={v(target.achieved_value)} dot="bg-primary" />
          <Stat id="open" label={`Open (${count})`} value={v(target.pipeline_value)} dot="bg-primary/40" />
          <Stat id="short" label="Short" value={v(target.short_value)} />
        </dl>

        <div className="flex h-2 overflow-hidden rounded-full bg-muted">
          <div className="bg-primary" style={{ width: `${achievedPct}%` }} />
          <div className="bg-primary/40" style={{ width: `${pipelinePct}%` }} />
        </div>

        <div>
          <div className="relative h-4">
            <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
            <div
              className="absolute left-0 top-1/2 h-px -translate-y-1/2 bg-primary"
              style={{ width: `${todayPct}%` }}
            />
            <div
              data-testid="target-today"
              className="absolute inset-y-0 w-px bg-primary"
              style={{ left: `${todayPct}%` }}
              title={`Today ${formatTargetDate(today)}`}
            />
            {target.opportunities.map((o) => (
              <span
                key={o.id}
                data-testid="target-pin"
                className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/40 ring-2 ring-background"
                style={{ left: `${position(o.expected_close_date, target.start_date, target.end_date)}%` }}
                title={`${o.opportunity_no} ${v(o.value)}, ${formatTargetDate(o.expected_close_date)}`}
                aria-label={`${o.opportunity_no} ${v(o.value)}, closes ${formatTargetDate(o.expected_close_date)}`}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between text-xs text-muted-foreground">
            <span>{formatTargetDate(target.start_date)}</span>
            <span>{formatTargetDate(target.end_date)}</span>
          </div>
        </div>

        {count > 0 ? (
          <ul className="divide-y border-t text-sm">
            {target.opportunities.map((o) => (
              <li key={o.id}>
                <Link
                  href={portalDetailPath('sales_opportunity', o.id, slug)}
                  className="flex items-center justify-between gap-3 py-2"
                >
                  <span className="min-w-0">
                    <span className="block text-xs text-muted-foreground">{o.opportunity_no}</span>
                    <span className="block truncate" title={o.title}>
                      {o.title}
                    </span>
                  </span>
                  <span className="shrink-0 text-right tabular-nums">
                    <span className="block">{v(o.value)}</span>
                    <span className="block text-xs text-muted-foreground">
                      {formatTargetDate(o.expected_close_date)}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function MyTargetPanel({ slug }: { slug?: string }) {
  const [data, setData] = useState<MyTargets | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMyTargets()
      .then((body) => {
        if (!cancelled) setData(body);
      })
      .catch(() => {
        // The panel is an aid beside the list: a failure leaves the list usable, not an
        // error screen.
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data || data.targets.length === 0) return null;
  return (
    <section aria-label="My target" className="space-y-3">
      {data.targets.map((t) => (
        <TargetCard key={t.target_id} target={t} today={data.today} slug={slug} />
      ))}
    </section>
  );
}
