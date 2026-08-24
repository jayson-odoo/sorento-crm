'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApexOptions } from 'apexcharts';
import dynamic from 'next/dynamic';

// Dynamically import ApexChart with SSR disabled to avoid window is not defined errors
const ApexChart = dynamic(() => import('react-apexcharts').then((mod) => mod.default), { ssr: false });
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useSLATrackingDashboardMetrics } from '../hooks/useConversationSLATracking';
import { formatDate } from '@/lib/helpers';
import { Skeleton } from '@/components/ui/skeleton';
import { RefreshCw } from 'lucide-react';

export default function SLATrackingDashboard() {
  const queryClient = useQueryClient();
  const { data: metrics, isLoading } = useSLATrackingDashboardMetrics();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await queryClient.invalidateQueries({ queryKey: ['sla-tracking-dashboard-metrics'] });
    setIsRefreshing(false);
  };

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {Array.from({ length: 8 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-32" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!metrics) {
    return null;
  }

  // Response + Resolution trends over past 30 days (from event logs)
  const responseResolutionTrendsOptions: ApexOptions = {
    series: [
      {
        name: 'Average Response Time (hours)',
        data: metrics.response_resolution_trends.map((t) => t.average_response_time),
      },
      {
        name: 'Average Resolution Time (hours)',
        data: metrics.response_resolution_trends.map((t) => t.average_resolution_time),
      },
    ],
    chart: {
      height: 250,
      type: 'area',
      toolbar: { show: false },
    },
    dataLabels: { enabled: false },
    stroke: {
      curve: 'smooth',
      width: 3,
      colors: ['var(--color-primary)', 'var(--color-green-500)'],
    },
    fill: {
      type: 'gradient',
      gradient: {
        shadeIntensity: 1,
        opacityFrom: 0.7,
        opacityTo: 0.3,
        stops: [0, 100],
      },
    },
    xaxis: {
      categories: metrics.response_resolution_trends.map((t) => {
        const date = new Date(t.date);
        return formatDate(date);
      }),
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: {
        style: {
          colors: 'var(--color-secondary-foreground)',
          fontSize: '12px',
        },
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: 'var(--color-secondary-foreground)',
          fontSize: '12px',
        },
        formatter: (val: number) => `${val.toFixed(1)}h`,
      },
    },
    tooltip: {
      y: {
        formatter: (val: number) => `${val.toFixed(2)} hours`,
      },
    },
    grid: {
      borderColor: 'var(--color-border)',
      strokeDashArray: 5,
    },
  };

  // Total conversation statuses (mutually exclusive)
  const statusBreakdownOptions: ApexOptions = {
    series: [
      metrics.status_breakdown.pending,
      metrics.status_breakdown.responded_not_resolved,
      metrics.status_breakdown.resolved,
    ],
    labels: ['Pending', 'Responded (Not Resolved)', 'Resolved'],
    chart: {
      type: 'pie',
      height: 250,
    },
    colors: ['var(--color-blue-500)', 'var(--color-orange-500)', 'var(--color-green-500)'],
    dataLabels: { enabled: true },
    legend: {
      position: 'bottom',
      labels: {
        colors: 'var(--color-secondary-foreground)',
      },
    },
  };

  // Pending conversations split by response overdue
  const pendingResponseOverdueOptions: ApexOptions = {
    series: [
      metrics.pending_response_overdue_breakdown.not_yet_overdue,
      metrics.pending_response_overdue_breakdown.overdue_at_response,
    ],
    labels: ['Pending Not Yet Overdue', 'Overdue at Response'],
    chart: {
      type: 'pie',
      height: 250,
    },
    colors: ['var(--color-blue-500)', 'var(--color-amber-500)'],
    dataLabels: { enabled: true },
    legend: {
      position: 'bottom',
      labels: {
        colors: 'var(--color-secondary-foreground)',
      },
    },
  };

  // Responded but unresolved split by resolution overdue
  const respondedResolutionOverdueOptions: ApexOptions = {
    series: [
      metrics.responded_resolution_overdue_breakdown.not_yet_overdue,
      metrics.responded_resolution_overdue_breakdown.overdue_at_resolution,
    ],
    labels: ['Responded Not Yet Overdue', 'Overdue at Resolution'],
    chart: {
      type: 'pie',
      height: 250,
    },
    colors: ['var(--color-orange-400)', 'var(--color-red-500)'],
    dataLabels: { enabled: true },
    legend: {
      position: 'bottom',
      labels: {
        colors: 'var(--color-secondary-foreground)',
      },
    },
  };

  return (
    <div className="space-y-6">
      {/* Header with Refresh Button */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">SLA Tracking Dashboard</h2>
        <Button
          variant="outline"
          onClick={handleRefresh}
          disabled={isRefreshing || isLoading}
        >
          <RefreshCw className={`size-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
          Refresh Metrics
        </Button>
      </div>

      {/* KPI Cards - all from conversation SLA tracking table */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Conversations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.total_trackings ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Pending</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">{metrics.pending_count ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {metrics.total_trackings > 0
                ? `${(((metrics.pending_count ?? 0) / metrics.total_trackings) * 100).toFixed(1)}%`
                : '0%'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Responded</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.responded_count ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {metrics.total_trackings > 0
                ? `${(((metrics.responded_count ?? 0) / metrics.total_trackings) * 100).toFixed(1)}%`
                : '0%'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Resolved</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{metrics.resolved_count ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {metrics.total_trackings > 0
                ? `${((metrics.resolved_count / metrics.total_trackings) * 100).toFixed(1)}%`
                : '0%'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Overdue at Response</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-600">{metrics.overdue_at_response_count ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Overdue at Resolution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">{metrics.overdue_at_resolution_count ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Average Response Time</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(metrics.average_response_time ?? 0).toFixed(1)}h
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Average Resolution Time</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(metrics.average_resolution_time ?? 0).toFixed(1)}h
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Response Time Trends (30 Days)</CardTitle>
          </CardHeader>
          <CardContent>
            <ApexChart
              options={responseResolutionTrendsOptions}
              series={responseResolutionTrendsOptions.series}
              type="area"
              height={250}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Conversation Status Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center items-center">
            <ApexChart
              options={statusBreakdownOptions}
              series={statusBreakdownOptions.series}
              type="pie"
              height={250}
              width="100%"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pending Conversations Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center items-center">
            <ApexChart
              options={pendingResponseOverdueOptions}
              series={pendingResponseOverdueOptions.series}
              type="pie"
              height={250}
              width="100%"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Responded Conversation Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center items-center">
            <ApexChart
              options={respondedResolutionOverdueOptions}
              series={respondedResolutionOverdueOptions.series}
              type="pie"
              height={250}
              width="100%"
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
