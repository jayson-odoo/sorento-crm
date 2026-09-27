'use client';

/**
 * My target, at the top of the portal's Sales Opportunity kind (fix lane round 2, F2; mockup
 * and layout choice on PR #1296, "Mockup: my target on the portal").
 *
 * One card per active target of the logging agent: a plain sentence (achieved of target by
 * the end date, the open opportunities closing before then and the gap left if they are all
 * won), a timeline from the start date to the end date with today marked and each open
 * opportunity pinned at its expected close date, a bar towards the target (achieved solid,
 * open opportunities striped, the rest short), and the opportunities themselves.
 *
 * Time and value get a row each: a date axis cannot also show how much an opportunity is
 * worth.
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

/** The plain-words line the owner asked for (PR #1296, F2). */
export function targetSentence(target: MyTarget): string {
  const v = (x: string | number) => formatTargetValue(x, target.metric);
  const count = target.opportunities.length;
  const head = `${v(target.achieved_value)} achieved of ${v(target.target_value)} by ${formatTargetDate(target.end_date)}`;
  if (num(target.gap_value) <= 0) return `${head}; target reached`;
  if (count === 0) {
    return `${head}; no open opportunities before then; still ${v(target.gap_value)} short`;
  }
  const opportunities = `${count} open ${count === 1 ? 'opportunity' : 'opportunities'} worth ${v(target.pipeline_value)} before then`;
  const tail =
    num(target.short_value) <= 0
      ? `target reached if ${count === 1 ? 'it is' : 'they are all'} won`
      : `still ${v(target.short_value)} short`;
  return `${head}; ${opportunities}; ${tail}`;
}

function countsLine(target: MyTarget): string {
  const metric = target.metric === 'amount' ? 'Amount' : 'Quantity';
  const scope =
    target.product_scope === 'all' || target.scope_labels.length === 0
      ? 'all products'
      : target.scope_labels.join(', ');
  return `${metric}, ${target.counts_label.toLowerCase()}, ${scope}`;
}

function TargetCard({ target, today, slug }: { target: MyTarget; today: string; slug?: string }) {
  const total = num(target.target_value);
  const achievedPct = total > 0 ? Math.min(100, (num(target.achieved_value) / total) * 100) : 100;
  const pipelinePct =
    total > 0 ? Math.min(100 - achievedPct, (num(target.pipeline_value) / total) * 100) : 0;
  const todayPct = position(today, target.start_date, target.end_date);
  const v = (x: string | number) => formatTargetValue(x, target.metric);

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
          <h3 className="text-base font-semibold break-words">{target.name}</h3>
          <span className="text-xs text-muted-foreground">{countsLine(target)}</span>
        </div>
        <p className="text-sm">{targetSentence(target)}</p>

        <div>
          <div className="relative h-9 rounded-md border bg-muted">
            <div
              className="absolute inset-y-0 left-0 rounded-l-md bg-primary/15"
              style={{ width: `${todayPct}%` }}
            />
            <div
              data-testid="target-today"
              className="absolute -inset-y-1 w-0.5 bg-primary"
              style={{ left: `${todayPct}%` }}
              title={`Today ${formatTargetDate(today)}`}
            />
            {target.opportunities.map((o) => (
              <span
                key={o.id}
                data-testid="target-pin"
                className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-warning ring-1 ring-warning"
                style={{ left: `${position(o.expected_close_date, target.start_date, target.end_date)}%` }}
                title={`${o.opportunity_no} ${v(o.value)}, ${formatTargetDate(o.expected_close_date)}`}
                aria-label={`${o.opportunity_no} ${v(o.value)}, closes ${formatTargetDate(o.expected_close_date)}`}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between gap-2 text-xs text-muted-foreground">
            <span>{formatTargetDate(target.start_date)}</span>
            <span className="text-primary">Today {formatTargetDate(today)}</span>
            <span>{formatTargetDate(target.end_date)}</span>
          </div>
        </div>

        <div>
          <div className="flex h-3.5 overflow-hidden rounded-full border bg-muted">
            <div className="bg-success" style={{ width: `${achievedPct}%` }} />
            <div
              className="text-warning"
              style={{
                width: `${pipelinePct}%`,
                backgroundImage:
                  'repeating-linear-gradient(45deg, currentColor 0 4px, transparent 4px 8px)',
              }}
            />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
            <span className="flex items-center gap-1">
              <i className="inline-block size-2.5 rounded-sm bg-success" />
              Achieved {v(target.achieved_value)}
            </span>
            <span className="flex items-center gap-1">
              <i className="inline-block size-2.5 rounded-sm bg-warning" />
              Open {v(target.pipeline_value)}
            </span>
            {num(target.short_value) > 0 ? (
              <span className="flex items-center gap-1">
                <i className="inline-block size-2.5 rounded-sm border bg-muted" />
                Short {v(target.short_value)}
              </span>
            ) : null}
          </div>
        </div>

        {target.opportunities.length > 0 ? (
          <ul className="divide-y border-t text-sm">
            {target.opportunities.map((o) => (
              <li key={o.id}>
                <Link
                  href={portalDetailPath('sales_opportunity', o.id, slug)}
                  className="flex items-start justify-between gap-2 py-2"
                >
                  <span className="min-w-0">
                    <span className="block font-medium">{o.opportunity_no}</span>
                    <span className="block truncate text-xs text-muted-foreground" title={o.title}>
                      {o.title}
                      {o.customer_or_prospect ? `, ${o.customer_or_prospect}` : ''}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
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
