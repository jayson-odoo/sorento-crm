'use client';

import Link from 'next/link';
import { useReportRunParams } from '@/lib/report-params-context';
import type { ReportPeriod } from '@/services/reportService';

const pad = (n: number) => String(n).padStart(2, '0');

/** The two dates a report period stands for, or none when it is not one this link can read. */
function datesOf(period: unknown): { from: string; to: string } | null {
  const p = period as ReportPeriod | undefined;
  if (!p || typeof p !== 'object') return null;
  if (p.kind === 'custom') return { from: p.from, to: p.to };
  if (p.kind === 'year') return { from: `${p.year}-01-01`, to: `${p.year}-12-31` };
  if (p.kind === 'month_range') {
    const last = new Date(Date.UTC(p.year, p.to_month, 0)).getUTCDate();
    return { from: `${p.year}-${pad(p.from_month)}-01`, to: `${p.year}-${pad(p.to_month)}-${pad(last)}` };
  }
  return null;
}

/** Back to the leaderboard's Product view on Invoiced, carrying the report's own period, brand, category and company. */
export function ProductRankingLink() {
  const params = useReportRunParams();
  const search = new URLSearchParams({ basis: 'invoiced', by: 'product' });
  const dates = datesOf(params.period);
  if (dates) {
    search.set('period', 'custom');
    search.set('from', dates.from);
    search.set('to', dates.to);
  }
  for (const key of ['company', 'brand', 'category'] as const) {
    const value = params[key];
    for (const id of Array.isArray(value) ? value : []) search.append(key, id);
  }
  return (
    <Link href={`/sales/leaderboard?${search.toString()}`} className="mt-2 inline-block text-sm text-primary hover:underline">
      Product ranking
    </Link>
  );
}
