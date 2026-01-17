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
        {Array.from({ length: 4 }).map((_, i) => (
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

  // Response Time Trends Chart (Area)
  const responseTimeTrendsOptions: ApexOptions = {
    series: [
      {
        name: 'Average Response Time (hours)',
        data: metrics.response_time_trends.map((t) => t.average_response_time),
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
      colors: ['var(--color-primary)'],
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
      categories: metrics.response_time_trends.map((t) => {
        const date = new Date(t.date);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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

  // Escalation Rates by Tier Chart (Bar)
  const escalationRatesOptions: ApexOptions = {
    series: [
      {
        name: 'Escalation Count',
        data: metrics.escalation_rates_by_tier.map((t) => t.escalation_count),
      },
    ],
    chart: {
      height: 250,
      type: 'bar',
      toolbar: { show: false },
    },
    dataLabels: { enabled: true },
    xaxis: {
      categories: metrics.escalation_rates_by_tier.map((t) => `Tier ${t.tier_level}`),
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
      },
    },
    colors: ['var(--color-orange-500)'],
    grid: {
      borderColor: 'var(--color-border)',
      strokeDashArray: 5,
    },
  };

  // Resolution Time Distribution Chart (Donut)
  const resolutionDistributionOptions: ApexOptions = {
    series: [metrics.resolution_time_distribution.resolved, metrics.resolution_time_distribution.unresolved],
    labels: ['Resolved', 'Unresolved'],
    chart: {
      type: 'donut',
      height: 250,
    },
    colors: ['var(--color-green-500)', 'var(--color-gray-400)'],
    dataLabels: { enabled: true },
    legend: {
      position: 'bottom',
      labels: {
        colors: 'var(--color-secondary-foreground)',
      },
    },
    plotOptions: {
      pie: {
        donut: {
          size: '70%',
        },
      },
    },
  };

  // Status Breakdown Chart (Pie)
  const statusBreakdownOptions: ApexOptions = {
    series: [
      metrics.status_breakdown.resolved,
      metrics.status_breakdown.escalated,
      metrics.status_breakdown.pending,
    ],
    labels: ['Resolved', 'Escalated', 'Pending'],
    chart: {
      type: 'pie',
      height: 250,
    },
    colors: [
      'var(--color-green-500)',
      'var(--color-orange-500)',
      'var(--color-blue-500)',
    ],
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

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Trackings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.total_trackings}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Resolved</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{metrics.resolved_count}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {metrics.total_trackings > 0
                ? `${((metrics.resolved_count / metrics.total_trackings) * 100).toFixed(1)}%`
                : '0%'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Average Resolution Time</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.average_resolution_time.toFixed(1)}h
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Escalation Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              {metrics.escalation_rate.toFixed(1)}%
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {metrics.escalated_count} escalated
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
              options={responseTimeTrendsOptions}
              series={responseTimeTrendsOptions.series}
              type="area"
              height={250}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Escalation Rates by Tier</CardTitle>
          </CardHeader>
          <CardContent>
            <ApexChart
              options={escalationRatesOptions}
              series={escalationRatesOptions.series}
              type="bar"
              height={250}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Resolution Time Distribution</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center items-center">
            <ApexChart
              options={resolutionDistributionOptions}
              series={resolutionDistributionOptions.series}
              type="donut"
              height={250}
              width="100%"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Status Breakdown</CardTitle>
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
      </div>
    </div>
  );
}
