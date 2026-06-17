'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Container } from '@/components/common/container';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  getKpiSummary,
  getKpiLeaderboard,
  getKpiTasks,
  type KpiScope,
} from './slaKpiService';

const fmtPct = (v: number | null) => (v == null ? '—' : `${v}%`);
const fmtHrs = (v: number | null) => (v == null ? '—' : `${v}h`);

function MetricCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="text-sm text-muted-foreground">{label}</div>
        <div className="text-2xl font-semibold">{value}</div>
        {sub ? <div className="text-xs text-muted-foreground mt-1">{sub}</div> : null}
      </CardContent>
    </Card>
  );
}

export default function SLAKpiDashboardPage() {
  const [scope, setScope] = useState<KpiScope>('all');
  const [page, setPage] = useState(1);
  const limit = 25;

  const summaryQ = useQuery({ queryKey: ['kpi-summary', scope], queryFn: () => getKpiSummary(scope) });
  const leaderQ = useQuery({ queryKey: ['kpi-leaderboard', scope], queryFn: () => getKpiLeaderboard(scope) });
  const tasksQ = useQuery({ queryKey: ['kpi-tasks', scope, page], queryFn: () => getKpiTasks(scope, page, limit) });

  const s = summaryQ.data;

  return (
    <Container>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">SLA KPI Dashboard</h1>
          <Select value={scope} onValueChange={(v) => { setScope(v as KpiScope); setPage(1); }}>
            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All SLA</SelectItem>
              <SelectItem value="form">Form SLA</SelectItem>
              <SelectItem value="conversation">Conversation SLA</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Summary cards */}
        {summaryQ.isLoading ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
          </div>
        ) : s ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <MetricCard label="Opened" value={s.opened} />
            <MetricCard label="Responded" value={s.responded} />
            <MetricCard label="Resolved" value={s.resolved} />
            <MetricCard label="Escalated" value={s.escalated} sub={`${s.escalated_manual} manual · ${s.escalated_auto} auto`} />
            <MetricCard label="Response met" value={fmtPct(s.pct_response_met)} sub={`${s.response_met} met · ${s.response_breach} breach`} />
            <MetricCard label="Resolution met" value={fmtPct(s.pct_resolution_met)} sub={`${s.resolution_met} met · ${s.resolution_breach} breach`} />
            <MetricCard label="Avg response" value={fmtHrs(s.avg_response_time_hours)} sub={`median ${fmtHrs(s.median_response_time_hours)}`} />
            <MetricCard label="Avg resolution" value={fmtHrs(s.avg_resolution_time_hours)} sub={`median ${fmtHrs(s.median_resolution_time_hours)}`} />
          </div>
        ) : (
          <Card><CardContent className="py-6 text-sm text-muted-foreground">No KPI data for this scope.</CardContent></Card>
        )}

        {/* Leaderboard */}
        <Card>
          <CardHeader className="py-4"><CardTitle className="text-base">Assignee leaderboard</CardTitle></CardHeader>
          <CardContent className="py-2">
            {leaderQ.isLoading ? (
              <Skeleton className="h-32 w-full" />
            ) : (leaderQ.data?.length ?? 0) === 0 ? (
              <div className="py-4 text-sm text-muted-foreground">No assignees in this scope.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="py-2 pr-4">Assignee</th>
                      <th className="py-2 pr-4">Total</th>
                      <th className="py-2 pr-4">Resolved</th>
                      <th className="py-2 pr-4">Avg resp</th>
                      <th className="py-2 pr-4">Avg reso</th>
                      <th className="py-2 pr-4">Breaches</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderQ.data!.map((r) => (
                      <tr key={r.assignee_id} className="border-t">
                        <td className="py-2 pr-4 truncate" title={r.assignee_name}>{r.assignee_name}</td>
                        <td className="py-2 pr-4">{r.total}</td>
                        <td className="py-2 pr-4">{r.resolved}</td>
                        <td className="py-2 pr-4">{fmtHrs(r.avg_response_time_hours)}</td>
                        <td className="py-2 pr-4">{fmtHrs(r.avg_resolution_time_hours)}</td>
                        <td className="py-2 pr-4">
                          {r.breach_count > 0 ? <Badge variant="destructive">{r.breach_count}</Badge> : '0'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Per-task drill-down */}
        <Card>
          <CardHeader className="py-4"><CardTitle className="text-base">Tasks</CardTitle></CardHeader>
          <CardContent className="py-2">
            {tasksQ.isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : (tasksQ.data?.data.length ?? 0) === 0 ? (
              <div className="py-4 text-sm text-muted-foreground">No tasks in this scope.</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th className="py-2 pr-4">Type</th>
                        <th className="py-2 pr-4">Tier</th>
                        <th className="py-2 pr-4">Owner</th>
                        <th className="py-2 pr-4">Resp</th>
                        <th className="py-2 pr-4">Reso</th>
                        <th className="py-2 pr-4">Esc (m/a)</th>
                        <th className="py-2 pr-4">Resp met</th>
                        <th className="py-2 pr-4">Reso met</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tasksQ.data!.data.map((t) => (
                        <tr key={t.tracking_id} className="border-t">
                          <td className="py-2 pr-4">{(t.source_entity_type || 'conversation').replace('_', ' ')}</td>
                          <td className="py-2 pr-4">{t.current_tier}</td>
                          <td className="py-2 pr-4 truncate" title={t.assignee_name}>{t.assignee_name}</td>
                          <td className="py-2 pr-4">{fmtHrs(t.response_time_hours)}</td>
                          <td className="py-2 pr-4">{fmtHrs(t.resolution_time_hours)}</td>
                          <td className="py-2 pr-4">{t.escalations_manual}/{t.escalations_auto}</td>
                          <td className="py-2 pr-4">{t.response_met ? '✓' : '—'}</td>
                          <td className="py-2 pr-4">{t.resolution_met ? '✓' : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between pt-3">
                  <span className="text-xs text-muted-foreground">
                    {tasksQ.data!.total} task{tasksQ.data!.total === 1 ? '' : 's'}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
                    <span className="text-xs">Page {page}</span>
                    <Button variant="outline" size="sm" disabled={page * limit >= tasksQ.data!.total} onClick={() => setPage((p) => p + 1)}>Next</Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </Container>
  );
}
