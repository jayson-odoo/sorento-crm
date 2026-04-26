'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchDashboardMetrics, type DashboardMetrics, type ScopeParam } from '../services/commercialPipelineApi';
import { PipelineScopeFilters } from '../components/PipelineScopeFilters';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';

export function PipelineDashboardClient() {
  const [scope, setScope] = React.useState<ScopeParam>('all');
  const [data, setData] = React.useState<DashboardMetrics | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setError(null);
    void (async () => {
      try {
        const m = await fetchDashboardMetrics(scope);
        if (!cancelled) setData(m);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scope]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!data) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    );
  }

  const pipelineTotal = Object.values(data.active_pipeline_value_by_stage).reduce(
    (a, b) => a + parseFloat(b || '0'),
    0,
  );

  return (
    <div className="space-y-6">
      <PipelineScopeFilters scope={scope} onScopeChange={setScope} />
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Open pipeline (tender value)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">
              {pipelineTotal.toLocaleString(undefined, { maximumFractionDigits: 2 })}{' '}
              {data.active_pipeline_currency ?? ''}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Tenders with multiple quotations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">{data.tenders_with_multiple_quotations}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">CRM tasks overdue</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">{data.crm_tasks_overdue}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Activity tasks overdue</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">{data.activity_tasks_overdue}</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Pipeline by stage (value)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {Object.entries(data.active_pipeline_value_by_stage).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <span className="text-muted-foreground">{k}</span>
                <span className="font-mono">{v}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Master quotation execution</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {Object.entries(data.master_quotation_count_by_execution).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <span className="text-muted-foreground">{k}</span>
                <span>{v}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Closest to closure</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {(data.closest_to_closure ?? []).map((row, idx) => {
            const r = row as Record<string, unknown>;
            return (
              <div key={idx} className="flex flex-wrap justify-between gap-2 border-b pb-2 last:border-0">
                <span className="font-medium">
                  {String(r.tender_code ?? '')} — {String(r.title ?? '')}
                </span>
                <span className="text-muted-foreground">{String(r.expected_close_on ?? '')}</span>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
